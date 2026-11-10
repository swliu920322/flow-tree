import json
import os
import shutil
import signal
import time

import pytest

from b1b_support import NID_A, NID_B, PY, Proj, automation, manifests, units


@pytest.fixture
def proj(tmp_path):
    return Proj(tmp_path / "p")


def attempt(res, entry):
    return next(a for a in res["attempts"] if a["entry"].endswith("/" + entry))


# ---------------- 通过路径与退出码 ----------------

def test_real_pass_writes_evidence_and_exits_zero_in_mapped_scope(proj):
    r, res = proj.verify()
    assert r.returncode == 0, r.stdout + r.stderr
    assert res["executed"] and attempt(res, "M-01")["state"] == "completed"
    assert automation(res, "CASE-01") == "passed" and automation(res, "STEP-03") == "passed"
    assert automation(res, "STEP-01") == "unmapped"
    mf = json.loads(manifests(proj.root)[0].read_text())
    assert mf["command"]["cwd"] == str(proj.root.resolve()) and mf["exit_code"] == 0
    assert mf["baseline"]["worktree_fingerprint"] and mf["baseline"]["runtime_digest"]
    assert mf["baseline"]["story_digest"] == proj.story_digest()
    assert {"plugin_report", "junit", "stdout", "stderr"} <= set(mf["artifacts"])


def test_default_scope_is_whole_story_so_unmapped_units_make_verify_fail(proj):
    r, res = proj.verify(mapped_only=False)
    assert r.returncode == 1
    assert automation(res, "CASE-01") == "passed" and automation(res, "STEP-01") == "unmapped"


def test_status_after_pass_is_current_and_exits_zero_even_with_unverified_units(proj):
    proj.verify()
    r, res = proj.status()
    assert r.returncode == 0
    assert automation(res, "CASE-01") == "passed"
    assert res["stories"][0]["summary"]["complete"] is False  # 规则未确认/人工未验收


def test_status_with_no_evidence_is_not_run_and_exit_zero(proj):
    r, res = proj.status()
    assert r.returncode == 0 and automation(res, "CASE-01") == "not_run"


def test_invalid_input_does_not_execute(proj):
    proj.story_file.write_text(proj.story_file.read_text(encoding="utf-8").replace("at: STEP-02\n    kind: validation", "at: NOPE\n    kind: validation"), encoding="utf-8")
    r, res = proj.verify()
    assert r.returncode == 1 and res["executed"] is False
    assert not manifests(proj.root)


# ---------------- 失败与各类不能通过 ----------------

def test_assertion_failure_is_failed_not_error(proj):
    (proj.root / "tests/test_savings.py").write_text("def test_zero_amount_rejected():\n    assert 1 == 2\ndef test_resume_after_lost_response():\n    assert True\n")
    r, res = proj.verify()
    assert r.returncode == 1
    assert attempt(res, "M-01")["state"] == "completed" and automation(res, "CASE-01") == "failed"
    assert automation(res, "CASE-02") == "passed"  # 另一个条目不受牵连


def test_all_skipped_is_not_run(proj):
    (proj.root / "tests/test_savings.py").write_text("import pytest\npytestmark = pytest.mark.skip(reason='x')\ndef test_zero_amount_rejected(): pass\ndef test_resume_after_lost_response(): pass\n")
    r, res = proj.verify()
    assert r.returncode == 1 and automation(res, "CASE-01") == "not_run"


def test_mapped_nodeid_absent_from_collection_is_error_even_if_exit_zero(proj):
    (proj.root / "tests/test_savings.py").write_text("def test_other(): pass\ndef test_resume_after_lost_response(): pass\n")
    r, res = proj.verify()
    assert r.returncode == 1
    assert automation(res, "CASE-01") == "error"           # exit 0, 但映射声明的测试没有执行
    assert automation(res, "CASE-02") == "passed"


def test_xfail_is_failed_and_strict_xpass_is_error(proj):
    (proj.root / "tests/test_savings.py").write_text(
        "import pytest\n@pytest.mark.xfail(reason='known')\ndef test_zero_amount_rejected(): assert False\n"
        "@pytest.mark.xfail(strict=True)\ndef test_resume_after_lost_response(): assert True\n")
    r, res = proj.verify()
    assert automation(res, "CASE-01") == "failed" and automation(res, "CASE-02") == "error"


