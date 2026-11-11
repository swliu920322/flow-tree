"""第二批: 只读故事验收接口。证据来自真实 git 仓库里的真实 pytest 子进程执行 (b1b_support.Proj)。"""
import hashlib
import json
import os
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from b1b_support import NID_A, NID_B, PY, Proj
from impl_support import ROOT

BACKEND = ROOT / "backend"
STATIC = BACKEND / "app" / "static"


def write_workspace(tmp_path, proj, env=None, python=PY, ws_id="ws1", extra=None):
    cfg = {"workspaces": [{
        "id": ws_id, "name": "测试工作区", "project_root": str(proj.root), "python": python,
        "stories": [str(proj.stories)], "mappings": [str(proj.maps)],
        "execution_context": {"env": env or {}}, **(extra or {}),
    }]}
    p = tmp_path / "workspaces.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return p


@pytest.fixture
def api(monkeypatch):
    sys.path.insert(0, str(BACKEND))
    from fastapi.testclient import TestClient
    import app.main as m
    from flowtree import view
    view._cache.clear()
    return TestClient(m.app), view


def snapshot(root: Path):
    """目录树的完整快照: 目录集合 + 每个文件的内容哈希与大小。读取接口不得改变它。"""
    files, dirs = {}, set()
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if ".git/" in rel + "/" and rel.split("/")[0] == ".git":
            continue
        if p.is_dir():
            dirs.add(rel)
        else:
            files[rel] = (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
    return dirs, files


def unit(detail, qid):
    for st in detail["flow"]:
        if st["qid"] == qid:
            return st["unit"]
        for b in st["branches"]:
            if b["qid"] == qid:
                return b["unit"]
    raise KeyError(qid)


@pytest.fixture
def real(tmp_path, monkeypatch, api):
    """已经真实执行过一次的项目 + 指向它的工作区配置 (执行上下文与当前一致)。"""
    p = Proj(tmp_path / "p")
    r, res = p.verify()
    assert r.returncode == 0, r.stdout[-600:]
    cfg = write_workspace(tmp_path, p)
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(cfg))
    c, view = api
    view._cache.clear()
    return c, p, tmp_path


# ---------------------------------------------------------------- 结构

def test_workspace_and_story_listing(real):
    c, p, _ = real
    w = c.get("/api/workspaces").json()["workspaces"][0]
    assert w["id"] == "ws1" and w["stories"] == 1 and w["problems"] == []
    l = c.get("/api/workspaces/ws1/stories").json()
    assert [s["id"] for s in l["stories"]] == ["SAV-001"]
    assert l["stories"][0]["summary"]["units_total"] == 6 and l["stories"][0]["summary"]["complete"] is False


def test_story_detail_is_a_vertical_flow_with_branches_and_correct_continuations(real):
    c, p, _ = real
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert [s["id"] for s in d["flow"]] == ["STEP-01", "STEP-02", "STEP-03", "STEP-04"]
    step2 = d["flow"][1]
    assert [b["id"] for b in step2["branches"]] == ["CASE-01", "CASE-02"]
    b1, b2 = step2["branches"]
    assert b1["continuation"] == {"type": "end", "target": None, "target_action": None}      # 校验失败: 结束
    assert b2["continuation"]["type"] == "rejoin" and b2["continuation"]["target"] == "STEP-03"  # 恢复: 汇合主线
    assert b2["continuation"]["target_action"] == "用户查看提交结果"
    assert d["flow"][0]["branches"] == [] and d["flow"][0]["branch_summary"]["total"] == 0


def test_four_dimensions_are_independent_and_totals_expose_denominators(real):
    c, p, _ = real
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    u = unit(d, "SAV-001.CASE-01")
    assert (u["rule"], u["implementation"], u["automation"], u["human"]) == ("draft", "unchecked", "passed", "none")
    t = d["totals"]
    assert t["total"] == 6 and t["automation"]["passed"] == 3 and t["automation"]["unmapped"] == 3
    assert t["human_unverified"] == 6 and t["rule_pending"] == 0
    assert d["summary"]["complete"] is False and d["summary"]["incomplete_reasons"]
    assert "percent" not in json.dumps(d).lower() and "progressRate" not in json.dumps(d)


