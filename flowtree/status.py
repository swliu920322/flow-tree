"""领域状态与聚合规则。四个维度分开保存, 不合并成单一灯色或百分比:

  rule(规则定义) / implementation(实现检查) / automation(自动验证) / human(人工验收)

自动验证的聚合分两步, 顺序不能颠倒:
  1. 有效性: 证据是否适用于当前基线 (current / stale / unknown)。stale/unknown 不是一种"低优先级失败",
     它只决定该证据能不能作为"本次结果"; 历史通过/失败仍保留 (last_known), 但不冒充当前结果。
  2. 结果: 只对有效 (current) 证据按固定优先级合并。
"""
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .mapping import LoadedMapping
from .story import LoadedStory


class Rule(str, Enum):
    DRAFT = "draft"      # 故事已定义, 尚无人工确认记录 (B1a 不提供确认记录, 因此不会出现 confirmed)
    PENDING = "pending"  # 被 open_question 阻塞


class Implementation(str, Enum):
    UNCHECKED = "unchecked"  # B1a 无实现检查来源, 恒为 unchecked


class Human(str, Enum):
    NONE = "none"      # 未验收
    PASS = "pass"
    REJECT = "reject"
    NA = "na"


class Auto(str, Enum):
    UNMAPPED = "unmapped"  # 没有任何映射条目覆盖
    NOT_RUN = "not_run"    # 已映射, 但无适用于当前基线的执行结果 / 测试被跳过
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"      # 真实测试断言失败 (含已登记的 xfail 缺陷)
    BLOCKED = "blocked"    # 已知环境前置缺失, 未能执行
    ERROR = "error"        # 执行/收集/解析故障、测试标识未知、XPASS 等无法据以判定通过


