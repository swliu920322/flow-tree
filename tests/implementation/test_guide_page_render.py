"""真实 Chrome 渲染: 指引区块在页面上的可见内容 (没有 Chrome 时明确跳过, 不是通过)。"""
import socket
import sys
import threading
import time

import pytest
import yaml

from b1b_support import Proj
from impl_support import ROOT
from test_b2_page_render import CHROME, dom, text_of
from test_b2_stories_api import write_workspace
from test_guide_view import _guide_for

pytestmark = pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium found (set FLOWTREE_CHROME); browser rendering not verified")


@pytest.fixture
def gserver(tmp_path, monkeypatch):
    import uvicorn
    sys.path.insert(0, str(ROOT / "backend"))
    import app.main as m
    from flowtree import view
    p = Proj(tmp_path / "p")
    assert p.verify()[0].returncode == 0
    gfile, g = _guide_for(p, tmp_path)
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p, extra={"guides": [str(gfile)]})))
    view._cache.clear()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(m.app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True); t.start()
    for _ in range(100):
        if srv.started: break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", p, gfile, g, view
    srv.should_exit = True; t.join(5)


def test_current_guide_shows_accounts_steps_and_aux_without_actions(gserver):
    url, p, gfile, g, view = gserver
    html = dom(f"{url}/stories?all=1#/ws1/SAV-001")
    t = text_of(html)
    assert "人工验收指引（只读，不代表已验收）" in t and "隔离环境" in t
    assert "alice" in t and "爱丽丝" in t and "pw-iso" in t
    first = g["steps"][0]["for"]
    assert f"做 {first}" in t and f"看到 {first}" in t and "不一致怎么办" in t and "原样记录" in t
    assert "辅助核对（不是你在界面上看到的）" in t and "后台核对" in t
    assert "run.sh" in t and "仅文字，不可在此执行" in t
    assert "人工未验收 6" in t                                   # 人工状态不变
    assert "通过/不通过" not in t and "签字" not in t and "确认验收" not in t
    assert "null" not in t and "[object" not in t and "undefined" not in t


def test_stale_guide_shows_pending_and_no_steps(gserver):
    url, p, gfile, g, view = gserver
    d0 = yaml.safe_load(p.story_file.read_text(encoding="utf-8")); d0["main_flow"][0]["expected"].append("新增的预期")
    p.story_file.write_text(yaml.safe_dump(d0, allow_unicode=True, sort_keys=False), encoding="utf-8")
    view._cache.clear()
    t = text_of(dom(f"{url}/stories?all=1#/ws1/SAV-001"))
    assert "待核对：故事内容在指引写成之后发生了变化" in t and "guide.story_changed" in t
    assert "pw-iso" not in t and "你做什么" not in t


def test_broken_guide_is_reported_on_page(gserver):
    url, p, gfile, g, view = gserver
    gfile.write_text("story: [unclosed\n", encoding="utf-8"); view._cache.clear()
    t = text_of(dom(f"{url}/stories?all=1#/ws1/SAV-001"))
    assert "指引配置存在以下问题" in t and "guide.yaml" in t