def test_collapsed_branch_summary_still_counts_risks(tmp_path, monkeypatch, api):
    p = Proj(tmp_path / "p")      # 从未执行: 已映射分支是"未执行", 另一个未映射
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p)))
    c, view = api; view._cache.clear()
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    bs = d["flow"][1]["branch_summary"]
    # SAV-001.STEP-02 的两个分支都已映射但从未执行: 折叠后仍可见 2 个"未执行", 不是 0 也不是"通过"
    assert bs["total"] == 2 and bs["never_run"] == 2 and bs["automation"]["unmapped"] == 0
    assert bs["attention"] == 2 and bs["outdated"] == 0 and bs["bad"] == 0 and bs["automation"]["passed"] == 0


# ---------------------------------------------------------------- 证据与有效性

def test_real_evidence_traceable_from_unit_to_nodeid_run_and_artifacts(real):
    c, p, _ = real
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    e = unit(d, "SAV-001.CASE-01")["entries"][0]
    assert e["validity"] == "current" and e["last_result"] == "passed" and e["counts_for_current"] == "passed"
    assert e["aspects"] and set(e["aspects"].values()) == {"same"}
    assert e["tests"][0]["nodeid"] == NID_A and e["tests"][0]["outcome"] == "passed"
    assert e["exit_code"] == 0 and e["command_clean"] is True
    ref = e["ref"]
    a = c.get(f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}").json()
    assert a["state"] == "completed" and a["command_clean"] and a["integrity_problems"] == []
    assert a["command"]["cwd"] == str(p.root.resolve()) and a["pytest_rootdir"] == str(p.root.resolve())
    assert {x["name"] for x in a["artifacts"]} == {"plugin_report", "junit", "stdout", "stderr"}
    j = c.get(f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}/artifacts/junit").json()
    assert "<testsuite" in j["text"] and j["sha256"].startswith("sha256:")


def test_modified_artifact_is_refused_not_shown_as_evidence(real):
    c, p, _ = real
    ref = unit(c.get("/api/workspaces/ws1/stories/SAV-001").json(), "SAV-001.CASE-01")["entries"][0]["ref"]
    junit = next((p.root / ".flowtree/runs").glob("*/*/M-01/junit.xml"))
    junit.write_text(junit.read_text() + "<!-- edited -->")
    r = c.get(f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}/artifacts/junit")
    assert r.status_code == 409 and "modified" in r.json()["detail"]
    a = c.get(f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}").json()
    assert any("junit" in x for x in a["integrity_problems"])


def test_source_change_makes_result_outdated_but_keeps_history(real):
    c, p, _ = real
    (p.root / "tests/test_savings.py").write_text("# edit\n" + (p.root / "tests/test_savings.py").read_text())
    d = c.get("/api/workspaces/ws1/stories/SAV-001?refresh=true").json()
    u = unit(d, "SAV-001.CASE-01")
    e = u["entries"][0]
    assert u["automation"] == "not_run" and e["validity"] == "stale" and e["last_result"] == "passed"
    assert e["aspects"]["worktree"] == "changed" and e["aspects"]["story"] == "same"
    assert d["totals"]["outdated"] == 3 and d["totals"]["never_run"] == 0   # 3 个已映射单元: 待更新, 而不是"从未执行"
    assert d["totals"]["automation"]["passed"] == 0


def test_environment_difference_is_reported_by_name_only_and_context_can_restore_validity(tmp_path, monkeypatch, api):
    p = Proj(tmp_path / "p")
    secret = "super-secret-value-123"
    r, res = p.verify(env={"FT_RATE": secret})
    assert r.returncode == 0
    c, view = api
    # 服务进程环境里没有 FT_RATE: 环境不同 → 待更新, 只暴露变量名
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p)))
    view._cache.clear()
    raw = c.get("/api/workspaces/ws1/stories/SAV-001").text
    d = json.loads(raw)
    e = unit(d, "SAV-001.CASE-01")["entries"][0]
    assert e["validity"] == "stale" and e["aspects"]["environment"] == "changed" and e["aspects"]["worktree"] == "same"
    assert "FT_RATE" in e["changed_env_names"] and secret not in raw
    # 工作区声明了与执行时一致的执行上下文 → 可以确认有效
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p, env={"FT_RATE": secret})))
    view._cache.clear()
    raw2 = c.get("/api/workspaces/ws1/stories/SAV-001").text
    e2 = unit(json.loads(raw2), "SAV-001.CASE-01")["entries"][0]
    assert e2["validity"] == "current" and secret not in raw2
    assert json.loads(raw2)["context"]["execution_context"]["env_names"] == ["FT_RATE"]      # 只有名称


