"""伴随运行时 (companion runtime): 被测行为所依赖、但不是 runner 自己探测的那部分运行环境。

例: Flutter 客户端联调测试会启动后端 Python 进程。后端解释器及其依赖在被忽略的 venv 里, 不在工作区指纹内,
现有 runner 的运行时摘要也不覆盖它们; 不绑定就会出现"改了依赖, 旧联调证据仍显示通过"。

配置分两层 (机器路径不进可移植映射):
- 映射 entry: `companions: [<名字>]`。
- 工作区配置: `companions: {<名字>: {kind, interpreter, bind_env}}`。

语义 (与现有运行时摘要一致, 只替换"运行时摘要"这一个值, 不新增失效机制):
- 未声明 companions 的 entry: 摘要与原来逐字节相同。
- 声明后: 组合摘要 = H(runner 自己的摘要, {名字: 伴随项摘要})。执行前、执行后 (重新探测, 不复用执行前的值)、
  只读重检用同一个函数。组合摘要变化 → 本次作废 / 证据 stale。
- 配置缺失、名字未知、绑定不一致、探测失败 → 摘要为 None 并带 error: 执行 blocked, 重检 unknown。
- 只保存组合摘要, 不能据此判断是哪个伴随项变了 (逐项展示需要另存可比较的逐项摘要, 本版不提供)。
- kind=python: 只读探测 (解释器 -I -B (不写字节码)、清洗环境、超时、不联网/不安装): 路径、版本、sqlite3 库版本、已安装发行包 名称==版本。
  不覆盖同版本包被原地改文件、操作系统库。

绑定: bind_env 是"测试实际收到解释器路径"的环境变量名。声明的解释器必须与该变量在实际子进程环境里的值一致
(实际值必须是绝对路径, 相对/~ 一律拒绝; 按规范化后的路径字符串比较, 不解析符号链接: 两个 venv 可能指向同一个基础解释器), 否则 blocked/unknown, 不会出现
"探测环境 A、实际运行环境 B"。
"""
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .runners import RuntimeProbe

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PROBE_TIMEOUT_S = 60
PROBE_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"}


@dataclass(frozen=True)
class CompanionSpec:
    name: str
    kind: str
    interpreter: str          # 绝对路径
    bind_env: str             # 测试实际接收该解释器路径的环境变量名


_PY_PROBE = r"""
import json, os, sys, sqlite3
import importlib.metadata as md
pk = set()
for d in md.distributions():
    n = d.metadata["Name"]
    if n:
        pk.add(n.lower().replace("_", "-") + "==" + d.version)
print(json.dumps({"prefix": sys.prefix, "version": sys.version, "sqlite_version": sqlite3.sqlite_version,
                  "packages": sorted(pk)}, sort_keys=True))
"""


