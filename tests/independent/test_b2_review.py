"""B2 独立接口断言；不复用实现方 fixture。"""
import hashlib
import json
from pathlib import Path
import sys

import pytest
import yaml

from test_b1b_review import IndependentProject

ROOT = Path(__file__).resolve().parents[2]


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(ROOT / "backend"))
    import app.main as main
    from flowtree import view
    project = IndependentProject(tmp_path / "project")
    config = tmp_path / "workspaces.yaml"
    config.write_text(yaml.safe_dump({"workspaces": [{
        "id": "independent", "name": "独立验收", "project_root": str(project.root),
        "python": sys.executable, "stories": [str(project.stories)], "mappings": [str(project.maps)],
    }]}), encoding="utf-8")
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(config))
    view._cache.clear()
    with TestClient(main.app) as client:
        yield client, project
    view._cache.clear()


def test_reading_unrun_project_is_completely_readonly(api):
    client, project = api
    before = snapshot(project.root)
    response = client.get("/api/workspaces/independent/stories/INDEPENDENT-A?refresh=true")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["flow"][0]["unit"]["automation"] == "not_run"
    assert detail["flow"][0]["unit"]["human"] == "none"
    assert not (project.root / ".flowtree").exists()
    assert snapshot(project.root) == before


def test_get_story_and_artifact_preserve_every_target_file(api):
    client, project = api
    run, execution = project.cli()
    assert run.returncode == 0, execution
    before = snapshot(project.root)
    detail = client.get("/api/workspaces/independent/stories/INDEPENDENT-A?refresh=true").json()
    entry = detail["flow"][0]["unit"]["entries"][0]
    assert entry["last_result"] == "passed"
    assert detail["flow"][0]["unit"]["human"] == "none"
    base = f"/api/workspaces/independent/attempts/{entry['run_id']}/INDEPENDENT-A/M-01"
    assert client.get(base).status_code == 200
    assert client.get(base + "/artifacts/junit").status_code == 200
    assert snapshot(project.root) == before


def test_artifact_with_tampered_manifest_is_not_trusted_even_if_hash_matches(api):
    client, project = api
    run, execution = project.cli()
    assert run.returncode == 0, execution
    manifest_path = Path(execution["attempts"][0]["manifest"])
    manifest = json.loads(manifest_path.read_text())
    stdout = manifest_path.parent / manifest["artifacts"]["stdout"]["path"]
    stdout.write_text("independent-forged-output", encoding="utf-8")
    manifest["artifacts"]["stdout"]["sha256"] = "sha256:" + hashlib.sha256(stdout.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    base = f"/api/workspaces/independent/attempts/{execution['run_id']}/INDEPENDENT-A/M-01"
    detail = client.get(base)
    assert detail.status_code == 200 and detail.json()["integrity_problems"]
    artifact = client.get(base + "/artifacts/stdout")
    assert artifact.status_code == 409, artifact.text
    assert "independent-forged-output" not in artifact.text


def test_workspace_config_switch_cannot_reuse_other_project_cache(tmp_path):
    from flowtree import view
    from flowtree.workspace import Workspace
    first = IndependentProject(tmp_path / "first")
    second = IndependentProject(tmp_path / "second")
    from flowtree.canon import content_digest
    story_path = second.stories / "INDEPENDENT-A.yaml"
    raw = yaml.safe_load(story_path.read_text())
    raw["title"] = "第二个项目的独立故事"
    second.write(story_path, raw)
    mapping_path = second.maps / "INDEPENDENT-A.yaml"
    mapping = yaml.safe_load(mapping_path.read_text())
    mapping["story_digest"] = content_digest(raw)
    second.write(mapping_path, mapping)
    original = Workspace("same-id", "original", first.root, sys.executable, [first.stories], [first.maps])
    changed = Workspace("same-id", "changed", second.root, sys.executable, [second.stories], [second.maps])
    view._cache.clear()
    try:
        a = view.story_detail(original, "INDEPENDENT-A")
        b = view.story_detail(changed, "INDEPENDENT-A")
        assert a["context"]["project_root"] == str(first.root)
        assert b["context"]["project_root"] == str(second.root), b
        assert b["story"]["title"] == "第二个项目的独立故事", b
    finally:
        view._cache.clear()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_story_routes_reject_writes(api, method):
    client, project = api
    before = snapshot(project.root)
    response = client.request(method, "/api/workspaces/independent/stories/INDEPENDENT-A")
    assert response.status_code == 405
    assert snapshot(project.root) == before
