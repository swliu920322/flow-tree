"""固定上下文的独立真实子进程验收。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from test_b1b_review import IndependentProject, ROOT, unit


@pytest.fixture
def pinned(tmp_path):
    project = IndependentProject(tmp_path / "project", source=(
        "import os,pathlib\ndef test_total():\n"
        "    assert 'REVIEW_UNDECLARED' not in os.environ\n"
        "    assert os.environ['REVIEW_VALUE'] == '7'\n"
        "    assert os.environ['REVIEW_CREDENTIAL'] == 'test-only-credential-739'\n"
        "    pathlib.Path('.flowtree/started').write_text('ran')\n"
    ))
    config = tmp_path / "workspace.yaml"
    row = {"id": "review", "project_root": str(project.root), "python": sys.executable,
           "stories": [str(project.stories)], "mappings": [str(project.maps)],
           "execution_context": {"mode": "pinned", "env": {"REVIEW_VALUE": "7"},
                                 "env_from_host": ["REVIEW_CREDENTIAL"]}}
    def save():
        config.write_text(yaml.safe_dump({"workspaces": [row]}), encoding="utf-8")
    def call(verb, overrides=None):
        env = {**os.environ, "REVIEW_CREDENTIAL": "test-only-credential-739", **(overrides or {})}
        env = {k: v for k, v in env.items() if v is not None}
        cmd = [sys.executable, "-m", "cli.main", "workspace", verb, "review", "--config", str(config), "--json"]
        result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=40)
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            payload = {"raw": result.stdout + result.stderr}
        return result, payload
    save()
    return project, config, row, save, call


def test_pinned_real_process_and_web_agree_across_hosts(pinned, monkeypatch):
    p, config, row, save, call = pinned
    run, result = call("verify", {"REVIEW_UNDECLARED": "first-host", "HOME": "/nonexistent-a"})
    assert run.returncode == 0, result
    run, status = call("status", {"REVIEW_UNDECLARED": "different-host", "HOME": "/nonexistent-b"})
    assert run.returncode == 0 and unit(status)["automation"] == "passed"
    assert unit(status)["entries"][0]["validity"] == "current"
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient
    import app.main as main
    from flowtree import view
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(config))
    monkeypatch.setenv("REVIEW_CREDENTIAL", "test-only-credential-739")
    monkeypatch.setenv("REVIEW_UNDECLARED", "web-host")
    monkeypatch.setenv("HOME", "/nonexistent-c")
    before = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in (p.root / ".flowtree").rglob("*") if f.is_file()}
    view._cache.clear()
    try:
        with TestClient(main.app) as client:
            response = client.get("/api/workspaces/review/stories/INDEPENDENT-A?refresh=true")
        assert response.status_code == 200
        u = response.json()["flow"][0]["unit"]
        assert u["automation"] == "passed" and u["entries"][0]["validity"] == "current"
        assert "test-only-credential-739" not in response.text
        assert before == {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in (p.root / ".flowtree").rglob("*") if f.is_file()}
    finally:
        view._cache.clear()


def test_changed_or_missing_declared_value_does_not_reuse_pass(pinned):
    p, config, row, save, call = pinned
    assert call("verify")[0].returncode == 0
    _, changed = call("status", {"REVIEW_CREDENTIAL": "different-value"})
    assert unit(changed)["entries"][0]["validity"] == "stale"
    _, missing = call("status", {"REVIEW_CREDENTIAL": None})
    assert unit(missing)["automation"] != "passed" and missing["context_problems"]
    (p.root / ".flowtree/started").unlink()
    run, blocked = call("verify", {"REVIEW_CREDENTIAL": None})
    assert run.returncode != 0 and blocked["attempts"][0]["state"] == "blocked"
    assert not (p.root / ".flowtree/started").exists()


def test_switch_from_pinned_to_inherit_invalidates(pinned):
    p, config, row, save, call = pinned
    assert call("verify")[0].returncode == 0
    row["execution_context"]["mode"] = "inherit"
    save()
    _, status = call("status")
    assert unit(status)["entries"][0]["validity"] == "stale"


def test_excludes_policy_change_invalidates_even_when_source_is_same(pinned):
    p, config, row, save, call = pinned
    excludes = config.parent / "excludes"
    excludes.write_text("unused-first\n")
    row["execution_context"]["git_excludes_file"] = str(excludes)
    save()
    assert call("verify")[0].returncode == 0
    excludes.write_text("unused-second\n")
    _, status = call("status")
    entry = unit(status)["entries"][0]
    assert entry["validity"] == "stale" and entry["aspects"]["context"] == "changed"


def test_host_git_configuration_does_not_change_pinned_fingerprint(pinned):
    p, config, row, save, call = pinned
    assert call("verify")[0].returncode == 0
    ignored = config.parent / "host-excludes"
    ignored.write_text("test_balance.py\n")
    global_config = config.parent / "host.gitconfig"
    global_config.write_text(f"[core]\n excludesFile = {ignored}\n")
    _, status = call("status", {"GIT_CONFIG_GLOBAL": str(global_config), "REVIEW_UNDECLARED": "host-value"})
    assert unit(status)["automation"] == "passed"
    assert unit(status)["entries"][0]["aspects"]["worktree"] == "same"


def test_declared_missing_excludes_file_cannot_produce_success(pinned):
    p, config, row, save, call = pinned
    row["execution_context"]["git_excludes_file"] = str(config.parent / "missing-excludes")
    save()
    run, result = call("verify")
    assert run.returncode != 0 and not result.get("ok", False), result
