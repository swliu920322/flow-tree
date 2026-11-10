"""Flutter 事件流解析器的单元反例 (纯函数, 不启动进程)。真实 `flutter test` 子进程测试在 test_flutter_real.py。"""
import json

import pytest

from flowtree.runners.flutter_runner import analyze, parse_events
from flowtree.status import AttemptState as S, TestOutcome as O

CWD = "/proj"
F = "/proj/test/a_test.dart"


def ev(**kw):
    return json.dumps(kw)


def stream(tests, *, success=True, extra=(), suites=None, hidden_result="success", protocol="0.1.1", done=True, count=None, load_hidden_flag=True):
    """tests: [(id, name, result, skipped)]; 生成合法事件流。"""
    suites = suites or {0: F}
    lines = [ev(protocolVersion=protocol, runnerVersion=None, pid=1, type="start", time=0)]
    for sid, path in suites.items():
        lines.append(ev(suite={"id": sid, "platform": "vm", "path": path}, type="suite", time=0))
    lines.append(ev(test={"id": 100, "name": f"loading {F}", "suiteID": 0, "groupIDs": [], "metadata": {"skip": False, "skipReason": None}}, type="testStart", time=1))
    lines.append(ev(count=len(suites) if count is None else count, type="allSuites", time=1))
    lines.append(ev(testID=100, result=hidden_result, skipped=False, hidden=load_hidden_flag or hidden_result == "success", type="testDone", time=2))
    if hidden_result != "success":
        lines.insert(-1, ev(testID=100, error="Failed to load", stackTrace="", isFailure=False, type="error", time=2))
    for tid, name, result, skipped in tests:
        lines.append(ev(test={"id": tid, "name": name, "suiteID": 0, "groupIDs": [], "metadata": {"skip": skipped, "skipReason": None}, "line": 3}, type="testStart", time=3))
        if result != "success":
            lines.append(ev(testID=tid, error=f"{name} failed", stackTrace="st", isFailure=(result == "failure"), type="error", time=4))
        lines.append(ev(testID=tid, result=result, skipped=skipped, hidden=False, type="testDone", time=5))
    lines.extend(extra)
    if done:
        lines.append(ev(success=success, type="done", time=9))
    return "\n".join(lines) + "\n"


def run(text, required=("test/a_test.dart::plain passes",), rc=0):
    return analyze(text, cwd=CWD, returncode=rc, required=list(required))


def test_clean_pass_hides_the_loading_pseudo_test_from_the_denominator():
    c, x = run(stream([(1, "plain passes", "success", False)]))
    assert c.state == S.COMPLETED and c.outcomes["test/a_test.dart::plain passes"] == O.PASSED
    assert c.counts == {"passed": 1} and x["real_test_count"] == 1 and x["hidden_events"][0]["result"] == "success"
    assert x["protocol_version"] == "0.1.1" and x["suites"] == ["test/a_test.dart"]


def test_assertion_failure_is_failed_with_raw_error_and_stack_kept_and_exception_is_error():
    c, x = run(stream([(1, "plain passes", "failure", False), (2, "boom", "error", False)], success=False), rc=1,
               required=("test/a_test.dart::plain passes", "test/a_test.dart::boom"))
    assert c.state == S.COMPLETED
    assert c.outcomes["test/a_test.dart::plain passes"] == O.FAILED and c.outcomes["test/a_test.dart::boom"] == O.ERROR
    d = c.details["test/a_test.dart::plain passes"]
    assert d["errors"][0]["error"] == "plain passes failed" and d["errors"][0]["stackTrace"] == "st" and d["errors"][0]["isFailure"] is True


def test_skipped_success_result_is_skipped_not_passed():
    c, _ = run(stream([(1, "plain passes", "success", True)]))      # testDone.result=success 但 skipped=true
    assert c.outcomes["test/a_test.dart::plain passes"] == O.SKIPPED


def test_metadata_skip_without_done_flag_is_still_skipped():
    text = stream([(1, "plain passes", "success", False)]).replace('"skip": false, "skipReason": null}, "line": 3', '"skip": true, "skipReason": "x"}, "line": 3')
    c, _ = run(text)
    assert c.outcomes["test/a_test.dart::plain passes"] == O.SKIPPED


def test_unmapped_failure_is_reported_separately():
    c, x = run(stream([(1, "plain passes", "success", False), (2, "other bug", "failure", False)], success=False), rc=1)
    assert c.state == S.COMPLETED and c.outcomes["test/a_test.dart::plain passes"] == O.PASSED
    assert c.unmapped_nonpass == {"test/a_test.dart::other bug": "failed"}


