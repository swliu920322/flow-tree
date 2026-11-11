"""基线采集: 工作区内容指纹、提交 SHA、被测运行时指纹。

worktree_fingerprint = 对 `git ls-files --cached --others --exclude-standard` 列出的全部文件
(已跟踪, 且包含未被忽略的未跟踪文件) 逐个取 (相对路径, 内容 sha256) 后合并哈希。
- 与提交 SHA 无关: 内容相同的不同提交等价; 未提交修改与未跟踪源码都会改变指纹。
- 已删除但仍在索引中的文件记为 <deleted>; 符号链接按其目标文本计。
- 被 .gitignore 忽略的内容 (例如 .venv、.flowtree) 不在其中, 环境另由 runtime 指纹追溯。
exclude: 本次执行所用的故事/映射文件 (已由 story_digest / entry_digest 绑定), 避免改一个映射条目使全部条目过期。
非 git 目录、git 不可用或读取失败 → None (有效性 unknown), 不退化为"无变化"。
"""
import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

PLUGIN_DIR = Path(__file__).resolve().parent / "plugin"
PLUGIN_FILE = PLUGIN_DIR / "flowtree_pytest_plugin.py"


def _git(args, cwd, env: Optional[dict] = None) -> Optional[bytes]:
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def git_head(cwd: Path, env: Optional[dict] = None) -> Optional[str]:
    out = _git(["rev-parse", "HEAD"], cwd, env)
    return out.decode().strip() if out else None


def worktree_fingerprint(cwd: Path, exclude: frozenset = frozenset(), env: Optional[dict] = None) -> Optional[str]:
    """env: 传给 git 的环境。执行时用过的 git 配置 (例如只对本次命令生效的 core.excludesFile) 必须在重检时保持一致。"""
    top = _git(["rev-parse", "--show-toplevel"], cwd, env)
    if not top:
        return None
    root = Path(top.decode().strip())
    listing = _git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], root, env)
    if listing is None:
        return None
    h = hashlib.sha256()
    for rel in sorted(set(x for x in listing.split(b"\0") if x)):
        path = root / os.fsdecode(rel)
        if exclude and Path(os.path.realpath(path)) in exclude:
            continue  # 本次使用的故事/映射文件已由各自的摘要绑定, 不在这里重复计入
        h.update(rel + b"\0")
        try:
            if path.is_symlink():
                h.update(b"L" + os.fsencode(os.readlink(path)))
            elif path.is_file():
                fh = hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        fh.update(chunk)
                h.update(b"F" + fh.digest())
            elif not os.path.lexists(path):
                h.update(b"<deleted>")
            else:  # 子模块等目录条目
                h.update(b"D")
        except OSError:
            return None
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


_PROBE = (
    "import importlib.util, json, sys;"
    "spec = importlib.util.spec_from_file_location('flowtree_pytest_plugin', sys.argv[1]);"
    "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
    "print(json.dumps(m.runtime_info()))"
)


def probe_runtime(python_exe: str, env: dict) -> Tuple[Optional[dict], Optional[str]]:
    """用与执行相同的解释器探测运行时。返回 (info, error)。缺 pytest 等视为环境前置缺失。"""
    try:
        r = subprocess.run([python_exe, "-I", "-B", "-c", _PROBE, str(PLUGIN_FILE)],
                           capture_output=True, text=True, timeout=60, env=env)
    except FileNotFoundError:
        return None, f"interpreter not found: {python_exe}"
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"interpreter probe failed: {e}"
    if r.returncode != 0:
        tail = r.stderr.strip().splitlines()[-1:] or ["no stderr"]
        return None, f"interpreter probe failed (is pytest installed in it?): {tail[0]}"
    try:
        return json.loads(r.stdout), None
    except ValueError:
        return None, "interpreter probe produced unparsable output"


# ---- 环境配置摘要 ----
# 传给被测进程的环境变量会影响测试结果 (env.id 只是标签)。默认全部纳入, 去掉已知的会话级噪声;
# 其余变量变化 → 证据 stale (宁可多失效, 不沿用旧通过)。映射可用 env.ignore 声明确实无关的变量。
# 只保存 HMAC (项目本地随机盐), 不落明文, 也不能由摘要反推出低熵的值。
VOLATILE_ENV = frozenset({
    "_", "PWD", "OLDPWD", "SHLVL", "TERM_SESSION_ID", "SECURITYSESSIONID", "ITERM_SESSION_ID", "WINDOWID",
    "LINES", "COLUMNS", "XPC_FLAGS", "XPC_SERVICE_NAME", "LaunchInstanceID", "__CF_USER_TEXT_ENCODING",
    "Apple_PubSub_Socket_Render", "SSH_AUTH_SOCK", "SSH_AGENT_PID", "DISPLAY", "PYTEST_CURRENT_TEST",
    "FLOWTREE_REPORT", "FLOWTREE_RUN_ID", "FLOWTREE_ATTEMPT_ID",
    "FLOWTREE_WORKSPACES",  # Web 服务自己的配置指针, 不属于被测环境。不能按 FLOWTREE_ 前缀排除: 被测代码可能读取同前缀变量
})


def env_salt(project_root: Path, create: bool = True) -> Optional[bytes]:
    """create=False (只读场景): 盐不存在就返回 None —— 不在被测项目里创建任何文件, 环境摘要因此无法计算 (unknown)。"""
    path = Path(project_root) / ".flowtree" / "env.salt"
    try:
        return bytes.fromhex(path.read_text().strip())
    except (OSError, ValueError):
        pass
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(salt.hex())
    return salt


def env_vars_map(env: dict, ignore, salt: bytes) -> dict:
    skip = VOLATILE_ENV | set(ignore or ())
    return {k: hmac.new(salt, f"{k}\0{v}".encode("utf-8", "surrogateescape"), hashlib.sha256).hexdigest()[:32]
            for k, v in env.items() if k not in skip}


def env_digest(vars_map: dict) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(vars_map, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
