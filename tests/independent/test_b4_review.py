"""Flutter机器协议独立反例，不复用实现方报告构造器。"""
import copy
import json

import pytest

from flowtree.runners.flutter_runner import analyze
from flowtree.status import AttemptState, TestOutcome as Outcome


def events():
    return [
        {"type": "start", "protocolVersion": "0.1.1", "pid": 100, "time": 0},
        {"type": "suite", "suite": {"id": 0, "path": "/p/test/a_test.dart"}, "time": 0},
        {"type": "allSuites", "count": 1, "time": 1},
        {"type": "testStart", "test": {"id": 1, "name": "group keeps::name", "suiteID": 0,
                                       "groupIDs": [], "metadata": {"skip": False}}, "time": 2},
        {"type": "testDone", "testID": 1, "result": "success", "skipped": False, "hidden": False, "time": 3},
        {"type": "done", "success": True, "time": 4},
    ]


def classify(rows, code=0):
    return analyze("\n".join(json.dumps(r) for r in rows), cwd="/p", returncode=code,
                   required=["test/a_test.dart::group keeps::name"])[0]


def test_complete_name_with_separator_is_preserved():
    result = classify(events())
    assert result.state == AttemptState.COMPLETED
    assert result.outcomes["test/a_test.dart::group keeps::name"] == Outcome.PASSED


def test_success_with_skip_is_not_pass():
    rows = events()
    rows[4]["skipped"] = True
    assert classify(rows).outcomes["test/a_test.dart::group keeps::name"] == Outcome.SKIPPED


@pytest.mark.parametrize("mutation", ["done_before_start", "second_session_start", "malformed_error"])
def test_impossible_or_inconsistent_stream_cannot_pass(mutation):
    rows = events()
    if mutation == "done_before_start":
        rows[3], rows[4] = rows[4], rows[3]
    elif mutation == "second_session_start":
        rows.insert(3, copy.deepcopy(rows[0]))
    else:
        rows.insert(4, {"type": "error", "testID": 1, "error": "unexpected error", "time": 2})
    assert classify(rows).state == AttemptState.ERROR


def test_loading_failure_with_hidden_false_is_session_error():
    rows = events()
    rows[3]["test"]["name"] = "loading /p/test/a_test.dart"
    rows[4]["result"] = "error"
    rows[-1]["success"] = False
    rows.insert(4, {"type": "error", "testID": 1, "error": "compile failed", "isFailure": False, "time": 2})
    assert classify(rows, 1).state == AttemptState.ERROR