def test_nonstrict_xpass_is_error_not_pass(proj):
    (proj.root / "tests/test_savings.py").write_text(
        "import pytest\n@pytest.mark.xfail\ndef test_zero_amount_rejected(): assert True\ndef test_resume_after_lost_response(): pass\n")
    r, res = proj.verify()
    assert automation(res, "CASE-01") == "error"


def test_teardown_failure_after_passing_call_is_not_pass(proj):
    (proj.root / "tests/test_savings.py").write_text(
        "import pytest\n@pytest.fixture\ndef f():\n    yield\n    raise RuntimeError('td')\n"
        "def test_zero_amount_rejected(f): pass\ndef test_resume_after_lost_response(): pass\n")
    r, res = proj.verify()
    assert r.returncode == 1 and automation(res, "CASE-01") == "error" and automation(res, "CASE-02") == "passed"


def test_setup_error_is_error(proj):
    (proj.root / "tests/test_savings.py").write_text(
        "import pytest\n@pytest.fixture\ndef f():\n    raise RuntimeError('su')\n"
        "def test_zero_amount_rejected(f): pass\ndef test_resume_after_lost_response(): pass\n")
    r, res = proj.verify()
    assert automation(res, "CASE-01") == "error"


def test_collection_error_fails_whole_attempt(proj):
    (proj.root / "tests/test_savings.py").write_text("def test_zero_amount_rejected(:\n")
    r, res = proj.verify()
    a = attempt(res, "M-01")
    assert a["state"] == "error" and "collection" in a["reason"] and r.returncode == 1


def test_parametrized_instance_exact_nodeid_must_exist(proj):
    (proj.root / "tests/test_savings.py").write_text(
        "import pytest\n@pytest.mark.parametrize('x', [1, 2])\ndef test_zero_amount_rejected(x): assert x\ndef test_resume_after_lost_response(): pass\n")
    proj.write_mapping(tests_a="tests/test_savings.py::test_zero_amount_rejected[1]")
    r, res = proj.verify()
    assert automation(res, "CASE-01") == "passed"
    proj.write_mapping(tests_a="tests/test_savings.py::test_zero_amount_rejected[9]")  # 不存在的实例
    r, res = proj.verify()
    assert automation(res, "CASE-01") == "error"


# ---------------- 范围与环境不能被悄悄改变 ----------------

def test_pytest_addopts_env_is_scrubbed_and_cannot_deselect(proj):
    r, res = proj.verify(env={"PYTEST_ADDOPTS": "-k nomatchatall"})
    assert automation(res, "CASE-01") == "passed"
    assert json.loads(manifests(proj.root)[0].read_text())["command"]["pytest_addopts_removed"] == "-k nomatchatall"


def test_ini_addopts_scope_option_detected_by_plugin(tmp_path):
    p = Proj(tmp_path / "p", pytest_ini="[pytest]\naddopts = -k zero\n")
    r, res = p.verify()
    a = attempt(res, "M-02")
    assert a["state"] == "error" and "scope-altering" in a["reason"]
    assert automation(res, "CASE-02") == "error"


def test_rootdir_differing_from_cwd_is_error_and_correct_cwd_fixes_it(tmp_path):
    p = Proj(tmp_path / "p")
    (p.root / "backend").mkdir()
    shutil.move(str(p.root / "tests"), str(p.root / "backend" / "tests"))
    (p.root / "backend" / "pytest.ini").write_text("[pytest]\n")   # 子目录 ini → pytest rootdir=backend
    p.write_mapping(argv="[python, -m, pytest, backend/tests, -q]")  # cwd="." 但 rootdir=backend: nodeid 基准不一致
    r, res = p.verify()
    a = attempt(res, "M-01")
    assert a["state"] == "error" and "rootdir" in a["reason"]
    p.write_mapping(cwd="backend", argv="[python, -m, pytest, tests, -q]")  # 基准一致
    r, res = p.verify()
    assert automation(res, "CASE-01") == "passed"


def test_missing_interpreter_and_missing_cwd_are_blocked_not_error(proj):
    r, res = proj.verify(python="/nonexistent/python")
    assert attempt(res, "M-01")["state"] == "blocked" and automation(res, "CASE-01") == "blocked"
    proj.write_mapping(cwd="nodir")
    r, res = proj.verify()
    assert attempt(res, "M-01")["state"] == "blocked"


