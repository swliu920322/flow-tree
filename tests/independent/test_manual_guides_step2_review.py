"""指引不能阻断自动验证；JSON 缺省仍应可机器读取。"""
import json
import sys
import pytest

from cli import main as cli
from flowtree.workspace import Workspace


def workspace(tmp_path, guides):
    return Workspace(id="review", name="review", project_root=tmp_path,
                     python=sys.executable, stories=[tmp_path], mappings=[tmp_path], guides=guides)


def test_no_guides_json_is_still_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_ws", lambda args: workspace(tmp_path, []))
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["ws", "guides", "review", "--json"])
    assert exit_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["guides"] == {}


def test_missing_guide_does_not_prevent_verify(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_load_ws", lambda args: workspace(tmp_path, [tmp_path / "missing-guide"]))
    calls = []
    monkeypatch.setattr(cli.service, "verify", lambda *args: calls.append(args) or {"review": True})
    monkeypatch.setattr(cli, "_render_verify", lambda res, as_json: 0)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["ws", "verify", "review", "--mapped-only"])
    assert exit_info.value.code == 0
    assert len(calls) == 1, "guide-only errors must not block the automation execution path"
