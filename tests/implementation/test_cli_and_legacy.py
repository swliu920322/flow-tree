import json
import shutil
import sqlite3
import subprocess
import sys

import pytest
import yaml

from impl_support import FIXTURES, ROOT


def flowtree(*args, cwd=None):
    return subprocess.run([sys.executable, "-m", "cli.main", *args], cwd=cwd or ROOT,
                          capture_output=True, text=True, timeout=60)


@pytest.fixture
def proj(tmp_path):
    stories = tmp_path / "stories"
    maps = tmp_path / "maps"
    stories.mkdir(); maps.mkdir()
    shutil.copy(FIXTURES / "sav-001.story.yaml", stories)
    shutil.copy(FIXTURES / "sav-001.mapping.yaml", maps)
    return stories, maps


# ---------- story validate / plan 退出码 ----------

def test_validate_ok_exit_0_and_json_digests(proj):
    stories, maps = proj
    r = flowtree("story", "validate", str(stories), "--mappings", str(maps), "--json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] and out["stories"][0]["id"] == "SAV-001"
    assert out["stories"][0]["untyped_inputs"] == ["amount", "category"]
    assert set(out["mappings"][0]["entries"]) == {"M-01", "M-02"}


def test_validate_reports_open_questions_but_succeeds(proj):
    stories, maps = proj
    p = stories / "sav-001.story.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("open_questions: []", "open_questions:\n  - 上限未定\n"), encoding="utf-8")
    r = flowtree("story", "validate", str(stories), "--json")
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["stories"][0]["open_questions"][0]["legacy"] is True


def test_validate_invalid_exit_1(proj):
    stories, maps = proj
    p = stories / "sav-001.story.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("at: STEP-02\n    kind: validation", "at: STEP-77\n    kind: validation"), encoding="utf-8")
    r = flowtree("story", "validate", str(stories))
    assert r.returncode == 1 and "dangling_ref" in r.stdout


def test_plan_succeeds_with_unmapped_and_never_claims_execution(proj):
    stories, maps = proj
    r = flowtree("story", "plan", str(stories), "--mappings", str(maps), "--json")
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["executed"] is False
    s = out["stories"][0]
    assert s["summary"]["automation"]["passed"] == 0
    assert s["summary"]["complete"] is False
    assert s["unmapped"] == ["SAV-001.STEP-01", "SAV-001.STEP-02", "SAV-001.STEP-04"]


def test_plan_invalid_input_exit_1(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: a story\n", encoding="utf-8")
    assert flowtree("story", "plan", str(bad)).returncode == 1


def test_usage_error_exit_2():
    assert flowtree("story").returncode == 2


# ---------- 旧路径不再伪成功 ----------

def test_init_generates_unverified_skeleton_without_scripts_or_signatures(tmp_path):
    proj = tmp_path / "Life-Piggy-Bank"  # 触发 piggy 模板, 其中曾预填签字
    proj.mkdir()
    for name in ("Life-Piggy-Bank", "generic-app"):
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        r = flowtree("--server", "http://127.0.0.1:9", "init", str(d))  # 端口 9: 不会连上, 离线生效
        assert r.returncode == 0, r.stderr
        circuit = json.loads((d / ".flowtree" / "circuit.json").read_text(encoding="utf-8"))
        assert circuit["origin"] == "template_unverified"
        assert circuit["nodes"], name
        for n in circuit["nodes"]:
            assert n["status"] == "pending_dev", (name, n["nodeId"])
            assert n["review"] == {}, (name, n["nodeId"])
        assert not (d / ".flowtree" / "tests").exists()
        assert "passed = True" not in "".join(p.read_text(encoding="utf-8") for p in (d / ".flowtree").rglob("*.py"))


def test_old_generated_script_is_never_executed_and_run_fails(tmp_path):
    d = tmp_path / "p"
    (d / ".flowtree" / "tests").mkdir(parents=True)
    (d / ".flowtree" / "circuit.json").write_text(json.dumps({"projectId": "p", "projectName": "p", "nodes": [
        {"nodeId": "N1", "name": "x", "status": "logic_verified", "review": {"logicVerified": True}}]}), encoding="utf-8")
    marker = d / "executed.txt"
    (d / ".flowtree" / "tests" / "test_circuit_verification.py").write_text(
        f"open({str(marker)!r}, 'w').write('x')\ndef verify_all_nodes():\n    return {{'N1': {{'passed': True}}}}\n", encoding="utf-8")
    before = (d / ".flowtree" / "circuit.json").read_text(encoding="utf-8")
    r = flowtree("run", str(d))
    assert r.returncode == 1 and "未执行验收" in r.stdout
    assert not marker.exists(), "legacy script must not be imported or executed"
    assert (d / ".flowtree" / "circuit.json").read_text(encoding="utf-8") == before
    assert not (d / ".flowtree" / "data.db").exists(), "no run record may be written"


def test_run_without_init_fails(tmp_path):
    assert flowtree("run", str(tmp_path)).returncode == 1


def test_watch_unavailable_exit_1(tmp_path):
    assert flowtree("watch", str(tmp_path)).returncode == 1


def test_status_succeeds_and_labels_legacy(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    assert flowtree("--server", "http://127.0.0.1:9", "init", str(d)).returncode == 0
    r = flowtree("status", str(d))
    assert r.returncode == 0 and "不是验收证据" in r.stdout and "通过率" in r.stdout and "%" not in r.stdout


def test_status_uninitialized_exit_1(tmp_path):
    assert flowtree("status", str(tmp_path)).returncode == 1


# ---------- storage ----------

def test_storage_empty_run_is_not_all_pass(tmp_path):
    from cli.storage import StorageManager
    s = StorageManager(tmp_path)
    s.record_run("p", "p", 0, [], [], {})
    s.record_run("p", "p", 3, ["a"], [], {})
    s.record_run("p", "p", 1, ["a"], [], {"a": {"passed": True}})
    statuses = sorted(h["status"] for h in s.get_history(10))
    assert statuses == ["ALL_PASS", "INCOMPLETE", "NO_EVIDENCE"]


def test_storage_migrates_legacy_rows_to_unverified(tmp_path):
    ft = tmp_path / ".flowtree"
    ft.mkdir()
    conn = sqlite3.connect(ft / "data.db")
    conn.executescript("""
        CREATE TABLE flowtree_runs (run_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, project_name TEXT,
            git_commit TEXT, git_branch TEXT, total_nodes INTEGER, passed_nodes INTEGER, blocked_nodes INTEGER,
            duration_ms REAL, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO flowtree_runs (run_id, project_id, project_name, total_nodes, passed_nodes, blocked_nodes, status)
            VALUES ('run_old', 'p', 'p', 0, 0, 0, 'ALL_PASS');
    """)
    conn.commit(); conn.close()
    from cli.storage import StorageManager
    hist = StorageManager(tmp_path).get_history(5)
    assert hist[0]["run_id"] == "run_old" and hist[0]["evidence_kind"] == "legacy_unverified"


# ---------- MCP 工具类委托同一服务 ----------

def test_mcp_tools_do_not_fake_success(tmp_path, proj):
    sys.path.insert(0, str(ROOT))
    from cli.mcp_server import FlowTreeMCPTools as T
    d = tmp_path / "p"; d.mkdir()
    r = T.tool_verify(str(d))
    assert r["executed"] is False
    stories, maps = proj
    v = T.tool_story_validate([str(stories)], [str(maps)])
    assert v["ok"] is True
    p = T.tool_story_plan([str(stories)], [str(maps)])
    assert p["executed"] is False
