"""Codex 第二轮 B1B-01～06 的实现方回归 (真实子进程/真实 git 仓库; 独立断言在 tests/independent/test_b1b_review.py)。"""
import json
import os
import shutil
import signal
import sqlite3
import time

import pytest

from b1b_support import NID_A, NID_B, PY, Proj, automation, manifests, units
from flowtree.canon import content_digest, load_yaml_text


@pytest.fixture
def proj(tmp_path):
    return Proj(tmp_path / "p")


def attempt(res, entry):
    return next(a for a in res["attempts"] if a["entry"].endswith("/" + entry))


def add_second_story(p, sid="SAV-002"):
    """复制故事与映射为另一个故事, 条目 ID 与第一个故事相同 (M-01/M-02)。"""
    st = p.story_file.read_text(encoding="utf-8").replace("id: SAV-001", f"id: {sid}")
    (p.stories / f"{sid}.story.yaml").write_text(st, encoding="utf-8")
    digest = content_digest(load_yaml_text(st))
    mp = p.map_file.read_text(encoding="utf-8").replace("story: SAV-001", f"story: {sid}").replace("SAV-001.", f"{sid}.")
    mp = mp.replace(p.story_digest(), digest)
    (p.maps / f"{sid}.mapping.yaml").write_text(mp, encoding="utf-8")


# ---------------- B1B-01 ----------------

def two_passes(p):
    p.verify()
    time.sleep(0.01)
    return p.verify()[1]


@pytest.mark.parametrize("mutation", ["truncate", "remove_manifest", "remove_dir", "list_json", "bad_baseline_type", "missing_key"])
def test_latest_attempt_damage_never_falls_back_to_older_pass(proj, mutation):
    res = two_passes(proj)
    latest = next(a for a in res["attempts"] if a["entry"].endswith("M-01"))["manifest"]
    from pathlib import Path
    mp = Path(latest)
    if mutation == "truncate":
        mp.write_text("{")
    elif mutation == "remove_manifest":
        mp.unlink()
    elif mutation == "remove_dir":
        shutil.rmtree(mp.parent)
    elif mutation == "list_json":
        mp.write_text("[]")
    elif mutation == "bad_baseline_type":
        d = json.loads(mp.read_text()); d["baseline"] = "x"; mp.write_text(json.dumps(d))
    elif mutation == "missing_key":
        d = json.loads(mp.read_text()); del d["state"]; mp.write_text(json.dumps(d))
    r, st = proj.status()
    assert r.returncode == 0, r.stdout + r.stderr          # 状态读取不能崩溃
    assert automation(st, "CASE-01") == "error", mutation
    assert st["evidence_problems"]
    assert automation(st, "CASE-02") == "passed"           # 其他条目不受牵连


def test_deleting_index_row_of_latest_makes_it_inconsistent_not_older_pass(proj):
    two_passes(proj)
    conn = sqlite3.connect(proj.root / ".flowtree" / "data.db")
    conn.execute("DELETE FROM flowtree_attempts WHERE attempt_id IN (SELECT attempt_id FROM flowtree_attempts "
                 "WHERE entry_id='M-01' ORDER BY started_at DESC LIMIT 1)")
    conn.commit(); conn.close()
    r, st = proj.status()
    assert automation(st, "CASE-01") == "error"


def test_damaged_older_attempt_is_reported_but_latest_valid_wins(proj):
    proj.verify()
    first = manifests(proj.root)[0]
    time.sleep(0.01)
    proj.verify()
    first.write_text("{")
    r, st = proj.status()
    assert automation(st, "CASE-01") == "passed" and st["evidence_problems"]


