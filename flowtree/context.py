"""执行上下文: 唯一一处决定"实际传给被测子进程 / 运行时探测 / git 的环境"。

执行、前后基线、CLI 状态、Web 只读重检全部调用 `resolve()`, 不再各自拼装环境。

两种模式:
- inherit (默认, 与此前行为逐字节一致): 宿主环境 + 声明的覆盖项 (+ git excludes 以 GIT_CONFIG_* 传入)。
  宿主环境不同, 环境摘要就不同; 旧证据保持有效 (context_digest 恒为 None)。
- pinned: 子进程环境**只**包含固定的 PATH + `env` 字面值 + `env_from_host` 声明的宿主变量 + FlowTree 注入项。
  先约束实际环境, 再对**实际环境**取完整摘要; 未声明的宿主变量根本不会进入测试, 因而变化与测试无关。
  git 调用同样隔离 (不读宿主的系统/全局 git 配置), 工作区指纹不随宿主 git 配置变化。

机密与凭据: `env` 只放非机密字面值 (疑似密钥或 URL 内嵌凭据的值会被配置校验拒绝);
`env_from_host` 的值在运行/重检时从启动进程的宿主环境读取, 永不写入配置、manifest、响应或日志。
缺少必需的宿主变量 → 明确的 problems (执行为 blocked, 重检为 unknown), 绝不静默退回宿主环境。

context_digest 只在 pinned 下非空: 模式、变量名集合、git 隔离方式、git excludes 文件内容摘要 (不含任何值)。
"""
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from . import baseline as bl

MODES = ("inherit", "pinned")
DEFAULT_PINNED_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
SECRET_NAME = re.compile(r"(SECRET|TOKEN|PASSW(OR)?D|CREDENTIAL|PRIVATE|API_?KEY|ACCESS_?KEY)", re.I)
URL_CREDENTIAL = re.compile(r"://[^/@\s:]+:[^/@\s]+@")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
GIT_ISOLATION = "git-isolated-v1"


@dataclass
class ContextSpec:
    mode: str = "inherit"
    env: Dict[str, str] = field(default_factory=dict)          # 字面值 (非机密)
    env_from_host: Tuple[str, ...] = ()                         # 值来自宿主环境 (机密/凭据)
    pinned_path: Optional[str] = None
    git_excludes_file: Optional[Path] = None

    def validate(self) -> List[str]:
        out: List[str] = []
        if self.mode not in MODES:
            out.append(f"mode must be one of {MODES}, got {self.mode!r}")
        for k, v in self.env.items():
            if not ENV_NAME.match(k):
                out.append(f"env name {k!r} is not a valid variable name")
            if SECRET_NAME.search(k) or URL_CREDENTIAL.search(str(v)):
                out.append(f"env {k!r} looks like a secret/credential: do not write it into configuration; list the name under env_from_host")
        for k in self.env_from_host:
            if not ENV_NAME.match(k):
                out.append(f"env_from_host name {k!r} is not a valid variable name")
            if k in self.env:
                out.append(f"{k!r} is declared both in env and env_from_host")
        if self.pinned_path and self.mode != "pinned":
            out.append("pinned_path is only meaningful with mode: pinned")
        return out

    def identity(self) -> str:
        """缓存/比较身份: 影响解析结果的全部声明。字面值参与, 但只留在内存。"""
        return repr((self.mode, tuple(sorted(self.env.items())), tuple(sorted(self.env_from_host)),
                     self.pinned_path, str(self.git_excludes_file) if self.git_excludes_file else None))


@dataclass
class ResolvedContext:
    spec: ContextSpec
    env: Dict[str, str]                       # 实际传给被测子进程的环境 (不含本次尝试专属的 FLOWTREE_* 注入)
    git_env: Optional[Dict[str, str]]         # git 调用所用环境; None = 沿用 env (inherit 的既有行为)
    problems: List[str]
    context_digest: Optional[str]
    removed_addopts: Optional[str] = None     # 被清除的宿主 PYTEST_ADDOPTS (仅 inherit 可能有)

    @property
    def effective_git_env(self) -> Dict[str, str]:
        return self.git_env if self.git_env is not None else self.env

    def summary(self) -> Dict[str, object]:
        """可展示的摘要: 只有名称与布尔, 没有任何值。"""
        return {
            "mode": self.spec.mode, "env_names": sorted(self.spec.env), "env_from_host": sorted(self.spec.env_from_host),
            "git_excludes_configured": self.spec.git_excludes_file is not None,
            "git_isolated": self.git_env is not None, "problems": list(self.problems),
            "context_digest": self.context_digest,
        }


def _file_digest(path: Optional[Path]) -> Optional[str]:
    if not path:
        return None
    try:
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return "unreadable"


def resolve(spec: Optional[ContextSpec] = None, host: Optional[Mapping[str, str]] = None) -> ResolvedContext:
    spec = spec or ContextSpec()
    host = os.environ if host is None else host
    problems = list(spec.validate())
    plugin = str(bl.PLUGIN_DIR)

    if spec.mode == "pinned":
        env: Dict[str, str] = {"PATH": spec.pinned_path or DEFAULT_PINNED_PATH}
        env.update(spec.env)
        for name in spec.env_from_host:
            if name in host:
                env[name] = host[name]
            else:
                problems.append(f"required host variable {name} is not set (declared in env_from_host)")
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [plugin, env.get("PYTHONPATH")]))
        git_env = {"PATH": env["PATH"], "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "LC_ALL": "C"}
        if spec.git_excludes_file:
            git_env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.excludesFile",
                            "GIT_CONFIG_VALUE_0": str(spec.git_excludes_file)})
        digest = "sha256:" + hashlib.sha256(json.dumps({
            "mode": "pinned", "git": GIT_ISOLATION, "env_names": sorted(spec.env),
            "from_host": sorted(spec.env_from_host), "excludes": _file_digest(spec.git_excludes_file),
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return ResolvedContext(spec, env, git_env, problems, digest, None)

    # inherit: 与此前 child_env + Workspace.execution_env 的拼装逐项一致
    env = dict(host)
    env.update(spec.env)
    if spec.git_excludes_file:
        count = int(host.get("GIT_CONFIG_COUNT", "0") or 0)
        env["GIT_CONFIG_COUNT"] = str(count + 1)
        env[f"GIT_CONFIG_KEY_{count}"] = "core.excludesFile"
        env[f"GIT_CONFIG_VALUE_{count}"] = str(spec.git_excludes_file)
    for name in spec.env_from_host:      # inherit 下宿主变量本就在 env 里; 仍要求存在, 缺失明确报告
        if name not in host:
            problems.append(f"required host variable {name} is not set (declared in env_from_host)")
    removed = env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [plugin, env.get("PYTHONPATH")]))
    return ResolvedContext(spec, env, None, problems, None, removed)
