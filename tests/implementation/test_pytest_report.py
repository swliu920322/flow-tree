import copy

import pytest

from flowtree.pytest_report import classify, derive_outcome
from flowtree.status import AttemptState, AttemptState as S, Baseline, EntryEvidence, Auto, TestOutcome as O, compute_units

NID = "tests/t.py::test_a"
KEY = ("tests.t", "test_a")
PH_OK = {"setup": {"outcome": "passed"}, "call": {"outcome": "passed"}, "teardown": {"outcome": "passed"}}


def report(**over):
    r = {
        "schema": 1, "run_id": "r1", "attempt_id": "r1.M", "rootdir": "/proj", "terminal": True, "exitstatus": 0,
        "scope_altering_options": {}, "collect_errors": [], "deselected": [],
        "collected": [{"nodeid": NID, "junit": {"classname": "tests.t", "name": "test_a"}, "xfail_marker": False}],
        "items": {NID: copy.deepcopy(PH_OK)},
    }
    r.update(over)
    return r


def run(rep, junit=None, jerr=None, **kw):
    args = dict(run_id="r1", attempt_id="r1.M", cwd="/proj", returncode=0, required_nodeids=[NID])
    args.update(kw)
    return classify(rep, {KEY: "passed"} if junit is None else junit, jerr, **args)


def test_clean_pass():
    c = run(report())
    assert c.state == S.COMPLETED and c.outcomes[NID] == O.PASSED and c.counts == {"passed": 1}


@pytest.mark.parametrize("rep,why", [
    (None, "missing"),
    (report(schema=2), "schema"),
    (report(run_id="old-run"), "different run"),
    (report(attempt_id="other.M"), "different run"),
    (report(terminal=False), "terminal"),
    (report(exitstatus=1), "contradiction"),
    (report(rootdir="/elsewhere"), "rootdir"),
    (report(scope_altering_options={"keyword": "x"}), "scope-altering"),
    (report(collect_errors=[{"nodeid": "tests/t.py", "longrepr": "boom"}]), "collection"),
    (report(collected=[]), "no tests"),
])
def test_untrustworthy_reports_are_errors(rep, why):
    c = run(rep)
    assert c.state == S.ERROR and why in c.reason, c.reason


def test_replayed_report_for_old_run_cannot_pass_new_attempt():
    old = report()
    c = classify(old, {KEY: "passed"}, None, run_id="r2", attempt_id="r2.M", cwd="/proj", returncode=0, required_nodeids=[NID])
    assert c.state == S.ERROR


@pytest.mark.parametrize("rc", [2, 3, 4, 5])
def test_non_01_pytest_exit_status_is_error(rc):
    c = run(report(exitstatus=rc), returncode=rc)
    assert c.state == S.ERROR


def test_exit_1_with_failures_is_completed_with_failed_outcome():
    ph = copy.deepcopy(PH_OK); ph["call"] = {"outcome": "failed", "longrepr_head": "assert 1 == 2"}
    c = run(report(exitstatus=1, items={NID: ph}), junit={KEY: "bad"}, returncode=1)
    assert c.state == S.COMPLETED and c.outcomes[NID] == O.FAILED


def test_duplicate_nodeids_in_collected_set():
    rep = report()
    rep["collected"].append(rep["collected"][0])
    assert "duplicate" in run(rep).reason


def test_junit_missing_or_unreadable():
    c = classify(report(), None, "junit unreadable: x", run_id="r1", attempt_id="r1.M", cwd="/proj", returncode=0, required_nodeids=[NID])
    assert c.state == S.ERROR and "junit" in c.reason


@pytest.mark.parametrize("junit,why", [
    ({KEY: "bad"}, "disagree"),                                  # 插件说 passed, JUnit 说失败
    ({KEY: "passed", ("x", "extra"): "passed"}, "unknown"),        # JUnit 多出未知用例
    ({}, "no testcase"),                                          # JUnit 缺该用例
])
def test_report_junit_contradictions_are_errors(junit, why):
    c = run(report(), junit=junit)
    assert c.state == S.ERROR and why in c.reason, c.reason


def test_plugin_failure_but_junit_pass_is_contradiction():
    ph = copy.deepcopy(PH_OK); ph["call"] = {"outcome": "failed", "longrepr_head": "x"}
    c = run(report(exitstatus=1, items={NID: ph}), junit={KEY: "passed"}, returncode=1)
    assert c.state == S.ERROR and "disagree" in c.reason


