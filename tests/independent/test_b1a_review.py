"""Codex 独立断言。已发现缺陷保持失败，不以 skip/xfail 代替修复。"""
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from flowtree.canon import YamlLoadError, content_digest
from flowtree.service import plan, validate
from flowtree.status import (
    Auto, AttemptState, Baseline, EntryEvidence, TestOutcome as Outcome,
    Validity, combine, entry_result, evaluate_validity,
)

ROOT = Path(__file__).resolve().parents[2]


def story_data():
    return {
        "schema_version": "0.1", "id": "CHECK-01", "title": "独立样本",
        "actor": "用户", "goal": "明确结果", "inputs": {"amount": "0.25"},
        "main_flow": [
            {"id": "STEP-01", "action": "提交", "expected": ["记录一次"]},
            {"id": "STEP-02", "action": "查看", "expected": ["结果持久化"]},
        ],
        "branches": [{"id": "CASE-01", "at": "STEP-01", "kind": "recovery",
                      "condition": "响应丢失", "expected": ["确认原请求"],
                      "continuation": {"type": "rejoin", "target": "STEP-02"}}],
        "open_questions": [],
    }


def write_story(tmp_path, raw=None):
    path = tmp_path / "story.yaml"
    path.write_text(yaml.safe_dump(raw or story_data(), allow_unicode=True), encoding="utf-8")
    return path


def test_cli_plan_real_subprocess_never_claims_execution(tmp_path):
    path = write_story(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "story", "plan", str(path), "--json"],
        cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["executed"] is False
    summary = payload["stories"][0]["summary"]
    assert summary["units_total"] == 3
    assert summary["automation"]["unmapped"] == 3
    assert summary["automation"]["passed"] == 0
    assert summary["complete"] is False


def test_local_unknown_does_not_block_unrelated_unit(tmp_path):
    raw = story_data()
    raw["open_questions"] = [{"id": "Q1", "text": "恢复超时策略?", "blocks": ["CASE-01"]}]
    result = plan([write_story(tmp_path, raw)])
    assert result["ok"]
    units = {u["id"]: u for u in result["stories"][0]["units"]}
    assert units["CHECK-01.CASE-01"]["rule"] == "pending"
    assert units["CHECK-01.STEP-02"]["rule"] == "draft"
    assert all(u["human"] == "none" for u in units.values())


@pytest.mark.parametrize("change", ["duplicate", "dangling", "retry"])
def test_invalid_flow_is_rejected(tmp_path, change):
    raw = story_data()
    if change == "duplicate":
        raw["branches"][0]["id"] = "STEP-01"
    elif change == "dangling":
        raw["branches"][0]["continuation"]["target"] = "STEP-404"
    else:
        raw["branches"][0]["continuation"] = {"type": "retry", "target": "STEP-01"}
    assert validate([write_story(tmp_path, raw)])["ok"] is False


def test_empty_story_directory_is_not_successful_validation(tmp_path):
    # F03: 用户给错空目录时不能得到“格式与引用有效”的成功结果。
    result = validate([tmp_path])
    assert result["ok"] is False, result
    assert result["issues"]


def test_unicode_normalized_key_collision_is_rejected():
    # F04: NFC 后冲突的键不得静默覆盖，导致不同内容使用相同摘要。
    with pytest.raises(YamlLoadError):
        content_digest({"inputs": {"é": "original", "e\u0301": "other"}})


def test_unmapped_aggregate_never_becomes_passed():
    # F05: combine 是公共状态聚合函数，合法 Auto 值不得回退为 PASSED。
    assert combine([Auto.PASSED, Auto.UNMAPPED]) != Auto.PASSED


@pytest.mark.parametrize("outcome", [Outcome.SKIPPED, Outcome.XFAILED, Outcome.XPASSED, Outcome.ERROR])
def test_nonpass_outcome_cannot_contribute_pass(outcome):
    base = Baseline("story", "entry", "env", "tree")
    evidence = EntryEvidence("M1", AttemptState.COMPLETED, base, {"t.py::test_a": outcome})
    assert entry_result(["t.py::test_a"], evidence) != Auto.PASSED


@pytest.mark.parametrize("state", [AttemptState.RUNNING, AttemptState.ABORTED, AttemptState.ERROR, AttemptState.BLOCKED])
def test_incomplete_attempt_with_passing_test_does_not_pass(state):
    base = Baseline("story", "entry", "env", "tree")
    evidence = EntryEvidence("M1", state, base, {"t.py::test_a": Outcome.PASSED})
    assert entry_result(["t.py::test_a"], evidence) != Auto.PASSED


def test_changed_content_invalidates_same_git_sha():
    old = Baseline("story", "entry", "env", "old", git_sha="same")
    new = Baseline("story", "entry", "env", "new", git_sha="same")
    assert evaluate_validity(old, new)[0] == Validity.STALE


@pytest.fixture
def isolated_api(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient
    import app.main as api
    data = tmp_path / "data"
    shutil.copytree(ROOT / "backend/app/data", data)
    monkeypatch.setattr(api, "DATA_DIR", data)
    monkeypatch.setattr(api, "PROJECT_STORE", {})
    monkeypatch.setattr(api, "PROJECT_FILES", {
        "proj-life-piggy-bank": "life_piggy_bank.json",
        "proj-mall-001": "demo_project.json",
    })
    with TestClient(api.app) as client:
        yield client, api


def sync_payload(api, project_id):
    payload = copy.deepcopy(api.load_project_by_id("proj-life-piggy-bank").model_dump(mode="json"))
    payload["projectId"] = project_id
    for node in payload["nodes"]:
        node["status"] = "pending_dev"
        node["review"] = {}
    return payload


def test_sync_does_not_accept_forged_human_acceptance(isolated_api):
    # F01: 拦截可以拒绝请求或净化数据，但不得持久化调用方伪造的真实人签。
    client, api = isolated_api
    payload = sync_payload(api, "proj-independent-real")
    node = payload["nodes"][1]
    node["status"] = "review_pass"
    node["review"] = {"humanSignOff": True, "humanSignOffBy": "real-user"}
    response = client.post("/api/projects/sync", json=payload)
    if response.status_code >= 400:
        return
    stored = api.load_project_by_id(payload["projectId"])
    actual = next(n for n in stored.nodes if n.nodeId == node["nodeId"])
    assert not actual.review.humanSignOff and actual.status.value != "review_pass"


def test_synced_content_cannot_inherit_demo_permission_from_id(isolated_api):
    # F02: 用同名 ID 同步真实拓扑，不能继承内置 demo 的人签权限。
    client, api = isolated_api
    payload = sync_payload(api, "proj-life-piggy-bank")
    node = payload["nodes"][1]
    node["nodeId"] = "INDEPENDENT-REAL-NODE"
    response = client.post("/api/projects/sync", json=payload)
    if response.status_code >= 400:
        return
    response = client.patch(
        f"/api/projects/{payload['projectId']}/nodes/{node['nodeId']}/status",
        json={"status": "review_pass"},
    )
    assert response.status_code in (403, 404, 409), response.text
