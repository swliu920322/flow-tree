"""Codex 第一轮独立审查 F01-F05 及同源问题的实现方回归测试 (独立断言在 tests/independent, 不在此处)。"""
import copy
import shutil
import subprocess
import sys

import pytest

from impl_support import FIXTURES, ROOT
from flowtree import service
from flowtree.canon import YamlLoadError, content_digest
from flowtree.status import Auto, combine
from flowtree.story import load_story_file

BACKEND = ROOT / "backend"


@pytest.fixture
def api(tmp_path, monkeypatch):
    sys.path.insert(0, str(BACKEND))
    from fastapi.testclient import TestClient
    import app.main as m
    data = tmp_path / "data"
    shutil.copytree(BACKEND / "app" / "data", data)
    monkeypatch.setattr(m, "DATA_DIR", data)
    monkeypatch.setattr(m, "PROJECT_STORE", {})
    monkeypatch.setattr(m, "PROJECT_FILES", dict(m.PROJECT_FILES))
    return TestClient(m.app), m, data


def payload(m, pid="proj-real"):
    p = copy.deepcopy(m.load_project_by_id("proj-life-piggy-bank").model_dump(mode="json"))
    p["projectId"] = pid
    for n in p["nodes"]:
        n["status"] = "pending_dev"
        n["review"] = {}
    return p


# ---- F01 / F02 ----

@pytest.mark.parametrize("mutate", [
    lambda n: n.update(status="review_pass"),
    lambda n: n["review"].update(humanSignOff=True),
    lambda n: n["review"].update(humanSignOffBy="someone"),
    lambda n: n["review"].update(humanSignOffAt="2026-01-01T00:00:00"),
])
def test_sync_rejects_any_human_acceptance_carrier(api, mutate):
    c, m, _ = api
    p = payload(m)
    mutate(p["nodes"][1])
    r = c.post("/api/projects/sync", json=p)
    assert r.status_code == 422 and p["nodes"][1]["nodeId"] in r.text
    assert "proj-real" not in m.PROJECT_STORE


def test_sync_of_clean_project_still_works_and_cannot_be_signed_by_patch(api):
    c, m, _ = api
    p = payload(m)
    assert c.post("/api/projects/sync", json=p).status_code == 200
    nid = p["nodes"][1]["nodeId"]
    assert c.patch(f"/api/projects/proj-real/nodes/{nid}/status", json={"status": "review_pass"}).status_code == 403


@pytest.mark.parametrize("pid", ["proj-life-piggy-bank", "proj-mall-001"])
def test_demo_ids_are_reserved_against_sync(api, pid):
    c, m, data = api
    before = (data / m.PROJECT_FILES[pid]).read_bytes()
    assert c.post("/api/projects/sync", json=payload(m, pid)).status_code == 409
    assert (data / m.PROJECT_FILES[pid]).read_bytes() == before


@pytest.mark.parametrize("pid", ["../escape", "a/b", "..", "x" * 200, "a b"])
def test_sync_rejects_unsafe_project_ids(api, pid):
    c, m, data = api
    assert c.post("/api/projects/sync", json=payload(m, pid)).status_code == 422
    assert not list(data.parent.glob("escape*"))


def test_unknown_project_never_falls_back_to_demo_data(api):
    c, m, data = api
    demo = data / "life_piggy_bank.json"
    before = demo.read_bytes()
    node = m.load_project_by_id("proj-life-piggy-bank").nodes[1].nodeId
    assert c.patch(f"/api/projects/proj-unknown/nodes/{node}/status", json={"status": "logic_verified"}).status_code == 404
    assert c.get("/api/projects/proj-unknown/canvas").status_code == 404
    assert demo.read_bytes() == before


# ---- F03 ----

def test_empty_story_dir_fails_in_service_and_cli(tmp_path):
    r = service.validate([tmp_path])
    assert r["ok"] is False and r["issues"][0]["code"] == "story.no_files"
    assert service.plan([tmp_path])["ok"] is False
    out = subprocess.run([sys.executable, "-m", "cli.main", "story", "validate", str(tmp_path)],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 1


def test_empty_mapping_dir_is_distinct_from_no_mapping(tmp_path):
    stories = tmp_path / "s"; stories.mkdir()
    shutil.copy(FIXTURES / "sav-001.story.yaml", stories)
    empty = tmp_path / "m"; empty.mkdir()
    assert service.validate([stories])["ok"] is True                      # 未提供映射
    r = service.validate([stories], [empty])                               # 提供了却没发现文件
    assert r["ok"] is False and "mapping.no_files" in [i["code"] for i in r["issues"]]


# ---- F04 ----

def test_nfc_collision_in_story_file_is_reported(tmp_path):
    p = tmp_path / "s.yaml"
    text = (FIXTURES / "sav-001.story.yaml").read_text(encoding="utf-8").replace(
        "  category: 数码消费\n", "  é: a\n  é: b\n")
    p.write_text(text, encoding="utf-8")
    assert "story.yaml" in [i.code for i in load_story_file(p).issues]


def test_nfc_collision_nested_and_ok_case():
    with pytest.raises(YamlLoadError):
        content_digest({"a": [{"é": 1, "é": 2}]})
    content_digest({"é": 1, "x": 2})  # 无冲突正常


# ---- F05 ----

def test_combine_never_swallows_unmapped():
    assert combine([Auto.PASSED, Auto.UNMAPPED]) == Auto.UNMAPPED
    assert combine([Auto.UNMAPPED, Auto.NOT_RUN]) == Auto.NOT_RUN
    assert combine([Auto.FAILED, Auto.UNMAPPED]) == Auto.FAILED
    assert combine([Auto.PASSED]) == Auto.PASSED
