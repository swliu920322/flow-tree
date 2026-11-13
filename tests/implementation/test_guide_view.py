"""第二步: 工作区配置 -> 共享视图 -> 只读接口/CLI 中的人工验收指引。
指引放在被测项目根之外 (与当前示例一致); 不得改变故事摘要、证据有效性、自动化结果或人工状态。"""
import copy
import json
import subprocess
import sys

import pytest
import yaml

from b1b_support import Proj
from impl_support import ROOT
from test_b2_stories_api import api, unit, write_workspace  # noqa: F401  (api fixture)

from flowtree.guide import CURRENT
from flowtree.workspace import load_workspaces


def _guide_for(proj, tmp_path):
    from flowtree.story import load_story_file
    ls = load_story_file(proj.story_file)
    s = ls.story
    steps = [{"for": u, "account": "alice", "do": f"做 {u}", "see": f"看到 {u}", "if_not": "原样记录"} for u in s.unit_ids()[:2]]
    g = {"schema_version": "0.1", "story": "SAV-001", "story_digest": ls.digest,
         "environment": {"summary": "隔离环境", "start": ["run.sh"]},
         "accounts": [{"username": "alice", "display_name": "爱丽丝", "password": "pw-iso", "purpose": "验收"}],
         "steps": steps, "auxiliary": [{"for": s.unit_ids()[-1], "text": "后台核对", "note": "不是界面"}]}
    gd = tmp_path / "guides"; gd.mkdir(exist_ok=True)
    f = gd / "sav-001.guide.yaml"
    f.write_text(yaml.safe_dump(g, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return f, g


@pytest.fixture
def env(tmp_path, monkeypatch, api):
    c, view = api
    p = Proj(tmp_path / "p")
    assert p.verify()[0].returncode == 0
    gfile, g = _guide_for(p, tmp_path)
    cfgfile = write_workspace(tmp_path, p, extra={"guides": [str(gfile)]})
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(cfgfile))
    view._cache.clear()
    return c, view, p, gfile, g, cfgfile


def _nodes(d):
    for st in d["flow"]:
        yield st
        yield from st["branches"]


def _strip(d):
    d = copy.deepcopy(d)
    d.pop("guide", None)
    for n in _nodes(d):
        n.pop("guide", None)
    d["context"].pop("checked_at", None)
    return d


def test_current_guide_is_attached_near_nodes_with_accounts(env):
    c, view, p, gfile, g, _ = env
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    gi = d["guide"]
    assert gi["configured"] and gi["present"] and gi["usable"] and gi["status"] == CURRENT
    assert gi["accounts"][0]["password"] == "pw-iso" and gi["environment"]["start"] == ["run.sh"]
    by = {n["id"]: n for n in _nodes(d)}
    first = g["steps"][0]["for"]
    assert by[first]["guide"]["step"]["do"] == f"做 {first}"
    aux_unit = g["auxiliary"][0]["for"]
    assert by[aux_unit]["guide"]["auxiliary"][0]["text"] == "后台核对"


def test_no_guides_configured_is_normal_default(tmp_path, monkeypatch, api):
    c, view = api
    p = Proj(tmp_path / "p")
    assert p.verify()[0].returncode == 0
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p)))
    view._cache.clear()
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert d["guide"] == {"configured": False}
    assert not any("guide" in n for n in _nodes(d))


def test_story_change_shows_guide_pending_and_hides_steps(env):
    c, view, p, gfile, g, _ = env
    d0 = yaml.safe_load(p.story_file.read_text(encoding="utf-8"))
    d0["main_flow"][0]["expected"].append("新增的预期")
    p.story_file.write_text(yaml.safe_dump(d0, allow_unicode=True, sort_keys=False), encoding="utf-8")
    view._cache.clear()
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    gi = d["guide"]
    assert gi["status"] == "stale" and gi["usable"] is False and "accounts" not in gi
    assert any(i["code"] == "guide.story_changed" for i in gi["issues"])
    assert not any("guide" in n for n in _nodes(d))


def test_broken_guide_file_is_visible_not_silent(env):
    c, view, p, gfile, g, _ = env
    gfile.write_text("story: [unclosed\n", encoding="utf-8")
    view._cache.clear()
    gi = c.get("/api/workspaces/ws1/stories/SAV-001").json()["guide"]
    assert gi["configured"] and gi["present"] is False
    assert any(i["code"] == "guide.yaml" for i in gi["problems"])


def test_invalid_reference_marks_invalid_and_hides_steps(env):
    c, view, p, gfile, g, _ = env
    g2 = copy.deepcopy(g); g2["steps"][0]["for"] = "STEP-99"
    gfile.write_text(yaml.safe_dump(g2, allow_unicode=True, sort_keys=False), encoding="utf-8")
    view._cache.clear()
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert d["guide"]["status"] == "invalid" and not d["guide"]["usable"]
    assert not any("guide" in n for n in _nodes(d))