def test_name_containing_double_colon_matches_on_the_first_separator_only():
    c, _ = run(stream([(1, "G a::b c", "success", False)]), required=("test/a_test.dart::G a::b c",))
    assert c.outcomes["test/a_test.dart::G a::b c"] == O.PASSED


def test_same_name_in_two_files_is_allowed_but_same_file_duplicates_are_ambiguous_errors():
    other = "/proj/test/b_test.dart"
    base = stream([(1, "same", "success", False)], suites={0: F, 1: other})
    extra = [ev(test={"id": 7, "name": "same", "suiteID": 1, "groupIDs": [], "metadata": {"skip": False}}, type="testStart", time=6),
             ev(testID=7, result="success", skipped=False, hidden=False, type="testDone", time=7)]
    text = base.replace(ev(success=True, type="done", time=9), "\n".join(extra) + "\n" + ev(success=True, type="done", time=9))
    c, _ = run(text, required=("test/a_test.dart::same", "test/b_test.dart::same"))
    assert c.outcomes["test/a_test.dart::same"] == O.PASSED and c.outcomes["test/b_test.dart::same"] == O.PASSED
    dup = stream([(1, "same", "success", False), (2, "same", "success", False)])
    c, _ = run(dup, required=("test/a_test.dart::same",))
    assert c.state == S.COMPLETED and c.outcomes["test/a_test.dart::same"] == O.ERROR
    assert "ambiguous" in c.details["test/a_test.dart::same"]["reason"]


def test_interleaved_events_are_associated_by_id():
    base = stream([(1, "plain passes", "success", False), (2, "second", "success", False)]).splitlines()
    # 把 test 2 的 start 提到 test 1 的 done 之前, 并插入 print 事件
    i_start2 = next(i for i, l in enumerate(base) if '"id": 2' in l and "testStart" in l)
    i_done1 = next(i for i, l in enumerate(base) if '"testID": 1' in l and "testDone" in l)
    s2 = base.pop(i_start2)
    base.insert(i_done1, s2)
    base.insert(i_done1, ev(testID=1, messageType="print", message="hello", type="print", time=3))
    c, _ = run("\n".join(base) + "\n", required=("test/a_test.dart::plain passes", "test/a_test.dart::second"))
    assert c.state == S.COMPLETED and set(c.outcomes.values()) == {O.PASSED}


def test_non_json_noise_is_ignored_but_corrupt_json_is_an_error():
    good = stream([(1, "plain passes", "success", False)])
    assert run("Waiting for another flutter command...\n" + good)[0].state == S.COMPLETED
    assert run(good.replace('"type": "suite"', '"type": "suite"', 1) + '{"type": "tes')[0].state == S.ERROR


@pytest.mark.parametrize("mutate,why", [
    (lambda t: "\n".join(t.splitlines()[:-1]) + "\n", "no done event"),                      # 截断: 缺 done
    (lambda t: t.replace('"success": true, "type": "done"', '"success": null, "type": "done"'), "done.success is None"),
    (lambda t: t.replace("0.1.1", "9.9.9"), "unsupported event protocol"),
    (lambda t: t + t.splitlines()[-1] + "\n", "not unique"),
    (lambda t: t.replace('"count": 1', '"count": 2'), "allSuites"),
    (lambda t: t.replace(F, "/other/place/test/a_test.dart"), "outside the working directory"),
    (lambda t: "\n".join(l for l in t.splitlines() if "testDone" not in l or '"testID": 1,' not in l) + "\n", "never finished"),
])
def test_truncated_corrupt_or_foreign_reports_never_pass(mutate, why):
    good = stream([(1, "plain passes", "success", False)])
    text = mutate(good)
    c, _ = run(text)
    assert c.state == S.ERROR and why in c.reason, c.reason


def test_exit_code_contradictions_and_unexpected_codes():
    ok = stream([(1, "plain passes", "success", False)])
    assert run(ok, rc=1)[0].state == S.ERROR and "contradiction" in run(ok, rc=1)[0].reason
    bad = stream([(1, "plain passes", "failure", False)], success=False)
    assert run(bad, rc=0)[0].state == S.ERROR
    assert run(ok, rc=79)[0].state == S.ERROR and "exit status 79" in run(ok, rc=79)[0].reason
    lie = stream([(1, "plain passes", "failure", False)], success=True)     # done.success=true 但有失败
    assert run(lie, rc=0)[0].state == S.ERROR


def test_load_failure_in_a_hidden_test_blocks_the_command_even_if_mapped_tests_passed():
    c, _ = run(stream([(1, "plain passes", "success", False)], hidden_result="error", success=False), rc=1)
    assert c.state == S.ERROR and "load/setup failure" in c.reason and "Failed to load" in c.reason