def test_context_reports_overview_and_recheck_semantics(real):
    c, p, _ = real
    ctx = c.get("/api/workspaces/ws1/stories/SAV-001").json()["context"]
    assert ctx["validity_overview"] == {"current": 2, "stale": 0, "unknown": 0}
    assert ctx["recheck"]["can_determine_validity"] is True and "不是重新执行测试" in ctx["recheck"]["note"]
    assert ctx["checked_at"] and ctx["python"] == PY


def test_unknown_python_makes_validity_undeterminable_not_current(tmp_path, monkeypatch, api):
    p = Proj(tmp_path / "p")
    p.verify()
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p, python="/nonexistent/python")))
    c, view = api; view._cache.clear()
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    e = unit(d, "SAV-001.CASE-01")["entries"][0]
    assert e["validity"] == "unknown" and e["aspects"]["runtime"] == "unknown"
    assert d["context"]["recheck"]["can_determine_validity"] is False
    assert "runtime" in d["context"]["recheck"]["undetermined_aspects"]
    assert d["context"]["recheck"]["workspace_problems"]                  # 配置问题被如实报告
    assert unit(d, "SAV-001.CASE-01")["automation"] != "passed"


def test_corrupt_latest_manifest_is_error_with_problems_not_fallback(real):
    c, p, _ = real
    mp = next((p.root / ".flowtree/runs").glob("*/*/M-01/manifest.json"))
    mp.write_text("{")
    d = c.get("/api/workspaces/ws1/stories/SAV-001?refresh=true").json()
    assert unit(d, "SAV-001.CASE-01")["automation"] == "error" and d["evidence_problems"]
    assert unit(d, "SAV-001.CASE-02")["automation"] == "passed"


def test_unmapped_failure_in_command_is_surfaced_separately(tmp_path, monkeypatch, api):
    p = Proj(tmp_path / "p", tests="def test_zero_amount_rejected(): pass\ndef test_resume_after_lost_response(): pass\ndef test_unmapped_bug(): assert 1 == 2\n")
    p.verify()
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p)))
    c, view = api; view._cache.clear()
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert unit(d, "SAV-001.CASE-01")["automation"] == "passed"
    assert {f["entry"] for f in d["command_failures"]} == {"M-01", "M-02"}
    assert "tests/test_savings.py::test_unmapped_bug" in d["command_failures"][0]["unmapped_nonpass"]


def test_same_entry_id_in_two_stories_stays_distinct(tmp_path, monkeypatch, api):
    from test_b1b_fixes import add_second_story
    p = Proj(tmp_path / "p")
    add_second_story(p)
    r, _ = p.verify()
    assert r.returncode == 0
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p)))
    c, view = api; view._cache.clear()
    a = unit(c.get("/api/workspaces/ws1/stories/SAV-001").json(), "SAV-001.CASE-01")["entries"][0]
    b = unit(c.get("/api/workspaces/ws1/stories/SAV-002").json(), "SAV-002.CASE-01")["entries"][0]
    assert a["ref"]["story"] == "SAV-001" and b["ref"]["story"] == "SAV-002" and a["validity"] == b["validity"] == "current"


# ---------------------------------------------------------------- 只读性

def test_all_reads_leave_the_target_project_byte_identical(real):
    c, p, _ = real
    before = snapshot(p.root)
    ref = unit(c.get("/api/workspaces/ws1/stories/SAV-001").json(), "SAV-001.CASE-01")["entries"][0]["ref"]
    for url in ["/api/workspaces", "/api/workspaces/ws1/stories", "/api/workspaces/ws1/stories/SAV-001",
                "/api/workspaces/ws1/stories/SAV-001?refresh=true",
                f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}"] + [
                f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}/artifacts/{n}"
                for n in ("plugin_report", "junit", "stdout", "stderr")]:
        assert c.get(url).status_code == 200, url
    assert snapshot(p.root) == before


def test_reading_a_never_verified_project_creates_nothing_in_it(tmp_path, monkeypatch, api):
    p = Proj(tmp_path / "p")
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p)))
    c, view = api; view._cache.clear()
    before = snapshot(p.root)
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert unit(d, "SAV-001.CASE-01")["automation"] == "not_run" and d["totals"]["outdated"] == 0
    assert d["totals"]["never_run"] == 3 and d["context"]["validity_overview"] == {"current": 0, "stale": 0, "unknown": 0}
    assert snapshot(p.root) == before
    assert not (p.root / ".flowtree").exists() or not (p.root / ".flowtree" / "env.salt").exists()


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_no_write_methods_exist(real, method):
    c, p, _ = real
    for url in ["/api/workspaces", "/api/workspaces/ws1/stories", "/api/workspaces/ws1/stories/SAV-001"]:
        assert getattr(c, method)(url).status_code == 405