def test_guide_changes_never_alter_story_evidence_or_human_state(env):
    c, view, p, gfile, g, _ = env
    before = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    listing0 = c.get("/api/workspaces/ws1/stories").json()
    g2 = copy.deepcopy(g); g2["steps"][0]["see"] = "只改了文案"; g2["accounts"][0]["display_name"] = "改名"
    gfile.write_text(yaml.safe_dump(g2, allow_unicode=True, sort_keys=False), encoding="utf-8")
    view._cache.clear()
    after = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert _strip(before) == _strip(after)                       # 摘要、证据有效性、各维度状态均不变
    assert before["story"]["digest"] == after["story"]["digest"]
    listing1 = c.get("/api/workspaces/ws1/stories").json()
    assert [s["summary"] for s in listing0["stories"]] == [s["summary"] for s in listing1["stories"]]
    assert all(n["unit"]["human"] == "none" for n in _nodes(after))
    # 指引损坏也不改写自动化结果
    gfile.write_text("story: [unclosed\n", encoding="utf-8"); view._cache.clear()
    broken = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert _strip(before) == _strip(broken)


def test_workspace_config_guides_parsing_and_cache_identity(tmp_path):
    base = {"id": "w", "project_root": str(tmp_path), "stories": [str(tmp_path)], "mappings": [str(tmp_path)]}
    def load(extra):
        f = tmp_path / "w.yaml"
        f.write_text(yaml.safe_dump({"workspaces": [{**base, **extra}]}), encoding="utf-8")
        return load_workspaces(f)["w"]
    assert load({}).guides == []
    assert [str(x) for x in load({"guides": str(tmp_path / "g")}).guides] == [str(tmp_path / "g")]
    ws = load({"guides": [str(tmp_path / "missing")]})
    assert ws.problems() == [] or all("guide" not in x for x in ws.problems())   # 指引路径不进入执行/有效性问题
    from flowtree import view
    assert view.cache_key(load({})) != view.cache_key(load({"guides": [str(tmp_path / "g")]}))
    from flowtree.workspace import WorkspaceConfigError
    with pytest.raises(WorkspaceConfigError):
        load({"guides": [1]})


def _cli(cfg, *args):
    r = subprocess.run([sys.executable, "-m", "cli.main", "ws", "guides", "ws1", "--config", str(cfg), *args],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout


def test_cli_ws_guides_current_stale_and_default(env, tmp_path):
    c, view, p, gfile, g, cfg = env
    rc, out = _cli(cfg)
    assert rc == 0 and "当前可用" in out
    rc, out = _cli(cfg, "--json")
    assert rc == 0 and json.loads(out)["guides"]["SAV-001"]["status"] == "current"
    d0 = yaml.safe_load(p.story_file.read_text(encoding="utf-8")); d0["main_flow"][0]["expected"].append("变了")
    p.story_file.write_text(yaml.safe_dump(d0, allow_unicode=True, sort_keys=False), encoding="utf-8")
    rc, out = _cli(cfg)
    assert rc == 1 and "待核对" in out
    other = tmp_path / "x"; other.mkdir()
    rc, out = _cli(write_workspace(other, p))
    assert rc == 0 and "未配置指引" in out


def test_shipped_workspace_guides_match_page_data():
    """示例指引经共享视图的载荷与 CLI 校验看到的是同一个状态。"""
    from flowtree import service
    res = service.check_guides([ROOT / "examples" / "stories"], [ROOT / "examples" / "guides"])
    assert res["ok"] and {k: v["status"] for k, v in res["guides"].items()} == {"TASK-A-002": "current", "TASK-B-001": "current"}
    assert "steps" not in res["guides"]["TASK-A-002"]


def test_missing_guide_path_is_reported_but_never_pollutes_automation(env):
    c, view, p, gfile, g, cfg = env
    ok = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    ws_cfg = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    ws_cfg["workspaces"][0]["guides"] = [str(gfile.parent / "nope.guide.yaml")]
    cfg.write_text(yaml.safe_dump(ws_cfg, allow_unicode=True), encoding="utf-8")
    view._cache.clear()
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert d["context"]["recheck"] == ok["context"]["recheck"]            # 能否判定有效性不受影响
    assert d["context"]["recheck"]["can_determine_validity"] is True
    assert d["context"]["recheck"]["workspace_problems"] == []
    assert _strip(ok)["flow"] == _strip(d)["flow"]                          # 各维度状态不变
    assert c.get("/api/workspaces").json()["workspaces"][0]["problems"] == []
    assert d["guide"]["configured"] and d["guide"]["present"] is False
    assert d["guide"]["problems"], "missing guide path must still be reported"
    rc, out = _cli(cfg)
    assert rc == 1 and "guide.yaml" in out


def test_ws_guides_json_default_is_structured(tmp_path, env):
    c, view, p, gfile, g, cfg = env
    other = tmp_path / "y"; other.mkdir()
    rc, out = _cli(write_workspace(other, p), "--json")
    j = json.loads(out)
    assert rc == 0 and j["ok"] is True and j["configured"] is False and j["guides"] == {} and j["message"]
    rc, out = _cli(write_workspace(other, p))
    assert rc == 0 and "未配置指引" in out
