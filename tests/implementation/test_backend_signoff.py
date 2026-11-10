import shutil
import sys

import pytest

from impl_support import ROOT

BACKEND = ROOT / "backend"


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 演示项目的 PATCH 会写回数据文件, 用副本隔离, 不触碰仓库内的演示数据
    sys.path.insert(0, str(BACKEND))
    from fastapi.testclient import TestClient
    import app.main as m
    data = tmp_path / "data"
    shutil.copytree(BACKEND / "app" / "data", data)
    monkeypatch.setattr(m, "DATA_DIR", data)
    monkeypatch.setattr(m, "PROJECT_STORE", {})
    monkeypatch.setattr(m, "PROJECT_FILES", dict(m.PROJECT_FILES))
    return TestClient(m.app), m


def first_node(m, pid):
    return m.load_project_by_id(pid).nodes[1].nodeId


def test_review_pass_rejected_for_non_demo_project_and_no_side_effects(client):
    c, m = client
    node = first_node(m, "proj-life-piggy-bank")
    r = c.patch(f"/api/projects/proj-synced-from-cli/nodes/{node}/status",
                json={"status": "review_pass", "source": "human_reviewer"})
    assert r.status_code == 403
    assert "proj-synced-from-cli" not in m.PROJECT_STORE


def test_demo_project_sign_off_is_labelled_unauthenticated(client):
    c, m = client
    node = first_node(m, "proj-life-piggy-bank")
    r = c.patch(f"/api/projects/proj-life-piggy-bank/nodes/{node}/status", json={"status": "review_pass"})
    assert r.status_code == 200
    n = next(x for x in m.PROJECT_STORE["proj-life-piggy-bank"].nodes if x.nodeId == node)
    assert n.review.humanSignOffBy == "demo-unauthenticated"


def test_logic_verified_self_report_is_labelled(client):
    c, m = client
    pid = "proj-life-piggy-bank"
    node = first_node(m, pid)
    c.patch(f"/api/projects/{pid}/nodes/{node}/status", json={"status": "logic_verified", "source": "claude"})
    n = next(x for x in m.PROJECT_STORE[pid].nodes if x.nodeId == node)
    assert n.review.logicVerifiedBy == "self-reported:claude"


def test_simulation_limited_to_demo_projects(client):
    c, _ = client
    assert c.post("/api/projects/proj-real/simulate-agent").status_code == 403
    assert c.post("/api/projects/proj-life-piggy-bank/simulate-agent").json()["demo"] is True