def test_browsing_never_executes_tests_or_creates_runs(real):
    c, p, _ = real
    runs_before = sorted(str(x) for x in (p.root / ".flowtree/runs").rglob("manifest.json"))
    (p.root / "tests/test_savings.py").write_text("open('SHOULD_NOT_EXIST.txt', 'w').write('x')\ndef test_zero_amount_rejected(): pass\ndef test_resume_after_lost_response(): pass\n")
    for _ in range(3):
        c.get("/api/workspaces/ws1/stories/SAV-001?refresh=true")
    assert not (p.root / "SHOULD_NOT_EXIST.txt").exists()      # 测试文件的任何代码都没有被运行 (模块导入也不会发生)
    assert sorted(str(x) for x in (p.root / ".flowtree/runs").rglob("manifest.json")) == runs_before


# ---------------------------------------------------------------- 输入与错误

def test_identifier_validation_and_not_found(real):
    c, p, _ = real
    assert c.get("/api/workspaces/nope/stories").status_code == 404
    assert c.get("/api/workspaces/ws1/stories/NOPE-1").status_code == 404
    assert c.get("/api/workspaces/ws1/stories/..%2Fx").status_code in (400, 404)
    assert c.get("/api/workspaces/ws1/attempts/..%2F..%2Fx/SAV-001/M-01").status_code in (400, 404)
    assert c.get("/api/workspaces/ws1/attempts/run_x/SAV-001/M-01").status_code == 404
    ref = unit(c.get("/api/workspaces/ws1/stories/SAV-001").json(), "SAV-001.CASE-01")["entries"][0]["ref"]
    base = f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}/artifacts"
    assert c.get(f"{base}/manifest").status_code == 404 and c.get(f"{base}/..%2Fmanifest.json").status_code in (400, 404)


def test_bad_workspace_config_is_reported_not_crashing(tmp_path, monkeypatch, api):
    bad = tmp_path / "w.yaml"
    bad.write_text("workspaces:\n  - id: 'bad id'\n    project_root: /x\n    stories: []\n    mappings: []\n")
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(bad))
    c, _ = api
    r = c.get("/api/workspaces")
    assert r.status_code == 500 and "workspace config error" in r.json()["detail"]


def test_missing_config_gives_empty_list(tmp_path, monkeypatch, api):
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(tmp_path / "absent.yaml"))
    c, _ = api
    assert c.get("/api/workspaces").json() == {"workspaces": []}


@pytest.mark.parametrize("cfg,msg", [
    ("workspaces:\n  - id: a\n    project_root: /x\n    stories: [s]\n", "missing mappings"),
    ("workspaces:\n  - {id: a, project_root: /x, stories: [s], mappings: [m]}\n  - {id: a, project_root: /x, stories: [s], mappings: [m]}\n", "duplicate"),
    ("workspaces:\n  - {id: a, project_root: /x, stories: [s], mappings: [m], execution_context: {env: {'BAD NAME': 1}}}\n", "valid variable names"),
    ("nothing: 1\n", "workspaces"),
])
def test_workspace_config_validation(tmp_path, cfg, msg):
    from flowtree.workspace import WorkspaceConfigError, load_workspaces
    p = tmp_path / "w.yaml"; p.write_text(cfg)
    with pytest.raises(WorkspaceConfigError, match=msg):
        load_workspaces(p)


# ---------------------------------------------------------------- 页面静态约束

def test_page_is_self_contained_and_never_issues_write_requests():
    html = (STATIC / "stories.html").read_text(encoding="utf-8")
    js = (STATIC / "stories.js").read_text(encoding="utf-8")
    css = (STATIC / "stories.css").read_text(encoding="utf-8")
    for text in (html, js, css):
        assert "http://" not in text and "https://" not in text, "page must not depend on external resources"
    assert "method:" not in js and "POST" not in js and "XMLHttpRequest" not in js
    assert "innerHTML" not in js and "outerHTML" not in js and "insertAdjacentHTML" not in js and "eval(" not in js


def test_page_route_served_and_old_view_untouched(api):
    c, _ = api
    r = c.get("/stories")
    assert r.status_code == 200 and "故事验收" in r.text and r.headers["cache-control"] == "no-store"
    assert c.get("/").status_code == 200


