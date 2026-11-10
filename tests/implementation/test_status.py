import pytest

from impl_support import FIXTURES
from flowtree.mapping import load_mapping_file
from flowtree.status import (
    Auto, AttemptState, Baseline, EntryEvidence, Human, Rule, TestOutcome as O, Validity,
    combine, compute_units, entry_result, evaluate_validity, summarize,
)
from flowtree.story import load_stories

import shutil

NID_A = "tests/test_savings.py::test_zero_amount_rejected"
NID_B = "tests/test_savings.py::test_resume_after_lost_response"


def bl(**kw):
    d = dict(story_digest="s1", entry_digest="e1", env_id="env", worktree_fingerprint="fp1", git_sha="abc",
             runtime_digest="rt1", verifier="v1", env_digest="ed1")
    d.update(kw)
    return Baseline(**d)


def ev(entry_id, tests, state=AttemptState.COMPLETED, baseline=None, run_id="r1"):
    return EntryEvidence(entry_id, state, baseline or bl(), tests, run_id)


# ---------- 单条目结果 ----------

@pytest.mark.parametrize("outcome,expected", [
    (O.PASSED, Auto.PASSED), (O.FAILED, Auto.FAILED), (O.ERROR, Auto.ERROR),
    (O.SKIPPED, Auto.NOT_RUN), (O.XFAILED, Auto.FAILED), (O.XPASSED, Auto.ERROR), (O.MISSING, Auto.ERROR),
])
def test_single_outcome_mapping(outcome, expected):
    assert entry_result([NID_A], ev("M", {NID_A: outcome})) == expected


def test_unknown_nodeid_is_error_not_pass():
    assert entry_result([NID_A], ev("M", {"other::t": O.PASSED})) == Auto.ERROR


def test_one_passing_instance_of_two_required_does_not_pass():
    assert entry_result([NID_A, NID_B], ev("M", {NID_A: O.PASSED})) == Auto.ERROR


def test_zero_tests_completed_is_not_pass():
    assert entry_result([NID_A], ev("M", {})) == Auto.ERROR


def test_empty_required_list_never_passes():
    assert entry_result([], ev("M", {NID_A: O.PASSED})) == Auto.ERROR
    with pytest.raises(ValueError):
        combine([])


@pytest.mark.parametrize("state,expected", [
    (AttemptState.RUNNING, Auto.RUNNING), (AttemptState.BLOCKED, Auto.BLOCKED),
    (AttemptState.ERROR, Auto.ERROR), (AttemptState.ABORTED, Auto.ERROR),
])
def test_non_completed_attempt_states(state, expected):
    # 即使 tests 里有 passed, 非 completed 的尝试也不能判通过
    assert entry_result([NID_A], ev("M", {NID_A: O.PASSED}, state=state)) == expected


def test_combine_priority():
    assert combine([Auto.PASSED, Auto.NOT_RUN]) == Auto.NOT_RUN
    assert combine([Auto.PASSED, Auto.FAILED, Auto.ERROR]) == Auto.FAILED
    assert combine([Auto.ERROR, Auto.BLOCKED]) == Auto.ERROR
    assert combine([Auto.PASSED, Auto.PASSED]) == Auto.PASSED


# ---------- 有效性 ----------

def test_validity_current():
    assert evaluate_validity(bl(), bl()) == (Validity.CURRENT, [])


@pytest.mark.parametrize("field,value,reason", [
    ("story_digest", "s2", "story"), ("entry_digest", "e2", "entry"),
    ("env_id", "other", "environment"), ("worktree_fingerprint", "fp2", "worktree"),
    ("runtime_digest", "rt2", "runtime"), ("verifier", "v2", "verifier"), ("env_digest", "ed2", "environment configuration"),
])
def test_validity_stale_reasons(field, value, reason):
    v, reasons = evaluate_validity(bl(), bl(**{field: value}))
    assert v == Validity.STALE and any(reason in r for r in reasons)


def test_git_sha_alone_does_not_invalidate_when_content_identical():
    assert evaluate_validity(bl(git_sha="a"), bl(git_sha="b"))[0] == Validity.CURRENT


def test_unknown_fingerprint_gives_unknown_not_current():
    assert evaluate_validity(bl(worktree_fingerprint=None), bl())[0] == Validity.UNKNOWN
    assert evaluate_validity(bl(), bl(worktree_fingerprint=None))[0] == Validity.UNKNOWN


@pytest.mark.parametrize("field", ["runtime_digest", "verifier", "env_digest"])
def test_unknown_runtime_or_verifier_is_unknown_not_current(field):
    assert evaluate_validity(bl(**{field: None}), bl())[0] == Validity.UNKNOWN
    assert evaluate_validity(bl(), bl(**{field: None}))[0] == Validity.UNKNOWN


def test_definite_stale_wins_over_unknown():
    assert evaluate_validity(bl(worktree_fingerprint=None), bl(story_digest="s2"))[0] == Validity.STALE


