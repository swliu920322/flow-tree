"""故事契约 (schema_version 0.1): 模型、读取与引用校验。

故事只表达业务预期; 接口/测试文件放在独立映射 (mapping.py)。
可验证单元 (unit) = 主流程步骤 (STEP) 与分支场景 (CASE), 限定 ID 形如 `SAV-001.CASE-02`。
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .canon import DIGEST_FIELD, YamlLoadError, content_digest, load_yaml_file
from .issues import ERROR, WARNING, Issue

SCHEMA_VERSION = "0.1"
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")  # 不含 "."; "." 保留为限定符
DECIMAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
ALL_UNITS = "*"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(_Strict):
    path: str
    anchor: Optional[str] = None


class Step(_Strict):
    id: str
    action: str
    expected: List[str] = Field(default_factory=list)


class Continuation(_Strict):
    type: Literal["end", "rejoin", "retry"]
    target: Optional[str] = None


class Branch(_Strict):
    id: str
    at: str
    kind: str
    condition: str
    expected: List[str] = Field(default_factory=list)
    continuation: Continuation


class OpenQuestion(_Strict):
    id: str
    text: str
    # 受影响的步骤/场景 ID (故事内非限定 ID); "*" 表示整个故事。
    blocks: List[str] = Field(min_length=1)
    legacy: bool = False  # 旧格式字符串转换而来


class Clock(_Strict):
    now: str  # 无偏移的本地时间, 如 2026-01-01T09:30:00
    tz: str   # IANA 时区名

    @model_validator(mode="after")
    def _check(self):
        try:
            tz = ZoneInfo(self.tz)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError(f"unknown timezone {self.tz!r}")
        try:
            naive = datetime.fromisoformat(self.now)
        except ValueError:
            raise ValueError(f"invalid ISO datetime {self.now!r}")
        if naive.tzinfo is not None:
            raise ValueError("clock.now must be a local time without UTC offset; zone goes in clock.tz")
        a = naive.replace(tzinfo=tz, fold=0)
        b = naive.replace(tzinfo=tz, fold=1)
        if a.utcoffset() != b.utcoffset():
            raise ValueError(f"ambiguous local time {self.now} in {self.tz} (DST overlap)")
        roundtrip = a.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
        if roundtrip != naive:
            raise ValueError(f"nonexistent local time {self.now} in {self.tz} (DST gap)")
        return self


class Story(_Strict):
    schema_version: str
    id: str
    title: str
    actor: str
    goal: str
    digest: Optional[str] = None
    sources: List[Source] = Field(default_factory=list)
    preconditions: List[str] = Field(default_factory=list)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    clock: Optional[Clock] = None
    main_flow: List[Step]
    branches: List[Branch] = Field(default_factory=list)
    invariants: List[str] = Field(default_factory=list)
    open_questions: List[OpenQuestion] = Field(default_factory=list)

    @field_validator("open_questions", mode="before")
    @classmethod
    def _legacy_questions(cls, v):
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("open_questions must be a list")
        out = []
        for i, item in enumerate(v, start=1):
            if isinstance(item, str):
                # 旧格式: 没有关联信息, 不猜测影响范围, 保守阻塞整个故事
                out.append({"id": f"OQ-LEGACY-{i:02d}", "text": item, "blocks": [ALL_UNITS], "legacy": True})
            else:
                out.append(item)
        return out

    # ----- 派生信息 -----
    def unit_ids(self) -> List[str]:
        return [s.id for s in self.main_flow] + [b.id for b in self.branches]

    def qualified(self, unit_id: str) -> str:
        return f"{self.id}.{unit_id}"

    def blocked_by_questions(self) -> Dict[str, List[str]]:
        """unit_id -> 阻塞它的 open_question id 列表; 只含被阻塞的单元。"""
        out: Dict[str, List[str]] = {}
        units = self.unit_ids()
        for q in self.open_questions:
            targets = units if ALL_UNITS in q.blocks else q.blocks
            for u in targets:
                out.setdefault(u, []).append(q.id)
        return out


@dataclass
class LoadedStory:
    path: Path
    story: Optional[Story]
    digest: Optional[str]
    issues: List[Issue] = field(default_factory=list)


def _check_input_value(key: str, value: Any, where: str, issues: List[Issue]) -> bool:
    """返回该输入是否带类型声明并已校验。无声明的输入不声称已验证类型, 也不猜测字段含义。"""
    if isinstance(value, dict) and "type" in value:
        t = value.get("type")
        extra = set(value) - {"type", "value", "max_scale"}
        if extra:
            issues.append(Issue(ERROR, "story.input_typed_fields", where, f"typed input {key!r} has unknown fields {sorted(extra)}"))
            return True
        if "value" not in value:
            issues.append(Issue(ERROR, "story.input_typed_missing_value", where, f"typed input {key!r} lacks 'value'"))
            return True
        v = value["value"]
        if t == "decimal":
            if not isinstance(v, str) or not DECIMAL_RE.match(v):
                issues.append(Issue(ERROR, "story.input_decimal", where, f"{key!r}: decimal value must be a plain decimal string like \"0.25\", got {v!r}"))
            else:
                scale = value.get("max_scale")
                if scale is not None:
                    if not isinstance(scale, int) or isinstance(scale, bool) or scale < 0:
                        issues.append(Issue(ERROR, "story.input_decimal_scale", where, f"{key!r}: max_scale must be a non-negative integer"))
                    else:
                        frac = v.split(".", 1)[1] if "." in v else ""
                        if len(frac) > scale:
                            issues.append(Issue(ERROR, "story.input_decimal_scale", where, f"{key!r}: {v} has more than {scale} decimal places"))
        elif t == "integer":
            if isinstance(v, bool) or not isinstance(v, int):
                issues.append(Issue(ERROR, "story.input_integer", where, f"{key!r}: integer value must be a YAML integer, got {v!r}"))
        elif t == "string":
            if not isinstance(v, str):
                issues.append(Issue(ERROR, "story.input_string", where, f"{key!r}: string value must be a string, got {v!r}"))
        else:
            issues.append(Issue(ERROR, "story.input_type_unknown", where, f"{key!r}: unknown input type {t!r} (supported: decimal, integer, string)"))
        return True
    if isinstance(value, float):
        issues.append(Issue(WARNING, "story.input_float_untyped", where, f"{key!r} is an unquoted float; binary floats are not exact. Declare it as type: decimal or quote it"))
    return False


def _semantic_checks(story: Story, issues: List[Issue]) -> None:
    sid = story.id
    if not ID_RE.match(sid):
        issues.append(Issue(ERROR, "story.bad_id", sid, f"story id {sid!r} must match {ID_RE.pattern}"))
    if story.schema_version != SCHEMA_VERSION:
        issues.append(Issue(ERROR, "story.schema_version", sid, f"unsupported schema_version {story.schema_version!r}; expected {SCHEMA_VERSION!r}"))
    if not story.main_flow:
        issues.append(Issue(ERROR, "story.empty_main_flow", sid, "main_flow must contain at least one step"))

    # step / 分支共用一个 ID 命名空间
    seen: Dict[str, str] = {}
    for kind, items in (("main_flow", story.main_flow), ("branches", story.branches)):
        for i, item in enumerate(items):
            where = f"{sid}.{kind}[{i}]"
            if not ID_RE.match(item.id):
                issues.append(Issue(ERROR, "story.bad_id", where, f"id {item.id!r} must match {ID_RE.pattern}"))
            if item.id in seen:
                issues.append(Issue(ERROR, "story.duplicate_id", where, f"id {item.id!r} already used in {seen[item.id]}"))
            else:
                seen[item.id] = where

    step_index = {s.id: i for i, s in enumerate(story.main_flow)}
    for s in story.main_flow:
        if not s.expected:
            issues.append(Issue(WARNING, "story.step_no_expected", f"{sid}.{s.id}", "step has no observable expected result; cannot be accepted"))
    for i, b in enumerate(story.branches):
        where = f"{sid}.{b.id}"
        if b.at not in step_index:
            issues.append(Issue(ERROR, "story.dangling_ref", where, f"branch 'at' refers to unknown step {b.at!r}"))
        if not b.expected:
            issues.append(Issue(WARNING, "story.branch_no_expected", where, "branch has no expected result"))
        c = b.continuation
        if c.type == "end":
            if c.target is not None:
                issues.append(Issue(ERROR, "story.continuation_target", where, "continuation type 'end' must not have a target"))
        elif c.type == "rejoin":
            if not c.target:
                issues.append(Issue(ERROR, "story.continuation_target", where, "continuation type 'rejoin' requires a target step"))
            elif c.target not in step_index:
                issues.append(Issue(ERROR, "story.dangling_ref", where, f"rejoin target {c.target!r} is not a main_flow step"))
            elif b.at in step_index and step_index[c.target] <= step_index[b.at]:
                issues.append(Issue(ERROR, "story.rejoin_backward", where, f"rejoin target {c.target!r} must come after {b.at!r}; returning to an earlier step is a retry, which is not supported in schema 0.1"))
        else:  # retry
            issues.append(Issue(ERROR, "story.retry_unsupported", where, "continuation type 'retry' is not supported in schema 0.1 (needs target + bounded retry policy); it is rejected rather than treated as 'end'"))

    qids = set()
    units = set(story.unit_ids())
    for i, q in enumerate(story.open_questions):
        where = f"{sid}.open_questions[{i}]"
        if q.id in qids:
            issues.append(Issue(ERROR, "story.duplicate_id", where, f"open question id {q.id!r} duplicated"))
        qids.add(q.id)
        if q.legacy:
            issues.append(Issue(WARNING, "story.open_question_legacy", where, "legacy string open question: scope unknown, conservatively blocks every scenario of this story"))
        for t in q.blocks:
            if t != ALL_UNITS and t not in units:
                issues.append(Issue(ERROR, "story.dangling_ref", where, f"blocks refers to unknown step/branch {t!r}"))

    for key, value in story.inputs.items():
        w = f"{sid}.inputs.{key}"
        _check_input_value(key, value, w, issues)


def load_story_file(path: Path) -> LoadedStory:
    path = Path(path)
    issues: List[Issue] = []
    try:
        raw = load_yaml_file(path)
    except YamlLoadError as e:
        return LoadedStory(path, None, None, [Issue(ERROR, "story.yaml", str(path), str(e))])
    if not isinstance(raw, dict):
        return LoadedStory(path, None, None, [Issue(ERROR, "story.not_mapping", str(path), "story file must be a YAML mapping")])
    try:
        digest = content_digest(raw)
    except YamlLoadError as e:
        return LoadedStory(path, None, None, [Issue(ERROR, "story.yaml", str(path), str(e))])
    try:
        story = Story.model_validate(raw)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            issues.append(Issue(ERROR, "story.schema", f"{path}:{loc}", err["msg"]))
        return LoadedStory(path, None, digest, issues)
    if story.digest is not None and story.digest != digest:
        issues.append(Issue(ERROR, "story.digest_mismatch", story.id, f"declared digest {story.digest} does not match content {digest}"))
    _semantic_checks(story, issues)
    return LoadedStory(path, story, digest, issues)


@dataclass
class StorySet:
    stories: Dict[str, LoadedStory] = field(default_factory=dict)
    issues: List[Issue] = field(default_factory=list)  # 汇总 (含每个文件的 issue 与跨文件冲突)

    def get(self, story_id: str) -> Optional[LoadedStory]:
        return self.stories.get(story_id)


def collect_yaml_files(paths: List[Path]) -> List[Path]:
    files: List[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files.extend(sorted(x for x in p.rglob("*") if x.suffix in (".yaml", ".yml") and x.is_file()))
        else:
            files.append(p)
    return files


def empty_input_issues(paths: List[Path], code: str, label: str) -> List[Issue]:
    """显式给出的输入没有发现任何 YAML 文件时报错, 避免选错路径得到"空集合有效"。"""
    out = []
    for p in paths:
        p = Path(p)
        if p.is_dir() and not collect_yaml_files([p]):
            out.append(Issue(ERROR, code, str(p), f"no .yaml/.yml {label} files found in this directory"))
    return out


def load_stories(paths: List[Path]) -> StorySet:
    result = StorySet()
    owner: Dict[str, Path] = {}
    for f in collect_yaml_files(paths):
        loaded = load_story_file(f)
        result.issues.extend(loaded.issues)
        if loaded.story is None:
            continue
        sid = loaded.story.id
        if sid in owner:
            result.issues.append(Issue(ERROR, "story.duplicate_id", str(f), f"story id {sid!r} already defined in {owner[sid]}"))
            continue
        owner[sid] = f
        result.stories[sid] = loaded
    return result