def test_incomplete_session_missing_teardown_is_error():
    ph = {"setup": {"outcome": "passed"}, "call": {"outcome": "passed"}}
    c = run(report(items={NID: ph}))
    assert c.state == S.ERROR and "incomplete" in c.reason


def test_required_nodeid_missing_or_deselected_is_missing_outcome_not_pass():
    c = run(report(), required_nodeids=["tests/t.py::test_other"])
    assert c.state == S.COMPLETED and c.outcomes["tests/t.py::test_other"] == O.MISSING
    c = run(report(deselected=["tests/t.py::test_other"]), required_nodeids=["tests/t.py::test_other"])
    assert c.details["tests/t.py::test_other"]["reason"] == "deselected"


@pytest.mark.parametrize("phases,xfail,expected", [
    (PH_OK, False, O.PASSED),
    ({"setup": {"outcome": "failed"}}, False, O.ERROR),
    ({"setup": {"outcome": "skipped"}}, False, O.SKIPPED),
    ({"setup": {"outcome": "skipped", "wasxfail": "r"}}, True, O.XFAILED),
    ({**PH_OK, "call": {"outcome": "skipped", "wasxfail": "r"}}, True, O.XFAILED),
    ({**PH_OK, "call": {"outcome": "passed", "wasxfail": "r"}}, True, O.XPASSED),
    ({**PH_OK, "call": {"outcome": "failed", "longrepr_head": "[XPASS(strict)] "}}, True, O.XPASSED),
    ({**PH_OK, "call": {"outcome": "failed", "longrepr_head": "[XPASS(strict)] "}}, False, O.FAILED),  # 无 xfail 标记不能冒充 XPASS
    ({**PH_OK, "call": {"outcome": "failed", "longrepr_head": "assert"}}, True, O.FAILED),
    ({**PH_OK, "teardown": {"outcome": "failed"}}, False, O.ERROR),
    ({**PH_OK, "call": {"outcome": "failed", "longrepr_head": "a"}, "teardown": {"outcome": "failed"}}, False, O.FAILED),
    ({"setup": {"outcome": "passed"}}, False, O.MISSING),
    ({}, False, O.MISSING),
])
def test_derive_outcome(phases, xfail, expected):
    assert derive_outcome(phases, xfail)[0] == expected


@pytest.fixture
def sav(tmp_path):
    import shutil
    from impl_support import FIXTURES
    from flowtree.mapping import load_mapping_file
    from flowtree.story import load_stories
    d = tmp_path / "s"; d.mkdir()
    shutil.copy(FIXTURES / "sav-001.story.yaml", d)
    st = load_stories([d])
    return st.stories["SAV-001"], [load_mapping_file(FIXTURES / "sav-001.mapping.yaml", st)]


@pytest.mark.parametrize("state,expected", [(S.BLOCKED, Auto.BLOCKED), (S.ERROR, Auto.ERROR), (S.ABORTED, Auto.ERROR)])
def test_unrunnable_attempts_stay_visible_when_runtime_unavailable_on_both_sides(sav, state, expected):
    story, mappings = sav
    b = Baseline("d", "e", "env", "fp", runtime_digest=None, verifier="v", env_digest="ed")
    key = ("SAV-001", "M-01")
    u = {v.unit_id: v for v in compute_units(story, mappings, {key: EntryEvidence("M-01", state, b, {})}, {key: b})}
    assert u["SAV-001.CASE-01"].automation == expected


def test_completed_attempt_with_unavailable_runtime_is_still_unknown(sav):
    story, mappings = sav
    b = Baseline("d", "e", "env", "fp", runtime_digest=None, verifier="v", env_digest="ed")
    key = ("SAV-001", "M-01")
    ev = EntryEvidence("M-01", S.COMPLETED, b, {"tests/test_savings.py::test_zero_amount_rejected": O.PASSED})
    u = {v.unit_id: v for v in compute_units(story, mappings, {key: ev}, {key: b})}
    assert u["SAV-001.CASE-01"].automation == Auto.NOT_RUN       # 通过结果必须有可确认的运行时
    assert u["SAV-001.CASE-01"].entries[0].validity.value == "unknown"