# ---------- 单元/汇总 ----------

@pytest.fixture
def setup(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    shutil.copy(FIXTURES / "sav-001.story.yaml", d)
    stories = load_stories([d])
    lm = load_mapping_file(FIXTURES / "sav-001.mapping.yaml", stories)
    assert lm.issues == []
    return stories.stories["SAV-001"], [lm]


def units(setup, evidence, currents, human=None):
    story, mappings = setup
    return {u.unit_id: u for u in compute_units(story, mappings, evidence, currents, human)}


def test_no_evidence_gives_unmapped_and_not_run(setup):
    u = units(setup, {}, {})
    assert u["SAV-001.STEP-01"].automation == Auto.UNMAPPED
    assert u["SAV-001.CASE-01"].automation == Auto.NOT_RUN
    assert u["SAV-001.STEP-03"].automation == Auto.NOT_RUN


def test_current_pass_and_fail_by_entry(setup):
    key1, key2 = ("SAV-001", "M-01"), ("SAV-001", "M-02")
    evidence = {key1: ev("M-01", {NID_A: O.PASSED}), key2: ev("M-02", {NID_B: O.FAILED})}
    currents = {key1: bl(), key2: bl()}
    u = units(setup, evidence, currents)
    assert u["SAV-001.CASE-01"].automation == Auto.PASSED
    assert u["SAV-001.CASE-02"].automation == Auto.FAILED
    assert u["SAV-001.STEP-03"].automation == Auto.FAILED  # M-02 同时覆盖 STEP-03
    assert u["SAV-001.STEP-01"].automation == Auto.UNMAPPED  # 其他单元不受影响


def test_stale_pass_is_kept_as_history_but_not_current(setup):
    key = ("SAV-001", "M-01")
    evidence = {key: ev("M-01", {NID_A: O.PASSED})}
    u = units(setup, evidence, {key: bl(worktree_fingerprint="changed")})
    v = u["SAV-001.CASE-01"]
    assert v.automation == Auto.NOT_RUN
    assert v.entries[0].validity == Validity.STALE
    assert v.entries[0].result == Auto.PASSED          # 历史保留
    assert v.entries[0].contributes_current is None     # 但不计入本次


def test_stale_failure_does_not_masquerade_as_current_failure(setup):
    key = ("SAV-001", "M-01")
    u = units(setup, {key: ev("M-01", {NID_A: O.FAILED})}, {key: bl(story_digest="new")})
    assert u["SAV-001.CASE-01"].automation == Auto.NOT_RUN


def test_missing_current_baseline_is_unknown(setup):
    key = ("SAV-001", "M-01")
    u = units(setup, {key: ev("M-01", {NID_A: O.PASSED})}, {})
    assert u["SAV-001.CASE-01"].entries[0].validity == Validity.UNKNOWN
    assert u["SAV-001.CASE-01"].automation == Auto.NOT_RUN


def test_running_attempt_is_reported_running(setup):
    key = ("SAV-001", "M-01")
    u = units(setup, {key: ev("M-01", {}, state=AttemptState.RUNNING)}, {key: bl()})
    assert u["SAV-001.CASE-01"].automation == Auto.RUNNING


def test_summary_never_complete_in_b1a_even_if_all_pass(setup):
    key1, key2 = ("SAV-001", "M-01"), ("SAV-001", "M-02")
    evidence = {key1: ev("M-01", {NID_A: O.PASSED}), key2: ev("M-02", {NID_B: O.PASSED})}
    views = list(units(setup, evidence, {key1: bl(), key2: bl()}).values())
    s = summarize(views)
    assert s["units_total"] == 6 and s["automation"]["passed"] == 3
    assert s["complete"] is False
    assert any("human acceptance" in r for r in s["incomplete_reasons"])
    assert any("rule confirmation" in r for r in s["incomplete_reasons"])


def test_human_records_are_independent_of_automation(setup):
    u = units(setup, {}, {}, human={"SAV-001.STEP-01": Human.PASS})
    assert u["SAV-001.STEP-01"].human == Human.PASS
    assert u["SAV-001.STEP-01"].automation == Auto.UNMAPPED


def test_open_question_marks_rule_pending_without_hiding_automation(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    text = (FIXTURES / "sav-001.story.yaml").read_text(encoding="utf-8").replace(
        "open_questions: []",
        'open_questions:\n  - id: Q1\n    text: 上限？\n    blocks: [CASE-01]\n')
    (d / "s.yaml").write_text(text, encoding="utf-8")
    stories = load_stories([d])
    assert [i for i in stories.issues if i.severity == "error"] == []
    views = {v.unit_id: v for v in compute_units(stories.stories["SAV-001"], [], {}, {})}
    assert views["SAV-001.CASE-01"].rule == Rule.PENDING
    assert views["SAV-001.CASE-01"].blocked_by == ["Q1"]
    assert views["SAV-001.CASE-02"].rule == Rule.DRAFT