def test_real_flutter_shape_load_failure_has_hidden_false_and_must_still_be_a_load_failure():
    # 真实 flutter 3.38 的编译失败: 加载伪测试 testDone 的 hidden=false, result=error
    c, x = run(stream([], hidden_result="error", success=False, load_hidden_flag=False), rc=1)
    assert c.state == S.ERROR and "load/setup failure in loading test" in c.reason
    c, x = run(stream([(1, "plain passes", "success", False)], hidden_result="error", success=False, load_hidden_flag=False), rc=1)
    assert c.state == S.ERROR and "Failed to load" in c.reason                       # 即使其他测试通过也阻止命令成功


def test_a_user_test_is_never_mistaken_for_a_loading_pseudo_test():
    c, x = run(stream([(1, "loading is slow", "success", False)]), required=("test/a_test.dart::loading is slow",))
    assert c.outcomes["test/a_test.dart::loading is slow"] == O.PASSED and x["real_test_count"] == 1


def test_zero_real_tests_and_missing_mapped_test():
    c, _ = run(stream([]))
    assert c.state == S.ERROR and "no real tests" in c.reason
    c, _ = run(stream([(1, "some other", "success", False)]), required=("test/a_test.dart::plain passes",))
    assert c.state == S.COMPLETED and c.outcomes["test/a_test.dart::plain passes"] == O.MISSING


@pytest.mark.parametrize("mutate,why", [
    (lambda t: t.replace('"result": "failure"', '"result": "success"'), "inconsistent"),     # 成功但有 error 事件
    (lambda t: "\n".join(l for l in t.splitlines() if '"type": "error"' not in l) + "\n", "no error details"),
])
def test_result_and_error_events_must_agree(mutate, why):
    bad = stream([(1, "plain passes", "failure", False)], success=False)
    c, _ = run(mutate(bad), rc=1)
    assert c.state == S.ERROR and why in c.reason


def test_duplicate_or_unknown_ids_are_errors():
    good = stream([(1, "plain passes", "success", False)])
    dup_start = ev(test={"id": 1, "name": "again", "suiteID": 0, "groupIDs": [], "metadata": {"skip": False}}, type="testStart", time=6)
    c, _ = run(good.replace(ev(success=True, type="done", time=9), dup_start + "\n" + ev(success=True, type="done", time=9)))
    assert c.state == S.ERROR and "duplicate test id 1" in c.reason
    dup_done = good.replace(ev(success=True, type="done", time=9), ev(testID=1, result="success", skipped=False, hidden=False, type="testDone", time=8) + "\n" + ev(success=True, type="done", time=9))
    assert "finished twice" in run(dup_done)[0].reason
    unk = good.replace(ev(success=True, type="done", time=9), ev(testID=999, result="success", skipped=False, hidden=False, type="testDone", time=8) + "\n" + ev(success=True, type="done", time=9))
    assert "unknown test" in run(unk)[0].reason


def test_empty_output_and_wrong_first_event():
    assert run("")[0].state == S.ERROR and "no JSON events" in run("")[0].reason
    assert "does not begin with a start" in run(ev(type="suite"))[0].reason


def test_parse_events_counts_noise():
    evs, problems, noise = parse_events("noise\n" + ev(type="start") + "\n\nmore noise\n")
    assert len(evs) == 1 and noise == 2 and problems == []


# ---------------------------------------------------------------- B4-01: 协议生命周期与字段 (实现方回归)

def inject(text, *lines, before="done"):
    done_line = ev(success=True, type="done", time=9)
    assert done_line in text
    return text.replace(done_line, "\n".join(lines) + "\n" + done_line)


def test_testdone_before_its_teststart_is_an_error_even_if_the_pair_is_complete_overall():
    base = stream([(1, "plain passes", "success", False)]).splitlines()
    i_start = next(i for i, l in enumerate(base) if '"id": 1,' in l and "testStart" in l)
    i_done = next(i for i, l in enumerate(base) if '"testID": 1,' in l and "testDone" in l)
    assert i_start < i_done and '"id": 1,' in base[i_start] and '"testID": 1,' in base[i_done]
    base[i_start], base[i_done] = base[i_done], base[i_start]           # testDone 先于 testStart, 事件总数与配对都完整
    c, _ = run("\n".join(base) + "\n")
    assert c.state == S.ERROR and "out-of-order" in c.reason


