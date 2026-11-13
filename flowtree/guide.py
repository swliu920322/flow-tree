"""人工验收指引 (schema_version 0.1): 只读展示, 说明"人亲手验收时怎么做"。

指引不是规则, 也不是验收记录; 它不进入故事摘要, 不改变自动化结果或人工状态。
指引通过 story_digest 绑定当时的故事内容: 故事变了, 指引变为"待核对" (stale), 即使引用的 ID 仍然存在。
状态: current | stale | invalid。没有指引文件是正常缺省 (调用方不会拿到该故事的条目)。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .canon import YamlLoadError, content_digest, load_yaml_file
from .issues import ERROR, WARNING, Issue, has_errors
from .story import SCHEMA_VERSION, StorySet, collect_yaml_files, empty_input_issues

CURRENT, STALE, INVALID = "current", "stale", "invalid"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Environment(_Strict):
    summary: str = Field(min_length=1)
    # 只作文字展示, 不可点击执行
    start: List[str] = Field(default_factory=list)


class Account(_Strict):
    # 仅隔离验收环境的夹具账号; 不得放真实 token 或真实用户凭据。用途/显示名不是权限证明。
    username: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=1)
    purpose: str = Field(min_length=1)


class GuideStep(_Strict):
    target: str = Field(alias="for", min_length=1)   # 故事里真实的步骤或分支 ID (非限定)
    account: Optional[str] = None                    # 引用 accounts 里的 username
    do: str = Field(min_length=1)
    see: str = Field(min_length=1)                   # 具体操作现象; 与故事 expected (规则) 区分
    if_not: str = Field(min_length=1)


class Auxiliary(_Strict):
    target: str = Field(alias="for", min_length=1)
    text: str = Field(min_length=1)
    note: Optional[str] = None


class Guide(_Strict):
    schema_version: str
    story: str
    story_digest: str = Field(min_length=1)
    environment: Environment
    accounts: List[Account] = Field(default_factory=list)
    steps: List[GuideStep] = Field(min_length=1)
    auxiliary: List[Auxiliary] = Field(default_factory=list)


@dataclass
class LoadedGuide:
    path: Path
    guide: Optional[Guide]
    digest: Optional[str]
    status: str
    issues: List[Issue] = field(default_factory=list)


def _check(guide: Guide, path: Path, stories: StorySet, issues: List[Issue]) -> bool:
    """返回 True 表示故事摘要与指引绑定的一致。"""
    where = str(path)
    if guide.schema_version != SCHEMA_VERSION:
        issues.append(Issue(ERROR, "guide.schema_version", where, f"unsupported schema_version {guide.schema_version!r}; expected {SCHEMA_VERSION!r}"))
    users = [a.username for a in guide.accounts]
    for u in sorted({u for u in users if users.count(u) > 1}):
        issues.append(Issue(ERROR, "guide.duplicate_account", where, f"account {u!r} listed twice"))

    loaded = stories.get(guide.story)
    if loaded is None or loaded.story is None:
        issues.append(Issue(ERROR, "guide.dangling_ref", where, f"guide refers to unknown or invalid story {guide.story!r}"))
        return True
    story_errors = [i for i in loaded.issues if i.severity == ERROR]
    if story_errors:
        # 只看该故事自己的问题; 其他故事的错误不连带
        issues.append(Issue(ERROR, "guide.story_invalid", where, f"story {guide.story!r} has {len(story_errors)} error(s) (first: {story_errors[0].code}); a guide cannot be current for an invalid story"))
    units = set(loaded.story.unit_ids())
    seen = set()
    for i, s in enumerate(guide.steps):
        w = f"{guide.story}.guide.steps[{i}]"
        if s.target not in units:
            issues.append(Issue(ERROR, "guide.dangling_ref", w, f"for refers to unknown step/branch {s.target!r}"))
        if s.target in seen:
            issues.append(Issue(ERROR, "guide.duplicate_step", w, f"step/branch {s.target!r} already has a guide step"))
        seen.add(s.target)
        if s.account is not None and s.account not in users:
            issues.append(Issue(ERROR, "guide.unknown_account", w, f"account {s.account!r} is not declared in accounts"))
    for i, a in enumerate(guide.auxiliary):
        if a.target not in units:
            issues.append(Issue(ERROR, "guide.dangling_ref", f"{guide.story}.guide.auxiliary[{i}]", f"for refers to unknown step/branch {a.target!r}"))
    covered = seen | {a.target for a in guide.auxiliary}
    for u in loaded.story.unit_ids():
        if u not in covered:
            issues.append(Issue(WARNING, "guide.unit_uncovered", f"{guide.story}.{u}", "story step/branch has no guide step"))
    if guide.story_digest != loaded.digest:
        issues.append(Issue(ERROR, "guide.story_changed", where, f"guide was written for story digest {guide.story_digest} but the story is now {loaded.digest}; re-check the guide steps against the story and update story_digest"))
        return False
    return True


def load_guide_file(path: Path, stories: StorySet) -> LoadedGuide:
    path = Path(path)
    try:
        raw = load_yaml_file(path)
    except YamlLoadError as e:
        return LoadedGuide(path, None, None, INVALID, [Issue(ERROR, "guide.yaml", str(path), str(e))])
    if not isinstance(raw, dict):
        return LoadedGuide(path, None, None, INVALID, [Issue(ERROR, "guide.not_mapping", str(path), "guide file must be a YAML mapping")])
    try:
        digest = content_digest(raw)
    except YamlLoadError as e:
        return LoadedGuide(path, None, None, INVALID, [Issue(ERROR, "guide.yaml", str(path), str(e))])
    issues: List[Issue] = []
    try:
        guide = Guide.model_validate(raw)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            issues.append(Issue(ERROR, "guide.schema", f"{path}:{loc}", err["msg"]))
        return LoadedGuide(path, None, digest, INVALID, issues)
    digest_ok = _check(guide, path, stories, issues)
    only_stale = digest_ok is False and not has_errors([i for i in issues if i.code != "guide.story_changed"])
    status = CURRENT if not has_errors(issues) else (STALE if only_stale else INVALID)
    return LoadedGuide(path, guide, digest, status, issues)


@dataclass
class GuideSet:
    guides: Dict[str, LoadedGuide] = field(default_factory=dict)   # story_id -> 指引
    issues: List[Issue] = field(default_factory=list)

    def get(self, story_id: str) -> Optional[LoadedGuide]:
        return self.guides.get(story_id)


def load_guides(paths: List[Path], stories: StorySet) -> GuideSet:
    """paths 为空 = 未配置指引, 正常缺省。已配置的目录里没有文件、文件损坏、引用错误都会报告。"""
    result = GuideSet()
    result.issues.extend(empty_input_issues(paths, "guide.empty_dir", "guide"))
    for f in collect_yaml_files(paths):
        loaded = load_guide_file(f, stories)
        result.issues.extend(loaded.issues)
        if loaded.guide is None:
            continue
        sid = loaded.guide.story
        first = result.guides.get(sid)
        if first is not None:
            # 内容冲突: 不按文件顺序择一; 已收录的那份也降为 invalid, 后来的不收录
            issue = Issue(ERROR, "guide.duplicate_story", str(f), f"story {sid!r} already has a guide in {first.path}; conflicting guides are not resolved by file order")
            result.issues.append(issue)
            if not any(i.code == "guide.duplicate_story" for i in first.issues):
                first.issues.append(Issue(ERROR, "guide.duplicate_story", str(first.path), f"another guide for story {sid!r} exists in {f}"))
            first.status = INVALID
            continue
        result.guides[sid] = loaded
    return result


def guide_payload(lg: LoadedGuide) -> Dict[str, Any]:
    """CLI 与 Web 共用的可序列化形式。只有 current 的指引才带出可操作的步骤与账号;
    待核对 (stale) 或无效 (invalid) 时只给状态与原因, 不当作当前可用的操作步骤。"""
    out: Dict[str, Any] = {"status": lg.status, "path": str(lg.path), "digest": lg.digest,
                           "issues": [i.to_dict() for i in lg.issues], "usable": lg.status == CURRENT}
    if lg.status == CURRENT and lg.guide is not None:
        g = lg.guide
        out["environment"] = g.environment.model_dump()
        out["accounts"] = [a.model_dump() for a in g.accounts]
        out["steps"] = {s.target: {"account": s.account, "do": s.do, "see": s.see, "if_not": s.if_not} for s in g.steps}
        aux: Dict[str, List[Dict[str, Any]]] = {}
        for a in g.auxiliary:
            aux.setdefault(a.target, []).append({"text": a.text, "note": a.note})
        out["auxiliary"] = aux
    return out


def unattached_issues(gs: GuideSet) -> List[Issue]:
    """没有归属到任何已收录指引的问题 (文件损坏、空目录、被拒收的重复指引等); 页面必须显示, 不能静默。"""
    owned = {id(i) for lg in gs.guides.values() for i in lg.issues}
    return [i for i in gs.issues if id(i) not in owned]
