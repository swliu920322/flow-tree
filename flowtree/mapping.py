"""独立技术映射 (schema_version 0.1): 把故事单元关联到真实测试入口。

执行范围必须可证明:
- `tests` 的每一项都是显式对象 {nodeid, match}; 不接受裸字符串、前缀或通配符。
- match=exact: 精确测试标识。pytest: nodeid (可带具体参数实例, 如 test_a[1]);
  flutter: `<相对文件>::<带分组前缀的完整测试名>` (只按第一个 `::` 分隔)。
- match=parametrized: 需要"本次收集集合"证据才能证明参数实例完整, 目前明确拒绝。
- argv 与标识的 runner 专属校验由 flowtree.runners 负责 (pytest: 范围选项黑名单; flutter: 只接受文件路径的白名单)。
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .canon import YamlLoadError, content_digest, load_yaml_file
from .issues import ERROR, WARNING, Issue
from .runners import get_runner, runner_names
from .story import ID_RE, SCHEMA_VERSION, LoadedStory, StorySet, collect_yaml_files

LEVELS = ("code_review", "backend", "client", "e2e")
SUPPORTED_MATCH = ("exact",)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TestRef(_Strict):
    nodeid: str
    match: Literal["exact", "parametrized"]


class EnvRef(_Strict):
    id: str = Field(min_length=1)
    # 默认把传给被测进程的全部环境变量(去掉已知的会话级噪声)纳入有效性; 明确与结果无关的变量可在此声明排除
    ignore: List[str] = Field(default_factory=list)


class Entry(_Strict):
    id: str
    covers: List[str] = Field(min_length=1)
    level: Literal["code_review", "backend", "client", "e2e"]
    runner: str
    cwd: str
    argv: List[str] = Field(min_length=1)
    tests: List[TestRef] = Field(min_length=1)
    env: EnvRef
    timeout_s: int = Field(default=600, ge=1, le=3600)


class Mapping(_Strict):
    schema_version: str
    story: str
    story_digest: Optional[str] = None
    digest: Optional[str] = None
    entries: List[Entry]


@dataclass
class LoadedMapping:
    path: Path
    mapping: Optional[Mapping]
    digest: Optional[str]
    entry_digests: Dict[str, str] = field(default_factory=dict)
    issues: List[Issue] = field(default_factory=list)


def _check_entry(entry: Entry, where: str, issues: List[Issue]) -> None:
    if not ID_RE.match(entry.id):
        issues.append(Issue(ERROR, "mapping.bad_id", where, f"entry id {entry.id!r} must match {ID_RE.pattern}"))
    if entry.runner not in runner_names():
        issues.append(Issue(ERROR, "mapping.runner_unsupported", where, f"runner {entry.runner!r} unsupported (supported: {', '.join(runner_names())})"))
    else:
        get_runner(entry.runner).validate_entry(entry, where, issues)   # argv 与测试标识: runner 专属
    for name in entry.env.ignore:
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            issues.append(Issue(ERROR, "mapping.env_ignore", where, f"env.ignore name {name!r} is not a valid variable name"))
    if Path(entry.cwd).is_absolute():
        issues.append(Issue(WARNING, "mapping.cwd_absolute", where, "absolute cwd is not portable across machines"))

    seen = set()
    for j, t in enumerate(entry.tests):
        tw = f"{where}.tests[{j}]"
        if t.match not in SUPPORTED_MATCH:
            issues.append(Issue(ERROR, "mapping.match_unsupported", tw, f"match={t.match!r} is not supported: parametrized coverage needs collection evidence for the full instance set; use exact test ids"))
        if t.nodeid in seen:
            issues.append(Issue(ERROR, "mapping.duplicate_test", tw, f"nodeid {t.nodeid!r} listed twice in entry"))
        seen.add(t.nodeid)


def load_mapping_file(path: Path, stories: StorySet) -> LoadedMapping:
    path = Path(path)
    try:
        raw = load_yaml_file(path)
    except YamlLoadError as e:
        return LoadedMapping(path, None, None, issues=[Issue(ERROR, "mapping.yaml", str(path), str(e))])
    if not isinstance(raw, dict):
        return LoadedMapping(path, None, None, issues=[Issue(ERROR, "mapping.not_mapping", str(path), "mapping file must be a YAML mapping")])
    try:
        digest = content_digest(raw)
    except YamlLoadError as e:
        return LoadedMapping(path, None, None, issues=[Issue(ERROR, "mapping.yaml", str(path), str(e))])

    issues: List[Issue] = []
    try:
        m = Mapping.model_validate(raw)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            issues.append(Issue(ERROR, "mapping.schema", f"{path}:{loc}", err["msg"]))
        return LoadedMapping(path, None, digest, issues=issues)

    if m.schema_version != SCHEMA_VERSION:
        issues.append(Issue(ERROR, "mapping.schema_version", str(path), f"unsupported schema_version {m.schema_version!r}; expected {SCHEMA_VERSION!r}"))
    if m.digest is not None and m.digest != digest:
        issues.append(Issue(ERROR, "mapping.digest_mismatch", str(path), f"declared digest {m.digest} does not match content {digest}"))

    loaded_story = stories.get(m.story)
    if loaded_story is None:
        issues.append(Issue(ERROR, "mapping.dangling_ref", str(path), f"mapping refers to unknown or invalid story {m.story!r}"))
    elif m.story_digest is None:
        issues.append(Issue(WARNING, "mapping.unpinned", str(path), f"mapping is not pinned to a story digest (current: {loaded_story.digest}); a story edit will not be flagged as needing re-review"))
    elif m.story_digest != loaded_story.digest:
        issues.append(Issue(ERROR, "mapping.story_changed", str(path), f"mapping was written for story digest {m.story_digest} but the story is now {loaded_story.digest}; re-review the mapping and update story_digest"))

    entry_digests: Dict[str, str] = {}
    seen_ids = set()
    unit_ids = set(loaded_story.story.unit_ids()) if loaded_story and loaded_story.story else set()
    for i, e in enumerate(m.entries):
        where = f"{m.story}/{e.id}"
        if e.id in seen_ids:
            issues.append(Issue(ERROR, "mapping.duplicate_id", where, f"entry id {e.id!r} duplicated"))
        seen_ids.add(e.id)
        _check_entry(e, where, issues)
        for c in e.covers:
            story_part, dot, unit = c.partition(".")
            if not dot or not unit:
                issues.append(Issue(ERROR, "mapping.covers_unqualified", where, f"covers {c!r} must be a qualified id like {m.story}.STEP-01"))
            elif story_part != m.story:
                issues.append(Issue(ERROR, "mapping.covers_cross_story", where, f"covers {c!r} is outside mapping story {m.story!r}; cross-story coverage is not supported in B1a, use a separate mapping file"))
            elif loaded_story and loaded_story.story and unit not in unit_ids:
                issues.append(Issue(ERROR, "mapping.dangling_ref", where, f"covers {c!r}: story has no step/branch {unit!r}"))
        entry_digests[e.id] = content_digest({"story": m.story, "entry": e.model_dump(mode="json")})
    return LoadedMapping(path, m, digest, entry_digests, issues)


def load_mappings(paths: List[Path], stories: StorySet) -> List[LoadedMapping]:
    return [load_mapping_file(f, stories) for f in collect_yaml_files(paths)]