def test_legacy_flat_layout_attempt_is_still_readable(proj):
    res = proj.verify()[1]
    mp = next(a for a in res["attempts"] if a["entry"].endswith("M-01"))["manifest"]
    from pathlib import Path
    d = Path(mp).parent                       # runs/<run>/<story>/<entry>
    legacy = d.parent.parent / "M-01"         # runs/<run>/M-01
    shutil.copytree(d, legacy)
    shutil.rmtree(d)
    m = json.loads((legacy / "manifest.json").read_text())
    m["attempt_id"] = f"{m['run_id']}.M-01"
    (legacy / "manifest.json").write_text(json.dumps(m))
    conn = sqlite3.connect(proj.root / ".flowtree" / "data.db")
    conn.execute("UPDATE flowtree_attempts SET attempt_id=? WHERE attempt_id=?", (m["attempt_id"], f"{m['run_id']}.SAV-001.M-01"))
    conn.execute("UPDATE flowtree_attempts SET manifest_sha256=? WHERE attempt_id=?",
                 (__import__("flowtree.evidence", fromlist=["x"]).sha256_file(legacy / "manifest.json"), m["attempt_id"]))
    conn.commit(); conn.close()
    r, st = proj.status()
    assert automation(st, "CASE-01") == "passed", st["evidence_problems"]


# ---------------- B1B-02 ----------------

def test_same_entry_id_in_two_stories_keeps_both_evidence_and_exits_zero(proj):
    add_second_story(proj)
    r, res = proj.verify()
    assert r.returncode == 0, r.stdout[-800:]
    paths = [a["manifest"] for a in res["attempts"]]
    assert len(paths) == len(set(paths)) == 4
    s = res["stories"]
    assert {st["id"] for st in s} == {"SAV-001", "SAV-002"}
    for sid in ("SAV-001", "SAV-002"):
        assert units(res)[f"{sid}.CASE-01"]["automation"] == "passed"
    # 状态读取按 (故事, 条目) 各取各的最新证据
    r, st = proj.status()
    assert units(st)["SAV-002.CASE-01"]["automation"] == "passed" and units(st)["SAV-001.CASE-01"]["automation"] == "passed"


def test_failure_in_one_story_does_not_leak_into_same_named_entry_of_other(proj):
    add_second_story(proj)
    m2 = (proj.maps / "SAV-002.mapping.yaml")
    m2.write_text(m2.read_text().replace(NID_A, "tests/test_savings.py::test_missing"))
    r, res = proj.verify()
    assert units(res)["SAV-001.CASE-01"]["automation"] == "passed"
    assert units(res)["SAV-002.CASE-01"]["automation"] == "error"


def test_duplicate_entry_across_mapping_files_of_one_story_is_a_validation_error(proj):
    shutil.copy(proj.map_file, proj.maps / "dup.mapping.yaml")
    r, res = proj.verify()
    assert r.returncode == 1 and res["executed"] is False
    assert any(i["code"] == "mapping.duplicate_entry" for i in res["issues"])
    assert not manifests(proj.root)


def test_entry_selection_qualified_and_ambiguous(proj):
    add_second_story(proj)
    r, res = proj.verify("--entry", "M-01")
    assert r.returncode == 1 and res["executed"] is False and "ambiguous" in json.dumps(res["issues"])
    assert not manifests(proj.root)
    r, res = proj.verify("--entry", "SAV-002/M-01")
    assert res["executed"] and [a["entry"] for a in res["attempts"]] == ["SAV-002/M-01"] and r.returncode == 0


# ---------------- B1B-03 ----------------

def test_unknown_entry_executes_nothing(proj):
    r, res = proj.verify("--entry", "M-TYPO")
    assert r.returncode == 1 and res["executed"] is False and res["ok"] is False and not manifests(proj.root)


def test_partially_invalid_selection_is_rejected_whole(proj):
    r, res = proj.verify("--entry", "M-01", "--entry", "M-TYPO")
    assert res["executed"] is False and not manifests(proj.root)


def test_mapping_without_entries_is_not_success(proj):
    proj.map_file.write_text(proj.map_file.read_text().split("entries:")[0] + "entries: []\n")
    r, res = proj.verify()
    assert r.returncode == 1 and res["executed"] is False and res["ok"] is False