# ---------------------------------------------------------------- B2-01 / B2-02 回归

def _ref(c, qid="SAV-001.CASE-01"):
    return unit(c.get("/api/workspaces/ws1/stories/SAV-001").json(), qid)["entries"][0]["ref"]


def _art_url(ref, name):
    return f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}/artifacts/{name}"


def test_artifact_not_served_when_manifest_and_index_disagree_even_if_hash_matches(real):
    c, p, _ = real
    ref = _ref(c)
    stdout = next((p.root / ".flowtree/runs").glob("*/*/M-01/stdout.txt"))
    mp = stdout.parent / "manifest.json"
    stdout.write_text("forged-output")
    m = json.loads(mp.read_text())
    m["artifacts"]["stdout"]["sha256"] = "sha256:" + hashlib.sha256(b"forged-output").hexdigest()   # 与文件一致的伪造哈希
    mp.write_text(json.dumps(m))                                                                      # 不更新索引
    r = c.get(_art_url(ref, "stdout"))
    assert r.status_code == 409 and "forged-output" not in r.text and "integrity" in r.json()["detail"]
    assert c.get(_art_url(ref, "junit")).status_code == 409           # 记录不可信: 该尝试的所有产物都不作为证据提供
    d = c.get(f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}").json()
    assert d["integrity_problems"]                                   # 诊断仍可见
    assert unit(c.get("/api/workspaces/ws1/stories/SAV-001?refresh=true").json(), "SAV-001.CASE-01")["automation"] == "error"
    # 另一个条目的完好记录仍可读取
    ref2 = _ref(c, "SAV-001.CASE-02")
    assert c.get(_art_url(ref2, "junit")).status_code == 200


def test_artifact_refused_when_index_state_or_row_is_inconsistent(real):
    import sqlite3
    c, p, _ = real
    ref = _ref(c)
    conn = sqlite3.connect(p.root / ".flowtree" / "data.db")
    conn.execute("UPDATE flowtree_attempts SET state='error' WHERE entry_id='M-01'")
    conn.commit(); conn.close()
    assert c.get(_art_url(ref, "junit")).status_code == 409
    conn = sqlite3.connect(p.root / ".flowtree" / "data.db")
    conn.execute("DELETE FROM flowtree_attempts WHERE entry_id='M-01'")
    conn.commit(); conn.close()
    assert c.get(_art_url(ref, "junit")).status_code == 409


def test_intact_artifact_still_readable_and_reading_does_not_modify_it(real):
    c, p, _ = real
    ref = _ref(c)
    junit = next((p.root / ".flowtree/runs").glob("*/*/M-01/junit.xml"))
    before = (junit.read_bytes(), junit.stat().st_mtime_ns)
    assert c.get(_art_url(ref, "junit")).status_code == 200
    assert (junit.read_bytes(), junit.stat().st_mtime_ns) == before


def test_config_switch_to_another_project_never_mixes_cached_state(tmp_path, monkeypatch, api):
    c, view = api
    view._cache.clear()
    p1, p2 = Proj(tmp_path / "p1"), Proj(tmp_path / "p2")
    for p, title in ((p1, "项目一的故事"), (p2, "项目二的故事")):
        p.story_file.write_text(p.story_file.read_text(encoding="utf-8").replace("记录一次克制消费", title), encoding="utf-8")
        p.write_mapping()
    p2.verify()                                           # 只有项目二有证据
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p1)))
    d1 = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert d1["story"]["title"] == "项目一的故事" and d1["context"]["project_root"] == str(p1.root.resolve())
    assert d1["totals"]["never_run"] == 3
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p2)))   # 同一 id, 不同项目; 不强制刷新
    d2 = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert d2["story"]["title"] == "项目二的故事" and d2["context"]["project_root"] == str(p2.root.resolve())
    assert d2["totals"]["never_run"] == 0 and unit(d2, "SAV-001.CASE-01")["entries"][0]["has_evidence"]
    assert c.get("/api/workspaces/ws1/stories").json()["stories"][0]["title"] == "项目二的故事"
    assert c.get("/api/workspaces").json()["workspaces"][0]["project_root"] == str(p2.root.resolve())