def test_interpreter_without_pytest_is_blocked(proj):
    r, res = proj.verify(python="/usr/bin/python3")
    assert attempt(res, "M-01")["state"] == "blocked" and "pytest" in attempt(res, "M-01")["reason"]


def test_cwd_escaping_project_root_is_error(proj):
    proj.write_mapping(cwd="..")
    r, res = proj.verify()
    assert attempt(res, "M-01")["state"] == "error" and "outside" in attempt(res, "M-01")["reason"]


# ---------------- 超时与进程清理 ----------------

def test_timeout_terminates_owned_process_group_and_records_error(tmp_path):
    p = Proj(tmp_path / "p", timeout_s=2, tests="""
        import os, subprocess, sys, time
        def test_zero_amount_rejected():
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            open(os.path.join(os.path.dirname(__file__), "..", "child.pid"), "w").write(str(child.pid))
            time.sleep(60)
        def test_resume_after_lost_response(): pass
    """)
    r, res = p.verify("--entry", "M-01")
    a = attempt(res, "M-01")
    assert a["state"] == "error" and "timeout" in a["reason"] and r.returncode == 1
    pid = int((p.root / "child.pid").read_text())
    time.sleep(0.5)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)  # 子进程组里的孙进程也已被终止
    mf = json.loads(manifests(p.root)[0].read_text())
    assert mf["state"] == "error" and mf["finished_at"]


# ---------------- 有效性: 变更使旧证据失效 ----------------

def test_modified_tracked_source_makes_old_pass_stale_but_keeps_history(proj):
    proj.verify()
    (proj.root / "tests/test_savings.py").write_text("# changed\n" + (proj.root / "tests/test_savings.py").read_text())
    r, res = proj.status()
    assert r.returncode == 0
    u = units(res)["SAV-001.CASE-01"]
    assert u["automation"] == "not_run"
    e = u["entries"][0]
    assert e["validity"] == "stale" and e["last_result"] == "passed" and e["counts_for_current"] is None
    assert any("worktree" in x for x in e["validity_reasons"])


def test_new_untracked_source_file_invalidates(proj):
    proj.verify()
    (proj.root / "helper_added.py").write_text("X = 1\n")
    r, res = proj.status()
    assert units(res)["SAV-001.CASE-01"]["entries"][0]["validity"] == "stale"


def test_ignored_file_change_does_not_invalidate_but_is_not_hiding_source(proj):
    proj.verify()
    (proj.root / "__pycache__").mkdir(exist_ok=True)
    (proj.root / "__pycache__" / "x.pyc").write_text("noise")
    r, res = proj.status()
    assert automation(res, "CASE-01") == "passed"


def test_story_edit_invalidates_evidence(proj):
    proj.verify()
    proj.story_file.write_text(proj.story_file.read_text(encoding="utf-8").replace("记录一次克制消费", "记录一次克制消费(改)"), encoding="utf-8")
    proj.write_mapping()  # 映射所有者重审并更新钉住值
    r, res = proj.status()
    e = units(res)["SAV-001.CASE-01"]["entries"][0]
    assert e["validity"] == "stale" and any("story" in x for x in e["validity_reasons"])
    assert automation(res, "CASE-01") == "not_run"


def test_changed_mapping_entry_invalidates_only_that_entry(proj):
    proj.verify()
    proj.write_mapping(argv="[python, -m, pytest, tests/test_savings.py, -q, -v]")  # 两个条目的 argv 都变
    r, res = proj.status()
    assert automation(res, "CASE-01") == "not_run"
    # 只改 M-01 的 timeout, M-02 证据仍有效
    proj.write_mapping()
    proj.verify()
    text = proj.map_file.read_text().replace("timeout_s: 120", "timeout_s: 121", 1)
    proj.map_file.write_text(text)
    r, res = proj.status()
    assert automation(res, "CASE-01") == "not_run" and automation(res, "CASE-02") == "passed"


def test_environment_id_change_invalidates(proj):
    proj.verify()
    proj.write_mapping(env_id="env-2")
    r, res = proj.status()
    assert automation(res, "CASE-01") == "not_run"