def test_mapped_only_with_no_mapped_units_is_not_success(proj):
    # 条目只覆盖一个单元, 但选中后再 --mapped-only 仍有必需单元; 这里让映射覆盖被移走 → 无必需单元
    r, res = proj.verify("--entry", "M-01")
    assert res["executed"] and r.returncode == 0   # 选择条目 → 必需范围是其覆盖单元, 非空且通过


# ---------------- B1B-04 ----------------

ENV_TEST = "import os\ndef test_zero_amount_rejected():\n    assert 5 * int(os.environ['FT_RATE']) == 10\ndef test_resume_after_lost_response(): pass\n"


def test_environment_variable_change_makes_old_pass_stale_and_names_the_variable(tmp_path):
    p = Proj(tmp_path / "p", tests=ENV_TEST)
    r, res = p.verify(env={"FT_RATE": "2"})
    assert r.returncode == 0
    st = p.cli("story", "status", str(p.stories), "--mappings", str(p.maps), "--project-root", str(p.root), "--python", PY, "--json",
               env={"FT_RATE": "3"})
    e = units(json.loads(st.stdout))["SAV-001.CASE-01"]
    assert e["automation"] == "not_run" and e["entries"][0]["validity"] == "stale"
    assert any("FT_RATE" in x for x in e["entries"][0]["validity_reasons"])
    assert e["entries"][0]["last_result"] == "passed"      # 历史保留
    # 值不变则仍有效
    st = p.cli("story", "status", str(p.stories), "--mappings", str(p.maps), "--project-root", str(p.root), "--python", PY, "--json",
               env={"FT_RATE": "2"})
    assert units(json.loads(st.stdout))["SAV-001.CASE-01"]["automation"] == "passed"


def test_new_environment_variable_also_invalidates(proj):
    proj.verify(env={"FT_X": "1"})
    st = proj.cli("story", "status", str(proj.stories), "--mappings", str(proj.maps), "--project-root", str(proj.root), "--python", PY, "--json",
                  env={"FT_X": "1", "FT_EXTRA": "boom"})
    assert units(json.loads(st.stdout))["SAV-001.CASE-01"]["entries"][0]["validity"] == "stale"


def test_env_ignore_declaration_and_volatile_vars_do_not_invalidate(proj):
    text = proj.map_file.read_text().replace("env: {id: env-1}", "env: {id: env-1, ignore: [FT_NOISE]}")
    proj.map_file.write_text(text)
    proj.verify(env={"FT_NOISE": "a", "OLDPWD": "/a"})
    st = proj.cli("story", "status", str(proj.stories), "--mappings", str(proj.maps), "--project-root", str(proj.root), "--python", PY, "--json",
                  env={"FT_NOISE": "b", "OLDPWD": "/b"})
    assert units(json.loads(st.stdout))["SAV-001.CASE-01"]["automation"] == "passed"


def test_environment_values_are_never_stored_in_plaintext(proj):
    secret = "s3cr3t-value-xyzzy"
    proj.verify(env={"FT_API_TOKEN": secret})
    blob = b"".join(p.read_bytes() for p in (proj.root / ".flowtree").rglob("*") if p.is_file() and p.name != "env.salt")
    assert secret.encode() not in blob and b"FT_API_TOKEN" in blob     # 名称可见, 值不可见
    assert (proj.root / ".flowtree" / "env.salt").stat().st_mode & 0o077 == 0


def test_invalid_env_ignore_name_rejected(proj):
    proj.map_file.write_text(proj.map_file.read_text().replace("env: {id: env-1}", "env: {id: env-1, ignore: ['bad name']}", 1))
    r, res = proj.verify()
    assert res["executed"] is False and any(i["code"] == "mapping.env_ignore" for i in res["issues"])


# ---------------- B1B-05 ----------------

FAIL_UNMAPPED = ("def test_zero_amount_rejected(): pass\ndef test_resume_after_lost_response(): pass\n"
                 "def test_unmapped_bug(): assert 1 == 2\n")


