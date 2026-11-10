"""把插件 JSON 报告 + JUnit XML 归类为 FlowTree 的尝试状态与逐测试结果 (纯函数, 不启动进程)。

任何无法解释的矛盾都归为 ERROR, 不会因为"退出码 0"或"至少一个测试通过"而判通过。
"""
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .status import AttemptState, TestOutcome as O

REPORT_SCHEMA = 1


@dataclass
class Classification:
    state: AttemptState
    reason: Optional[str]
    outcomes: Dict[str, O] = field(default_factory=dict)          # 仅映射声明的 nodeid
    details: Dict[str, dict] = field(default_factory=dict)         # nodeid -> {outcome, reason, phases}
    counts: Dict[str, int] = field(default_factory=dict)           # 所有已收集项的分类计数
    junit: Dict[str, int] = field(default_factory=dict)
    # 未被映射声明、但本次命令已报告的失败/错误/XPASS: 不属于任何场景的判定, 但属于这条命令, 不得丢弃
    unmapped_nonpass: Dict[str, str] = field(default_factory=dict)


def derive_outcome(phases: dict, xfail_marker: bool) -> Tuple[O, str]:
    setup, call, td = phases.get("setup"), phases.get("call"), phases.get("teardown")
    if not setup:
        return O.MISSING, "setup never ran"
    if setup["outcome"] == "failed":
        return O.ERROR, "setup failed"
    if setup["outcome"] == "skipped":
        return (O.XFAILED, "xfail at setup") if setup.get("wasxfail") is not None else (O.SKIPPED, "skipped at setup")
    if not call:
        return O.MISSING, "call phase missing (interrupted?)"
    if call["outcome"] == "skipped":
        base, why = (O.XFAILED, "xfail") if call.get("wasxfail") is not None else (O.SKIPPED, "skipped")
    elif call["outcome"] == "passed":
        base, why = (O.XPASSED, "xpass (non-strict)") if call.get("wasxfail") is not None else (O.PASSED, "passed")
    elif call["outcome"] == "failed":
        if xfail_marker and str(call.get("longrepr_head", "")).startswith("[XPASS(strict)]"):
            base, why = O.XPASSED, "xpass (strict)"
        else:
            base, why = O.FAILED, "assertion/exception in call"
    else:
        return O.ERROR, f"unknown call outcome {call['outcome']!r}"
    if not td:
        return O.MISSING, "teardown phase missing (interrupted?)"
    if td["outcome"] != "passed":
        if base == O.FAILED:
            return O.FAILED, why + "; teardown also " + td["outcome"]
        return O.ERROR, f"teardown {td['outcome']} after {why}"
    return base, why


def parse_junit(path: str) -> Tuple[Optional[Dict[Tuple[str, str], str]], Optional[str]]:
    """返回 {(classname, name): passed|skipped|bad}。同一键多条记录 (如 call 失败 + teardown 错误) 取最差。"""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        return None, f"junit unreadable: {e}"
    out: Dict[Tuple[str, str], str] = {}
    rank = {"passed": 0, "skipped": 1, "bad": 2}
    for tc in root.iter("testcase"):
        key = (tc.get("classname", ""), tc.get("name", ""))
        if tc.find("failure") is not None or tc.find("error") is not None:
            st = "bad"
        elif tc.find("skipped") is not None:
            st = "skipped"
        else:
            st = "passed"
        if key not in out or rank[st] > rank[out[key]]:
            out[key] = st
    return out, None


_JUNIT_COMPAT = {
    O.PASSED: {"passed"},
    O.XPASSED: {"passed", "bad"},        # 非 strict 记为 passed; strict 记为 failure
    O.FAILED: {"bad"},
    O.ERROR: {"bad"},
    O.SKIPPED: {"skipped"},
    O.XFAILED: {"skipped"},
}