def test_file_created_during_run_gives_unknown_validity_not_current_pass(tmp_path):
    p = Proj(tmp_path / "p", tests="""
        import os
        def test_zero_amount_rejected():
            open(os.path.join(os.path.dirname(__file__), "..", "generated_untracked.txt"), "w").write("x")
        def test_resume_after_lost_response(): pass
    """)
    r, res = p.verify("--entry", "M-01")
    assert r.returncode == 1
    e = units(res)["SAV-001.CASE-01"]["entries"][0]
    assert e["validity"] == "unknown" and e["last_result"] == "passed" and automation(res, "CASE-01") == "not_run"
    mf = json.loads(manifests(p.root)[0].read_text())
    assert "worktree" in mf["changed_during_run"] and mf["state"] == "completed"


def test_story_modified_during_run_is_not_current_pass(tmp_path):
    p = Proj(tmp_path / "p")
    (p.root / "tests/test_savings.py").write_text(f"""
def test_zero_amount_rejected():
    import pathlib
    f = pathlib.Path(r"{p.story_file}")
    f.write_text(f.read_text(encoding="utf-8").replace("记录一次克制消费", "记录一次克制消费(运行中改)"), encoding="utf-8")
def test_resume_after_lost_response(): pass
""")
    r, res = p.verify("--entry", "M-01")
    e = units(res)["SAV-001.CASE-01"]["entries"][0]
    assert e["validity"] != "current" and automation(res, "CASE-01") != "passed"


# ---------------- 证据完整性 ----------------

def test_tampered_artifact_is_reported_and_never_passes(proj):
    proj.verify()
    junit = next((proj.root / ".flowtree/runs").glob("*/*/M-01/junit.xml"))
    junit.write_text(junit.read_text() + "<!-- edited -->")
    r, res = proj.status()
    assert r.returncode == 0
    assert automation(res, "CASE-01") == "error" and any("junit" in p for p in res["evidence_problems"])
    assert automation(res, "CASE-02") == "passed"


def test_manifest_edit_after_index_is_detected(proj):
    proj.verify()
    mp = manifests(proj.root)[0]
    d = json.loads(mp.read_text())
    d["required_nodeids"] = []
    mp.write_text(json.dumps(d))
    r, res = proj.status()
    assert any("manifest changed" in p for p in res["evidence_problems"])
    assert "error" in {automation(res, "CASE-01"), automation(res, "CASE-02")}


def test_index_row_deleted_is_inconsistent(proj):
    import sqlite3
    proj.verify()
    conn = sqlite3.connect(proj.root / ".flowtree" / "data.db")
    conn.execute("DELETE FROM flowtree_attempts WHERE entry_id='M-01'")
    conn.commit(); conn.close()
    r, res = proj.status()
    assert automation(res, "CASE-01") == "error" and any("no index row" in p for p in res["evidence_problems"])


def test_index_state_mismatch_is_inconsistent(proj):
    import sqlite3
    proj.verify()
    conn = sqlite3.connect(proj.root / ".flowtree" / "data.db")
    conn.execute("UPDATE flowtree_attempts SET state='error' WHERE entry_id='M-01'")
    conn.commit(); conn.close()
    r, res = proj.status()
    assert automation(res, "CASE-01") == "error"


def test_unfinished_attempt_is_running_then_aborted_and_never_passes(proj, monkeypatch):
    from flowtree import evidence, service
    from flowtree.evidence import EvidenceStore, now_iso
    proj.verify()
    old = json.loads(manifests(proj.root)[0].read_text())
    time.sleep(0.01)
    m = dict(old, run_id="run_zzz_unfinished", attempt_id="run_zzz_unfinished.SAV-001.M-01", state="running",
             started_at=now_iso(), finished_at=None, artifacts={}, outcomes={})   # 比真实通过更新的未完成尝试
    EvidenceStore(proj.root).write_manifest(m)

    def st():
        res = service.status([proj.stories], [proj.maps], proj.root, PY)
        return automation(res, "CASE-01")
    assert st() == "running"                                  # 刚开始: 仍在运行, 不回退到更早的通过
    monkeypatch.setattr(evidence, "RUNNING_GRACE_S", -10_000)  # 模拟已超过 timeout+宽限仍无终态
    assert st() == "error"                                    # aborted → error


def test_latest_attempt_wins_over_earlier_pass(proj):
    proj.verify()
    (proj.root / "tests/test_savings.py").write_text("def test_zero_amount_rejected(): assert False\ndef test_resume_after_lost_response(): pass\n")
    proj.verify()
    r, res = proj.status()
    assert automation(res, "CASE-01") == "failed"
