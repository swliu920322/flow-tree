"""用真实 Chrome 渲染页面并检查最终 DOM: 验证纵向流程、分支文案、折叠统计与详情抽屉。
需要本机 Chrome (可用 FLOWTREE_CHROME 指定路径); 没有时整组测试明确跳过并说明原因 —— 这是环境缺失, 不是通过。"""
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

import pytest

from b1b_support import PY, Proj
from impl_support import ROOT
from test_b2_stories_api import write_workspace

CHROME = os.environ.get("FLOWTREE_CHROME") or next(
    (p for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("google-chrome") or "",
                 shutil.which("chromium") or "") if p and os.path.exists(p)), None)
pytestmark = pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium found (set FLOWTREE_CHROME); browser rendering not verified")


@pytest.fixture
def server(tmp_path, monkeypatch):
    import uvicorn
    sys.path.insert(0, str(ROOT / "backend"))
    import app.main as m
    from flowtree import view
    p = Proj(tmp_path / "p")
    assert p.verify()[0].returncode == 0
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(write_workspace(tmp_path, p)))
    view._cache.clear()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(m.app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True); t.start()
    for _ in range(100):
        if srv.started: break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", p
    srv.should_exit = True; t.join(5)


def dom(url, extra=()):
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=8000",
                        "--dump-dom", *extra, url], capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stderr[-500:]
    return r.stdout


def text_of(html):
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_default_view_collapsed_keeps_risk_counts_and_vertical_order(server):
    url, p = server
    t = text_of(dom(f"{url}/stories#/ws1/SAV-001"))
    assert "整体未完成" in t and "已定义 6 个场景" in t and "本次通过 3" in t and "未映射 3" in t
    assert "人工未验收 6" in t and "规则仍为草稿 6" in t
    assert (t.index("用户打开克制记录弹窗") < t.index("用户选择分类，输入金额并确认提交")
            < t.index("用户查看提交结果") < t.index("用户离开页面后重新进入"))
    assert "+ 2 个分支" in t and "通过 2" in t                    # 折叠时分支数量与概况仍在
    assert "服务端处理成功但客户端未收到响应" not in t              # 默认不展开分支内容
    assert "null" not in t and "[object" not in t and "undefined" not in t


def test_expanded_view_shows_end_and_rejoin_and_ids_toggle(server):
    url, p = server
    t = text_of(dom(f"{url}/stories?all=1&ids=1#/ws1/SAV-001"))
    assert "金额为 0" in t and "服务端处理成功但客户端未收到响应" in t
    assert "本次操作到此结束" in t                              # end
    assert "处理后汇合到第 3 步「用户查看提交结果」" in t          # rejoin 指向主线
    assert "STEP-02" in t and "CASE-02" in t
    shown = dom(f"{url}/stories?all=1&ids=1#/ws1/SAV-001")
    hidden = dom(f"{url}/stories?all=1#/ws1/SAV-001")
    assert re.search(r"<body[^>]*class=\"show-ids\"", shown) and not re.search(r"<body[^>]*show-ids", hidden)  # 默认弱化 ID


def test_drawer_traces_scenario_to_nodeid_run_and_validity_and_states_unmapped_is_not_a_defect(server):
    url, p = server
    t = text_of(dom(f"{url}/stories?open=CASE-01&run=1#/ws1/SAV-001"))
    assert "tests/test_savings.py::test_zero_amount_rejected" in t and "run_" in t
    assert "对当前上下文 有效" in t and "pytest rootdir" in t and "manifest 与索引一致，产物哈希已核对" in t
    t2 = text_of(dom(f"{url}/stories?open=STEP-01#/ws1/SAV-001"))
    assert "不表示项目缺少测试，也不是业务缺陷" in t2


def test_stale_evidence_is_labelled_outdated_not_passed(server):
    url, p = server
    (p.root / "tests/test_savings.py").write_text("# edited\n" + (p.root / "tests/test_savings.py").read_text())
    t = text_of(dom(f"{url}/stories#/ws1/SAV-001"))
    assert "本次通过 0" in t and "待更新 3" in t
    assert "工作区代码不同" in t
    t2 = text_of(dom(f"{url}/stories?all=1&risk=1#/ws1/SAV-001"))
    assert "自动验证 待更新" in t2


def test_risk_filter_hides_fully_passing_steps_only(server):
    url, p = server
    t = text_of(dom(f"{url}/stories?risk=1#/ws1/SAV-001"))
    assert "用户选择分类，输入金额并确认提交" in t               # 自身未映射 → 保留
    assert "金额为 0" not in t and "服务端处理成功" not in t     # 两个分支本次都已通过 → 不列出
    assert "用户查看提交结果" not in t                          # 本次通过且无分支 → 隐藏
    assert "用户打开克制记录弹窗" in t and "用户离开页面后重新进入" in t   # 未映射的步骤是未覆盖项, 保留


def test_drawer_shows_declared_level_labels_without_claiming_wider_acceptance(server):
    url, p = server
    t = text_of(dom(f"{url}/stories?open=CASE-01#/ws1/SAV-001"))
    assert "验证层级 后端验证（映射声明）· runner：pytest" in t
    assert "不能说明所有角色界面、真机或生产环境已验收" in t
    assert "tests/test_savings.py::test_zero_amount_rejected" in t       # 完整测试名仍在
    assert "对当前上下文 有效" in t and "最近结果 通过" in t              # 最近结果与证据有效性仍独立显示
    assert "人工" in t and "规则" in t                                    # 规则/人工维度仍在
    assert "null" not in t and "[object" not in t and "undefined" not in t


def test_drawer_labels_client_and_e2e_levels_from_the_mapping_declaration(server):
    url, p = server
    text = p.map_file.read_text()
    p.map_file.write_text(text.replace("level: backend", "level: client", 1).replace("level: backend", "level: e2e", 1))
    from flowtree import view
    view._cache.clear()
    t1 = text_of(dom(f"{url}/stories?open=CASE-01#/ws1/SAV-001"))
    assert "验证层级 客户端验证（映射声明）· runner：pytest" in t1
    t2 = text_of(dom(f"{url}/stories?open=CASE-02#/ws1/SAV-001"))
    assert "验证层级 联调（映射声明）· runner：pytest" in t2
