"""工作区配置: 把"哪个本地项目、哪些故事/映射、在什么执行上下文里"显式写成配置。

不把任何具体项目的业务规则硬编码进代码。execution_context 描述当初执行证据时的上下文, 用于在只读场景下
重新计算"证据是否仍适用"; 上下文与执行时不一致时有效性会变成 stale/unknown, 不会被悄悄忽略。
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .canon import YamlLoadError, load_yaml_file
from .context import ContextSpec

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / ".flowtree" / "workspaces.yaml"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class WorkspaceConfigError(Exception):
    pass


@dataclass
class Workspace:
    id: str
    name: str
    project_root: Path
    python: Optional[str]
    stories: List[Path]
    mappings: List[Path]
    env: Dict[str, str] = field(default_factory=dict)
    git_excludes_file: Optional[Path] = None
    mode: str = "inherit"
    env_from_host: List[str] = field(default_factory=list)
    pinned_path: Optional[str] = None

    def context(self) -> ContextSpec:
        """CLI 执行/状态与 Web 只读重检共用的唯一上下文声明 (解析见 flowtree.context.resolve)。"""
        return ContextSpec(mode=self.mode, env=dict(self.env), env_from_host=tuple(self.env_from_host),
                           pinned_path=self.pinned_path, git_excludes_file=self.git_excludes_file)

    def env_names(self) -> List[str]:
        return sorted(self.env)

    def problems(self) -> List[str]:
        out = []
        if not self.project_root.is_dir():
            out.append(f"project_root does not exist: {self.project_root}")
        if self.python and not Path(self.python).exists():
            out.append(f"python does not exist: {self.python}")
        if self.git_excludes_file and not self.git_excludes_file.exists():
            out.append(f"git_excludes_file does not exist: {self.git_excludes_file}")
        for p in self.stories:
            if not p.exists():
                out.append(f"story path does not exist: {p}")
        for p in self.mappings:
            if not p.exists():
                out.append(f"mapping path does not exist: {p}")
        return out


def config_path() -> Path:
    return Path(os.environ.get("FLOWTREE_WORKSPACES") or DEFAULT_CONFIG)


def load_workspaces(path: Optional[Path] = None) -> Dict[str, Workspace]:
    path = Path(path) if path else config_path()
    if not path.exists():
        return {}
    try:
        raw = load_yaml_file(path)
    except YamlLoadError as e:
        raise WorkspaceConfigError(str(e))
    if not isinstance(raw, dict) or not isinstance(raw.get("workspaces"), list):
        raise WorkspaceConfigError(f"{path}: expected a mapping with a 'workspaces' list")

    def resolve(p: str) -> Path:
        q = Path(p).expanduser()
        return q if q.is_absolute() else (REPO_ROOT / q)

    out: Dict[str, Workspace] = {}
    for i, w in enumerate(raw["workspaces"]):
        where = f"{path}: workspaces[{i}]"
        if not isinstance(w, dict):
            raise WorkspaceConfigError(f"{where}: must be a mapping")
        wid = w.get("id")
        if not isinstance(wid, str) or not ID_RE.match(wid):
            raise WorkspaceConfigError(f"{where}: id must match {ID_RE.pattern}")
        if wid in out:
            raise WorkspaceConfigError(f"{where}: duplicate workspace id {wid!r}")
        for key in ("project_root", "stories", "mappings"):
            if key not in w:
                raise WorkspaceConfigError(f"{where}: missing {key}")
        ctx = w.get("execution_context") or {}
        env = ctx.get("env") or {}
        if not isinstance(env, dict) or any(not isinstance(k, str) or not ENV_NAME_RE.match(k) for k in env):
            raise WorkspaceConfigError(f"{where}: execution_context.env must map valid variable names to values")
        unknown = set(ctx) - {"mode", "env", "env_from_host", "pinned_path", "git_excludes_file"}
        if unknown:
            raise WorkspaceConfigError(f"{where}: unknown execution_context fields {sorted(unknown)}")
        from_host = ctx.get("env_from_host") or []
        if not isinstance(from_host, list) or any(not isinstance(x, str) for x in from_host):
            raise WorkspaceConfigError(f"{where}: execution_context.env_from_host must be a list of variable names")
        ge = ctx.get("git_excludes_file")
        out[wid] = Workspace(
            id=wid, name=str(w.get("name") or wid), project_root=resolve(w["project_root"]).resolve(),
            python=str(resolve(w["python"])) if w.get("python") else None,
            stories=[resolve(x) for x in (w["stories"] if isinstance(w["stories"], list) else [w["stories"]])],
            mappings=[resolve(x) for x in (w["mappings"] if isinstance(w["mappings"], list) else [w["mappings"]])],
            env={k: str(v) for k, v in env.items()}, git_excludes_file=resolve(ge) if ge else None,
            mode=str(ctx.get("mode") or "inherit"), env_from_host=list(from_host), pinned_path=ctx.get("pinned_path"),
        )
        bad = out[wid].context().validate()
        if bad:
            raise WorkspaceConfigError(f"{where}: execution_context: " + "; ".join(bad))
    return out