def _canon_digest(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def probe_python(spec: CompanionSpec) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """返回 (摘要, 可展示信息, 错误)。信息不含路径/包清单, 只有版本与计数。"""
    exe = spec.interpreter
    if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
        return None, None, f"companion {spec.name!r}: interpreter not found or not executable"
    try:
        r = subprocess.run([exe, "-I", "-B", "-c", _PY_PROBE], capture_output=True, text=True,
                           timeout=PROBE_TIMEOUT_S, env=dict(PROBE_ENV), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return None, None, f"companion {spec.name!r}: interpreter probe failed: {type(e).__name__}"
    if r.returncode != 0:
        return None, None, f"companion {spec.name!r}: interpreter probe failed (exit {r.returncode})"
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return None, None, f"companion {spec.name!r}: interpreter probe produced unparsable output"
    ident = {"kind": "python", "interpreter": os.path.abspath(exe), **data}
    info = {"kind": "python", "python": data["version"].split()[0], "sqlite": data["sqlite_version"],
            "packages": len(data["packages"])}
    return _canon_digest(ident), info, None


PROBES: Dict[str, Callable[[CompanionSpec], Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]]] = {
    "python": probe_python,
}


def validate_spec(name: str, raw: Any) -> Tuple[Optional[CompanionSpec], List[str]]:
    where = f"companions.{name}"
    if not NAME_RE.match(name):
        return None, [f"{where}: name must match {NAME_RE.pattern}"]
    if not isinstance(raw, dict):
        return None, [f"{where}: must be a mapping"]
    out: List[str] = []
    unknown = set(raw) - {"kind", "interpreter", "bind_env"}
    if unknown:
        out.append(f"{where}: unknown fields {sorted(unknown)}")
    kind = raw.get("kind")
    if kind not in PROBES:
        out.append(f"{where}: kind must be one of {sorted(PROBES)}")
    interp = raw.get("interpreter")
    if not isinstance(interp, str) or not os.path.isabs(os.path.expanduser(interp)):
        out.append(f"{where}: interpreter must be an absolute path")
    bind = raw.get("bind_env")
    if not isinstance(bind, str) or not ENV_NAME_RE.match(bind):
        out.append(f"{where}: bind_env must name the environment variable through which the test receives the interpreter")
    if out:
        return None, out
    return CompanionSpec(name, kind, os.path.abspath(os.path.expanduser(interp)), bind), []


def cache_key(entry, specs: Mapping[str, CompanionSpec], env: Mapping[str, str]) -> Optional[tuple]:
    """影响伴随探测结果的全部输入 (配置 + 实际绑定值)。未声明 companions → None, 原缓存键不变。"""
    names = tuple(getattr(entry, "companions", ()) or ())
    if not names:
        return None
    parts = []
    for n in names:
        s = specs.get(n)
        parts.append((n, None) if s is None else (n, s.kind, s.interpreter, s.bind_env, env.get(s.bind_env)))
    return tuple(parts)


def _binding_problem(spec: CompanionSpec, env: Mapping[str, str]) -> Optional[str]:
    actual = env.get(spec.bind_env)
    if actual is None:
        return f"companion {spec.name!r}: {spec.bind_env} is not set in the test environment, cannot confirm the declared interpreter is the one in use"
    if not os.path.isabs(actual):   # 相对路径/~ 取决于各进程自己的 cwd/HOME: 验证器与被测进程可能指向不同解释器
        return f"companion {spec.name!r}: {spec.bind_env} must be an absolute path, a relative or ~ value can resolve to a different interpreter in the test process"
    if os.path.normpath(actual) != spec.interpreter:
        return f"companion {spec.name!r}: {spec.bind_env} does not match the declared interpreter (probing environment A while the test would run in B)"
    return None


def probe_companions(entry, env: Mapping[str, str], specs: Optional[Mapping[str, CompanionSpec]] = None
                     ) -> Tuple[Dict[str, str], Dict[str, Any], List[str]]:
    """对 entry 声明的伴随项做一次全新的只读探测 (从不复用缓存)。返回 (逐项摘要, 可展示信息, 问题)。"""
    specs = specs or {}
    problems: List[str] = []
    items: Dict[str, str] = {}
    infos: Dict[str, Any] = {}
    for n in (getattr(entry, "companions", ()) or ()):
        s = specs.get(n)
        if s is None:
            problems.append(f"companion {n!r} is not configured in the workspace")
            continue
        p = _binding_problem(s, env)
        if p:
            problems.append(p)
            continue
        digest, info, err = PROBES[s.kind](s)
        if err:
            problems.append(err)
        else:
            items[n], infos[n] = digest, info
    return items, infos, problems


def combine(base_digest: Optional[str], items: Mapping[str, str]) -> Optional[str]:
    """组合摘要: 只保存这一个值, 不能据此判断哪个伴随项变了。"""
    if base_digest is None:
        return None
    return _canon_digest({"base": base_digest, "companions": dict(items)})


def runtime_with_companions(runner, entry, exe, python, env, cwd, project_root,
                            specs: Optional[Mapping[str, CompanionSpec]] = None) -> RuntimeProbe:
    """执行前 / 只读重检用: runner 自己的探测 + 声明的伴随项。(执行后见 execution: 对 runner 报告的"实际运行时"同样组合。)"""
    base = runner.runtime(entry, exe, python, env, cwd, project_root)
    if not getattr(entry, "companions", None) or base.error:
        return base
    items, infos, problems = probe_companions(entry, env, specs)
    info_out = dict(base.info or {})
    if problems:
        return RuntimeProbe(None, info_out, "; ".join(problems))
    info_out["companions"] = infos
    return RuntimeProbe(combine(base.digest, items), info_out, None)