@pytest.mark.parametrize("change", ["python", "env", "git_excludes", "mappings"])
def test_any_result_affecting_config_change_invalidates_cache(tmp_path, monkeypatch, api, change):
    c, view = api
    view._cache.clear()
    p = Proj(tmp_path / "p")
    p.verify(env={"FT_RATE": "2"})
    base = dict(env={"FT_RATE": "2"})
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p, **base)))
    e = unit(c.get("/api/workspaces/ws1/stories/SAV-001").json(), "SAV-001.CASE-01")["entries"][0]
    assert e["validity"] == "current"                      # 与执行时一致的上下文
    excl = tmp_path / "excl"; excl.write_text("\n")
    if change == "python":
        cfg = write_workspace(tmp_path, p, env={"FT_RATE": "2"}, python="/nonexistent/python")
    elif change == "env":
        cfg = write_workspace(tmp_path, p, env={"FT_RATE": "3"})
    elif change == "git_excludes":
        cfg = write_workspace(tmp_path, p, env={"FT_RATE": "2"}, extra={"execution_context": {"env": {"FT_RATE": "2"}, "git_excludes_file": str(excl)}})
    else:
        empty = tmp_path / "empty_maps"; empty.mkdir()
        cfg = write_workspace(tmp_path, p, env={"FT_RATE": "2"}, extra={"mappings": [str(empty)]})
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(cfg))
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()          # 不强制刷新: 不能再得到旧的 current
    e2 = unit(d, "SAV-001.CASE-01")["entries"]
    assert not e2 or e2[0]["validity"] != "current"


def test_cache_still_serves_same_config_within_ttl_and_refresh_bypasses_it(real, monkeypatch):
    c, p, _ = real
    from flowtree import view
    calls = []
    orig = view._build
    monkeypatch.setattr(view, "_build", lambda ws: (calls.append(1), orig(ws))[1])
    view._cache.clear()
    c.get("/api/workspaces/ws1/stories/SAV-001"); c.get("/api/workspaces/ws1/stories/SAV-001"); c.get("/api/workspaces/ws1/stories")
    assert len(calls) == 1                                  # 20 秒内同配置仍用缓存
    c.get("/api/workspaces/ws1/stories/SAV-001?refresh=true")
    assert len(calls) == 2                                  # 显式刷新仍可用
    assert len(view._cache) == 1                            # 同一 id 的旧配置结果被淘汰, 不无限增长


# ---------------------------------------------------------------- 验证层级 (映射声明的 level / runner)

def _entries(detail):
    out = {}
    for st in detail["flow"]:
        for u in [st["unit"]] + [b["unit"] for b in st["branches"]]:
            for e in u["entries"]:
                out[e["entry"]] = e
    return out


def test_entries_expose_declared_level_and_runner(real):
    c, p, _ = real
    es = _entries(c.get("/api/workspaces/ws1/stories/SAV-001").json())
    assert set(es) == {"M-01", "M-02"}
    for e in es.values():
        assert (e["level"], e["runner"]) == ("backend", "pytest")
    assert es["M-01"]["tests"][0]["nodeid"].endswith("test_zero_amount_rejected")      # 完整测试名与运行入口仍在
    assert es["M-01"]["ref"]["entry"] == "M-01"


def test_level_is_the_mapping_declaration_and_does_not_change_the_recorded_result(real):
    c, p, _ = real
    from flowtree import view
    before = _entries(c.get("/api/workspaces/ws1/stories/SAV-001").json())
    text = p.map_file.read_text()
    assert text.count("level: backend") == 2
    p.map_file.write_text(text.replace("level: backend", "level: e2e", 1))              # 只改 M-01 的声明
    view._cache.clear()
    after = _entries(c.get("/api/workspaces/ws1/stories/SAV-001").json())
    assert (after["M-01"]["level"], after["M-02"]["level"]) == ("e2e", "backend")
    assert after["M-01"]["last_result"] == before["M-01"]["last_result"] == "passed"    # 已记录的结果不因层级字段而被改写
    assert after["M-02"]["validity"] == before["M-02"]["validity"] == "current"         # 未改动的条目判定不变


def test_entry_removed_from_mapping_no_longer_appears_with_a_declaration(real):
    c, p, _ = real
    from flowtree import view
    text = p.map_file.read_text()
    head, _, rest = text.partition("  - id: M-02")
    p.map_file.write_text(head)                                                         # 删掉 M-02 条目
    view._cache.clear()
    es = _entries(c.get("/api/workspaces/ws1/stories/SAV-001").json())
    assert es["M-01"]["level"] == "backend"
    assert "M-02" not in es      # 映射里已没有的条目不会作为条目出现, 因此不会带出过期的声明