class Validity(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class AttemptState(str, Enum):
    RUNNING = "running"      # 已写开始记录, 尚无终态 (中断后遗留同样呈现此态, 由 evidence 层判定为 aborted)
    COMPLETED = "completed"  # 子进程正常结束且报告可解析
    BLOCKED = "blocked"
    ERROR = "error"
    ABORTED = "aborted"      # 中断 / 无终态记录


class TestOutcome(str, Enum):
    __test__ = False  # 避免被 pytest 当作测试类收集
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    XFAILED = "xfailed"
    XPASSED = "xpassed"
    MISSING = "missing"  # 报告中不存在该 nodeid


_OUTCOME_TO_AUTO = {
    TestOutcome.PASSED: Auto.PASSED,
    TestOutcome.FAILED: Auto.FAILED,
    TestOutcome.XFAILED: Auto.FAILED,   # 登记的已知缺陷: 预期行为未交付, 不是完成
    TestOutcome.ERROR: Auto.ERROR,
    TestOutcome.SKIPPED: Auto.NOT_RUN,  # 未实际执行断言
    TestOutcome.XPASSED: Auto.ERROR,    # 已登记缺陷意外通过: 标记需复核, 不据此判通过
    TestOutcome.MISSING: Auto.ERROR,    # 映射声明了但没有执行证据 / 标识未知
}

# 合并优先级 (越靠前越优先展示); 只有全部显式为 PASSED 才得 PASSED, 任何非通过值都不会被吞掉
_PRIORITY = [Auto.FAILED, Auto.ERROR, Auto.BLOCKED, Auto.RUNNING, Auto.NOT_RUN, Auto.UNMAPPED]


def combine(statuses: List[Auto]) -> Auto:
    """合并多个有效结果。空集合没有依据, 不能得到 PASSED。"""
    if not statuses:
        raise ValueError("cannot combine an empty result set; absence of results is not a pass")
    for s in _PRIORITY:
        if s in statuses:
            return s
    if all(s == Auto.PASSED for s in statuses):
        return Auto.PASSED
    raise ValueError(f"unhandled automation status in {statuses!r}")


@dataclass(frozen=True)
class Baseline:
    """执行证据所绑定的基线。worktree_fingerprint 由已跟踪与未跟踪(非忽略)文件的内容计算,
    与提交 SHA 无关; git_sha 仅作溯源。任一方指纹为 None 表示无法确认, 有效性为 unknown。"""
    story_digest: str
    entry_digest: str
    env_id: str
    worktree_fingerprint: Optional[str]
    git_sha: Optional[str] = None
    mapping_digest: Optional[str] = None  # 溯源; 不参与有效性 (映射中其他条目变动不应使本条目失效)
    # 被测解释器及其已安装依赖的摘要 (忽略的 .venv 不在工作区指纹内, 必须单独追溯); None=无法确认
    runtime_digest: Optional[str] = None
    # 验证器版本 (FlowTree 执行/解析逻辑与插件); None=无法确认
    verifier: Optional[str] = None
    # 传给被测进程的环境配置摘要 (名称+值的 HMAC, 不含明文); env.id 只是标签, 不能代替配置一致性
    env_digest: Optional[str] = None
    # 执行上下文策略摘要 (仅 pinned 模式非空; None = inherit/旧证据, 是合法取值而非"未知")。换模式或改策略即失效
    context_digest: Optional[str] = None


def evaluate_validity(evidence: Baseline, current: Baseline) -> Tuple[Validity, List[str]]:
    stale: List[str] = []
    if evidence.story_digest != current.story_digest:
        stale.append("story content changed")
    if evidence.entry_digest != current.entry_digest:
        stale.append("mapping entry changed")
    if evidence.env_id != current.env_id:
        stale.append("environment id differs")
    unknown: List[str] = []
    for label, a, b in (
        ("worktree content", evidence.worktree_fingerprint, current.worktree_fingerprint),
        ("runtime environment", evidence.runtime_digest, current.runtime_digest),
        ("verifier version", evidence.verifier, current.verifier),
        ("environment configuration", evidence.env_digest, current.env_digest),
    ):
        if a is None or b is None:
            unknown.append(f"{label} cannot be determined")
        elif a != b:
            stale.append(f"{label} changed")
    if evidence.context_digest != current.context_digest:   # None 是合法取值 (inherit/旧证据), 不同即失效
        stale.append("execution context policy changed")
    if stale:
        return Validity.STALE, stale
    if unknown:
        return Validity.UNKNOWN, unknown
    return Validity.CURRENT, []


def compare_aspects(evidence: Baseline, current: Baseline) -> Dict[str, str]:
    """逐维度比较 (same / changed / unknown), 供界面分别说明哪一方面不一致。与 evaluate_validity 使用同一组字段。"""
    out: Dict[str, str] = {}
    for label, a, b in (
        ("story", evidence.story_digest, current.story_digest),
        ("mapping_entry", evidence.entry_digest, current.entry_digest),
        ("env_id", evidence.env_id, current.env_id),
        ("worktree", evidence.worktree_fingerprint, current.worktree_fingerprint),
        ("runtime", evidence.runtime_digest, current.runtime_digest),
        ("verifier", evidence.verifier, current.verifier),
        ("environment", evidence.env_digest, current.env_digest),
    ):
        out[label] = "unknown" if a is None or b is None else ("same" if a == b else "changed")
    out["context"] = "same" if evidence.context_digest == current.context_digest else "changed"
    return out


@dataclass
class EntryEvidence:
    entry_id: str
    state: AttemptState
    baseline: Baseline
    tests: Dict[str, TestOutcome] = field(default_factory=dict)  # nodeid -> outcome
    run_id: Optional[str] = None
    # 记录本身损坏/不一致 (manifest 缺失或不可读、索引不符、产物被改): 无法判定任何事实, 按 error 呈现, 不看基线
    corrupt: bool = False
    exit_code: Optional[int] = None                # 整条 pytest 命令的退出码
    command_nonpass: Dict[str, str] = field(default_factory=dict)  # 未被映射、但本次命令已报告失败的测试
    env_vars: Dict[str, str] = field(default_factory=dict)         # 环境变量名 -> HMAC (仅用于指出哪些变量变了)


def entry_result(required_nodeids: List[str], ev: EntryEvidence) -> Auto:
    """单个映射条目的结果。required_nodeids 来自映射声明, 报告中多出的测试不计入。"""
    if not required_nodeids:
        return Auto.ERROR  # 映射校验保证非空; 防御: 没有声明的测试不能产生通过
    if ev.state == AttemptState.RUNNING:
        return Auto.RUNNING
    if ev.state == AttemptState.BLOCKED:
        return Auto.BLOCKED
    if ev.state in (AttemptState.ERROR, AttemptState.ABORTED):
        return Auto.ERROR
    return combine([_OUTCOME_TO_AUTO[ev.tests.get(n, TestOutcome.MISSING)] for n in required_nodeids])


@dataclass
class EntryView:
    entry_id: str
    validity: Optional[Validity]       # None: 从未执行
    validity_reasons: List[str]
    result: Optional[Auto]             # 证据自身结论 (无论是否适用于当前基线)
    contributes_current: Optional[Auto]  # 只有 validity==current 时才有值
    run_id: Optional[str]


@dataclass
class UnitView:
    unit_id: str            # 限定 ID
    rule: Rule
    blocked_by: List[str]
    implementation: Implementation
    automation: Auto        # 本次(当前基线)结果
    entries: List[EntryView]
    human: Human = Human.NONE


def compute_units(
    story: LoadedStory,
    mappings: List[LoadedMapping],
    evidence: Dict[Tuple[str, str], EntryEvidence],
    current_baselines: Dict[Tuple[str, str], Baseline],
    human: Optional[Dict[str, Human]] = None,
) -> List[UnitView]:
    """evidence / current_baselines 以 (story_id, entry_id) 为键; 缺失表示从未执行 / 无法计算当前基线。"""
    s = story.story
    assert s is not None
    human = human or {}
    blocked = s.blocked_by_questions()

    by_unit: Dict[str, List[Tuple[str, List[str]]]] = {}
    for lm in mappings:
        if lm.mapping is None or lm.mapping.story != s.id:
            continue
        for e in lm.mapping.entries:
            for c in e.covers:
                by_unit.setdefault(c.partition(".")[2], []).append((e.id, [t.nodeid for t in e.tests]))

    views: List[UnitView] = []
    for uid in s.unit_ids():
        qid = s.qualified(uid)
        entries: List[EntryView] = []
        currents: List[Auto] = []
        for entry_id, nodeids in by_unit.get(uid, []):
            key = (s.id, entry_id)
            ev = evidence.get(key)
            if ev is None:
                entries.append(EntryView(entry_id, None, [], None, None, None))
                currents.append(Auto.NOT_RUN)
                continue
            if ev.corrupt:
                entries.append(EntryView(entry_id, Validity.UNKNOWN, ["evidence record is corrupt or inconsistent"],
                                         Auto.ERROR, Auto.ERROR, ev.run_id))
                currents.append(Auto.ERROR)
                continue
            result = entry_result(nodeids, ev)
            cur_base = current_baselines.get(key)
            if cur_base is None:
                validity, reasons = Validity.UNKNOWN, ["current baseline unavailable"]
            else:
                eb = ev.baseline
                if (ev.state in (AttemptState.BLOCKED, AttemptState.ERROR, AttemptState.ABORTED)
                        and eb.runtime_digest is None and cur_base.runtime_digest is None):
                    # 未能运行的尝试描述的就是"拿不到运行时": 双方都拿不到视为一致, 否则 blocked/error 会被显示成 not_run
                    eb = replace(eb, runtime_digest="<unavailable>")
                    cur_base = replace(cur_base, runtime_digest="<unavailable>")
                validity, reasons = evaluate_validity(eb, cur_base)
            if validity == Validity.CURRENT:
                entries.append(EntryView(entry_id, validity, reasons, result, result, ev.run_id))
                currents.append(result)
            else:
                # 历史结果保留在 result 里, 但不计入本次
                entries.append(EntryView(entry_id, validity, reasons, result, None, ev.run_id))
                currents.append(Auto.NOT_RUN)
        automation = Auto.UNMAPPED if not entries else combine(currents)
        views.append(UnitView(
            unit_id=qid,
            rule=Rule.PENDING if uid in blocked else Rule.DRAFT,
            blocked_by=blocked.get(uid, []),
            implementation=Implementation.UNCHECKED,
            automation=automation,
            entries=entries,
            human=human.get(qid, Human.NONE),
        ))
    return views


def summarize(views: List[UnitView]) -> Dict:
    """汇总只给分母与分类计数, 不给单一百分比。complete 要求同时满足: 全部单元自动验证本次通过、
    规则不再 pending、人工验收 pass/na。B1a 没有规则确认记录, 因此 complete 恒为 False 且 reasons 如实说明。"""
    total = len(views)
    auto = {a.value: 0 for a in Auto}
    for v in views:
        auto[v.automation.value] += 1
    stale_or_unknown = sum(
        1 for v in views if any(e.validity in (Validity.STALE, Validity.UNKNOWN) for e in v.entries)
    )
    rule_pending = sum(1 for v in views if v.rule == Rule.PENDING)
    human_unverified = sum(1 for v in views if v.human == Human.NONE)
    reasons: List[str] = []
    if total == 0:
        reasons.append("no units defined")
    if auto["passed"] != total:
        reasons.append(f"{total - auto['passed']} of {total} units lack a current passing automated result")
    if rule_pending:
        reasons.append(f"{rule_pending} units blocked by open questions")
    if any(v.rule != Rule.PENDING for v in views):
        reasons.append("rule confirmation records are not supported yet; rules remain draft")
    if human_unverified:
        reasons.append(f"{human_unverified} units without human acceptance")
    return {
        "units_total": total,
        "automation": auto,
        "units_with_stale_or_unknown_evidence": stale_or_unknown,
        "rule_pending": rule_pending,
        "human_unverified": human_unverified,
        "complete": False if reasons else True,
        "incomplete_reasons": reasons,
    }