def classify(
    report: Optional[dict],
    junit: Optional[Dict[Tuple[str, str], str]],
    junit_error: Optional[str],
    *,
    run_id: str,
    attempt_id: str,
    cwd: str,
    returncode: int,
    required_nodeids: List[str],
) -> Classification:
    def err(reason, **kw):
        return Classification(AttemptState.ERROR, reason, **kw)

    if report is None:
        return err("plugin report missing or unreadable (plugin not loaded, or session killed before it started)")
    if report.get("schema") != REPORT_SCHEMA:
        return err(f"unsupported plugin report schema {report.get('schema')!r}")
    if report.get("run_id") != run_id or report.get("attempt_id") != attempt_id:
        return err("plugin report belongs to a different run/attempt (stale or reused file)")
    if not report.get("terminal"):
        return err("plugin report has no terminal record (session did not finish)")
    if report.get("exitstatus") != returncode:
        return err(f"exit code contradiction: process exited {returncode}, report says {report.get('exitstatus')}")
    if os.path.realpath(report.get("rootdir", "")) != os.path.realpath(cwd):
        return err(f"pytest rootdir {report.get('rootdir')!r} differs from mapping cwd {cwd!r}; mapping nodeids are relative to rootdir, so they cannot be matched reliably (add --rootdir=. or adjust cwd)")
    if report.get("scope_altering_options"):
        return err(f"scope-altering pytest options are active: {report['scope_altering_options']}")
    if report.get("collect_errors"):
        return err(f"{len(report['collect_errors'])} collection error(s): {report['collect_errors'][0]['nodeid']}")
    if returncode not in (0, 1):
        return err(f"pytest exit status {returncode} (0=all passed, 1=test failures are the only completed states)")

    collected = report.get("collected", [])
    ids = [c["nodeid"] for c in collected]
    if len(ids) != len(set(ids)):
        return err("duplicate nodeids in collected set")
    if not ids:
        return err("no tests were collected")
    if junit is None:
        return err(junit_error or "junit report missing")

    outcomes_all: Dict[str, O] = {}
    reasons: Dict[str, str] = {}
    for c in collected:
        o, why = derive_outcome(report.get("items", {}).get(c["nodeid"], {}), bool(c.get("xfail_marker")))
        outcomes_all[c["nodeid"]] = o
        reasons[c["nodeid"]] = why
    if any(o == O.MISSING for o in outcomes_all.values()):
        bad = next(n for n, o in outcomes_all.items() if o == O.MISSING)
        return err(f"incomplete session: {bad}: {reasons[bad]}")

    # JUnit 交叉校验: 逐项比较, 而不是比较总数
    expected_keys = {}
    for c in collected:
        k = c.get("junit")
        if not k:
            return err(f"cannot derive junit key for {c['nodeid']}; cross-check impossible")
        expected_keys[(k["classname"], k["name"])] = c["nodeid"]
    extra = set(junit) - set(expected_keys)
    if extra:
        return err(f"junit contains testcases unknown to the plugin report: {sorted(extra)[:3]}")
    for key, nid in expected_keys.items():
        if key not in junit:
            return err(f"junit has no testcase for {nid}")
        if junit[key] not in _JUNIT_COMPAT[outcomes_all[nid]]:
            return err(f"report/junit disagree for {nid}: plugin={outcomes_all[nid].value} junit={junit[key]}")

    deselected = set(report.get("deselected", []))
    outcomes: Dict[str, O] = {}
    details: Dict[str, dict] = {}
    for nid in required_nodeids:
        if nid in outcomes_all:
            outcomes[nid] = outcomes_all[nid]
            details[nid] = {"outcome": outcomes_all[nid].value, "reason": reasons[nid], "phases": report["items"].get(nid, {})}
        else:
            outcomes[nid] = O.MISSING
            details[nid] = {"outcome": "missing", "reason": "deselected" if nid in deselected else "not collected in this run"}
    unmapped = {n: o.value for n, o in outcomes_all.items()
                if n not in set(required_nodeids) and o in (O.FAILED, O.ERROR, O.XPASSED)}
    counts: Dict[str, int] = {}
    for o in outcomes_all.values():
        counts[o.value] = counts.get(o.value, 0) + 1
    jc = {"passed": 0, "skipped": 0, "bad": 0}
    for v in junit.values():
        jc[v] += 1
    return Classification(AttemptState.COMPLETED, None, outcomes, details, counts, jc, unmapped)