@pytest.mark.parametrize("where", ["after_allsuites", "just_before_done", "at_the_end_after_done"])
def test_a_second_session_start_is_an_error_wherever_it_appears(where):
    good = stream([(1, "plain passes", "success", False)])
    start = ev(protocolVersion="0.1.1", runnerVersion=None, pid=2, type="start", time=0)
    if where == "after_allsuites":
        text = good.replace(ev(testID=100, result="success", skipped=False, hidden=True, type="testDone", time=2), start + "\n" + ev(testID=100, result="success", skipped=False, hidden=True, type="testDone", time=2))
    elif where == "just_before_done":
        text = inject(good, start)
    else:
        text = good + start + "\n"
    c, _ = run(text)
    assert c.state == S.ERROR and ("second session start" in c.reason or "not unique or not the last" in c.reason)


def test_two_complete_concatenated_sessions_are_not_accepted():
    good = stream([(1, "plain passes", "success", False)])
    assert run(good + good)[0].state == S.ERROR


@pytest.mark.parametrize("field", ["testID", "error", "isFailure"])
def test_error_event_missing_a_protocol_field_is_an_error_not_ignored(field):
    bad = {"testID": 1, "error": "unexpected", "stackTrace": "st", "isFailure": True}
    del bad[field]
    text = inject(stream([(1, "plain passes", "success", False)]).replace('"result": "success", "skipped": false, "hidden": false', '"result": "success", "skipped": false, "hidden": false', 1),
                  ev(type="error", **bad))
    c, x = run(text)
    assert c.state == S.ERROR and "malformed error event" in c.reason
    assert len(x["malformed_events"]) == 1 and '"type": "error"' in x["malformed_events"][0]    # 原始事件保留


@pytest.mark.parametrize("kind,event", [
    ("error", dict(type="error", testID=1, error=5, stackTrace="s", isFailure=True)),              # 类型错误
    ("error", dict(type="error", testID=1, error="e", stackTrace=7, isFailure=True)),
    ("error", dict(type="error", testID=1, error="e", stackTrace="s", isFailure="yes")),
    ("testDone", dict(type="testDone", testID=1, result="success", skipped="no", hidden=False)),
    ("testDone", dict(type="testDone", testID=1, result="success", hidden=False)),                   # 缺 skipped
    ("testStart", dict(type="testStart", test={"id": 5, "suiteID": 0})),                              # 缺 name
    ("suite", dict(type="suite", suite={"id": 9})),                                                    # 缺 path
    ("allSuites", dict(type="allSuites", count="1")),
])
def test_malformed_protocol_events_are_errors(kind, event):
    text = inject(stream([(1, "plain passes", "success", False)]), ev(**event))
    c, _ = run(text)
    assert c.state == S.ERROR and f"malformed {kind} event" in c.reason, c.reason


def test_error_event_after_its_testdone_or_for_an_unstarted_test_is_an_error():
    good = stream([(1, "plain passes", "success", False)])
    late = inject(good, ev(type="error", testID=1, error="late", stackTrace="", isFailure=True))
    assert "after its testDone" in run(late)[0].reason
    unstarted = inject(good, ev(type="error", testID=42, error="x", stackTrace="", isFailure=True))
    assert "had not started" in run(unstarted)[0].reason


def test_events_after_done_are_an_error():
    good = stream([(1, "plain passes", "success", False)])
    assert run(good + ev(type="print", testID=1, message="late", messageType="print") + "\n")[0].state == S.ERROR


def test_testdone_whose_test_starts_later_is_an_error_but_normal_interleaving_still_passes():
    # 正常交错: test 2 在 test 1 完成前开始, 各自有序
    text = "\n".join([
        ev(protocolVersion="0.1.1", runnerVersion=None, pid=1, type="start", time=0),
        ev(suite={"id": 0, "platform": "vm", "path": F}, type="suite", time=0),
        ev(count=1, type="allSuites", time=1),
        ev(test={"id": 1, "name": "one", "suiteID": 0, "groupIDs": [], "metadata": {"skip": False}}, type="testStart", time=2),
        ev(test={"id": 2, "name": "two", "suiteID": 0, "groupIDs": [], "metadata": {"skip": False}}, type="testStart", time=3),
        ev(testID=2, result="success", skipped=False, hidden=False, type="testDone", time=4),
        ev(testID=1, result="success", skipped=False, hidden=False, type="testDone", time=5),
        ev(success=True, type="done", time=6)]) + "\n"
    c, _ = run(text, required=("test/a_test.dart::one", "test/a_test.dart::two"))
    assert c.state == S.COMPLETED and set(c.outcomes.values()) == {O.PASSED}
    # 同样的事件, 但 test 2 的 done 排在它的 start 之前
    lines = text.splitlines()
    lines[4], lines[5] = lines[5], lines[4]
    assert run("\n".join(lines) + "\n", required=("test/a_test.dart::one",))[0].state == S.ERROR