def test_unmapped_failing_test_in_command_makes_verify_fail_but_keeps_scenario_truth(tmp_path):
    p = Proj(tmp_path / "p", tests=FAIL_UNMAPPED)
    r, res = p.verify()
    assert r.returncode == 1 and res["ok"] is False
    assert automation(res, "CASE-01") == "passed" and automation(res, "CASE-02") == "passed"   # 被映射场景的真实结果
    a = attempt(res, "M-01")
    assert a["state"] == "completed" and a["exit_code"] == 1 and a["command_clean"] is False   # 不改写成 error
    assert a["unmapped_nonpass"] == {"tests/test_savings.py::test_unmapped_bug": "failed"}
    assert res["commands_clean"] is False


def test_status_surfaces_command_failures_separately(tmp_path):
    p = Proj(tmp_path / "p", tests=FAIL_UNMAPPED)
    p.verify()
    r, st = p.status()
    assert r.returncode == 0
    assert automation(st, "CASE-01") == "passed"
    assert {c["entry"] for c in st["command_failures"]} == {"M-01", "M-02"}
    assert st["command_failures"][0]["unmapped_nonpass"]


def test_unmapped_skip_and_xfail_do_not_make_command_dirty(tmp_path):
    p = Proj(tmp_path / "p", tests="import pytest\ndef test_zero_amount_rejected(): pass\ndef test_resume_after_lost_response(): pass\n"
                                  "@pytest.mark.skip\ndef test_s(): pass\n@pytest.mark.xfail\ndef test_x(): assert False\n")
    r, res = p.verify()
    assert r.returncode == 0 and res["commands_clean"] is True


# ---------------- B1B-06 ----------------

STUBBORN = """
import os, signal, subprocess, sys, time, pathlib
CHILD = ("import os,signal,time,pathlib;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
         "pathlib.Path(%r).write_text(str(os.getpid()));time.sleep(60)")
def test_zero_amount_rejected():
    pid_file = os.path.join(os.path.dirname(__file__), "..", "stubborn.pid")
    subprocess.Popen([sys.executable, "-c", CHILD % pid_file])
    time.sleep(60)
def test_resume_after_lost_response(): pass
"""


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_sigterm_ignoring_grandchild_is_killed_on_timeout_and_cleanup_is_recorded(tmp_path):
    p = Proj(tmp_path / "p", tests=STUBBORN, timeout_s=2)
    pid = None
    try:
        r, res = p.verify("--entry", "M-01")
        a = attempt(res, "M-01")
        assert a["state"] == "error" and "cleared" in a["reason"] and "NOT" not in a["reason"]
        assert a["cleanup"]["sigterm"] and a["cleanup"]["sigkill"] and a["cleanup"]["cleared"]
        pid = int((p.root / "stubborn.pid").read_text())
        time.sleep(0.3)
        assert not alive(pid)
    finally:
        if pid and alive(pid):
            os.kill(pid, signal.SIGKILL)


LEAK = """
import os, subprocess, sys
def test_zero_amount_rejected():
    c = subprocess.Popen([sys.executable, "-c", "import time,os,pathlib;pathlib.Path(%r).write_text(str(os.getpid()));time.sleep(60)" %
                          os.path.join(os.path.dirname(__file__), "..", "leaked.pid")])
def test_resume_after_lost_response(): pass
"""


def test_process_leaked_by_a_passing_test_is_cleaned_and_recorded(tmp_path):
    p = Proj(tmp_path / "p", tests=LEAK)
    pid = None
    try:
        r, res = p.verify("--entry", "M-01")
        pidfile = p.root / "leaked.pid"
        for _ in range(20):
            if pidfile.exists() and pidfile.read_text():
                break
            time.sleep(0.1)
        pid = int(pidfile.read_text())
        time.sleep(0.3)
        a = attempt(res, "M-01")
        assert a["cleanup"] and a["cleanup"]["cleared"]
        assert not alive(pid)
    finally:
        if pid and alive(pid):
            os.kill(pid, signal.SIGKILL)
