"""独立构建临时 Git 项目，通过 CLI 和真实 pytest 子进程检查 B1b。

不复用实现方 fixture，不修改产品代码；已复现缺陷保持失败。
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
import yaml

from flowtree.canon import content_digest

ROOT = Path(__file__).resolve().parents[2]


class IndependentProject:
    def __init__(self, root, source="def test_total():\n    assert sum([2, 3]) == 5\n"):
        self.root = root
        root.mkdir()
        (root / "test_balance.py").write_text(source, encoding="utf-8")
        (root / ".gitignore").write_text(".flowtree/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
        self.stories = root / "stories"
        self.maps = root / "maps"
        self.stories.mkdir()
        self.maps.mkdir()
        self.add_story("INDEPENDENT-A")

    def add_story(self, sid, entry_id="M-01", nodeid="test_balance.py::test_total", argv=None):
        story = {
            "schema_version": "0.1", "id": sid, "title": "核对合计",
            "actor": "用户", "goal": "查看确定的计算结果",
            "main_flow": [{"id": "STEP-01", "action": "查看合计", "expected": ["2 与 3 的合计为 5"]}],
        }
        mapping = {
            "schema_version": "0.1", "story": sid, "story_digest": content_digest(story),
            "entries": [{
                "id": entry_id, "covers": [f"{sid}.STEP-01"], "level": "backend",
                "runner": "pytest", "cwd": ".", "argv": argv or ["python", "-m", "pytest", "test_balance.py", "-q"],
                "tests": [{"nodeid": nodeid, "match": "exact"}],
                "env": {"id": "independent-isolated"}, "timeout_s": 15,
            }],
        }
        self.write(self.stories / f"{sid}.yaml", story)
        self.write(self.maps / f"{sid}.yaml", mapping)

    @staticmethod
    def write(path, data):
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def cli(self, verb="verify", extra=(), env=None):
        args = [verb] if verb == "verify" else ["story", "status"]
        cmd = [sys.executable, "-m", "cli.main", *args, str(self.stories), "--mappings", str(self.maps),
               "--project-root", str(self.root), "--python", sys.executable, "--json", *extra]
        run = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **(env or {})},
                             text=True, capture_output=True, timeout=45)
        assert run.stdout.strip().startswith("{"), run.stdout + run.stderr
        return run, json.loads(run.stdout)


def unit(payload, sid="INDEPENDENT-A"):
    return next(s for s in payload["stories"] if s["id"] == sid)["units"][0]


def test_real_execution_is_current_but_never_human_accepted(tmp_path):
    project = IndependentProject(tmp_path / "project")
    run, payload = project.cli()
    assert run.returncode == 0, payload
    assert unit(payload)["automation"] == "passed"
    assert unit(payload)["human"] == "none" and unit(payload)["rule"] == "draft"
    manifest = json.loads(Path(payload["attempts"][0]["manifest"]).read_text())
    assert manifest["exit_code"] == 0
    assert manifest["baseline"]["runtime_digest"]
    report = json.loads((Path(payload["attempts"][0]["manifest"]).parent / "plugin-report.json").read_text())
    assert [c["nodeid"] for c in report["collected"]] == ["test_balance.py::test_total"]
    assert report["terminal"] is True
    assert report["items"]["test_balance.py::test_total"]["call"]["outcome"] == "passed"


@pytest.mark.parametrize("mutation", ["truncate", "remove"])
def test_latest_unreadable_manifest_cannot_fall_back_to_older_pass(tmp_path, mutation):
    project = IndependentProject(tmp_path / "project")
    first, _ = project.cli()
    second, payload = project.cli()
    assert first.returncode == second.returncode == 0
    latest = Path(payload["attempts"][0]["manifest"])
    if mutation == "truncate":
        latest.write_text("{", encoding="utf-8")
    else:
        latest.unlink()
    run, status = project.cli("status")
    assert run.returncode == 0
    assert unit(status)["automation"] != "passed", status
    assert status["evidence_problems"], status


def test_same_entry_id_in_two_stories_cannot_overwrite_evidence(tmp_path):
    project = IndependentProject(tmp_path / "project")
    project.add_story("INDEPENDENT-B", entry_id="M-01")
    run, payload = project.cli()
    manifests = [a["manifest"] for a in payload["attempts"]]
    assert len(manifests) == len(set(manifests)) == 2, payload
    assert run.returncode == 0, payload
    assert unit(payload, "INDEPENDENT-A")["automation"] == "passed"
    assert unit(payload, "INDEPENDENT-B")["automation"] == "passed"


@pytest.mark.parametrize("empty_mode", ["unknown_entry", "empty_mapping"])
def test_empty_execution_scope_never_returns_success(tmp_path, empty_mode):
    project = IndependentProject(tmp_path / "project")
    extra = ["--mapped-only"]
    if empty_mode == "unknown_entry":
        extra += ["--entry", "M-TYPO"]
    else:
        path = project.maps / "INDEPENDENT-A.yaml"
        mapping = yaml.safe_load(path.read_text())
        mapping["entries"] = []
        project.write(path, mapping)
    run, payload = project.cli(extra=extra)
    assert run.returncode != 0 and payload["ok"] is False, payload
    assert payload["executed"] is False, payload


def test_changed_test_environment_cannot_reuse_old_pass(tmp_path):
    project = IndependentProject(tmp_path / "project", source=(
        "import os\ndef test_total():\n"
        "    rate = int(os.environ['FLOWTREE_REVIEW_RATE'])\n"
        "    assert 5 * rate == 10\n"
    ))
    run, payload = project.cli(env={"FLOWTREE_REVIEW_RATE": "2"})
    assert run.returncode == 0, payload
    # 同样源码和解释器，环境改变后直接运行真实断言，证明结果已不同。
    control = subprocess.run([sys.executable, "-m", "pytest", "test_balance.py", "-q"], cwd=project.root,
                             env={**os.environ, "FLOWTREE_REVIEW_RATE": "3"},
                             capture_output=True, text=True, timeout=20)
    assert control.returncode == 1 and "1 failed" in control.stdout, control.stdout + control.stderr
    run, status = project.cli("status", env={"FLOWTREE_REVIEW_RATE": "3"})
    assert run.returncode == 0
    assert unit(status)["automation"] != "passed", status
    assert unit(status)["entries"][0]["validity"] in ("stale", "unknown")


def test_unmapped_failure_in_explicit_command_is_not_success(tmp_path):
    project = IndependentProject(tmp_path / "project", source=(
        "def test_total():\n    assert sum([2, 3]) == 5\n"
        "def test_no_double_charge():\n    assert 2 * 5 == 5\n"
    ))
    run, payload = project.cli()
    manifest = json.loads(Path(payload["attempts"][0]["manifest"]).read_text())
    assert manifest["exit_code"] == 1 and manifest["counts"]["failed"] == 1
    assert run.returncode != 0 and payload["ok"] is False, payload


@pytest.mark.parametrize("failure", ["assertion", "teardown", "skip"])
def test_real_failure_and_nonexecution_are_not_passed(tmp_path, failure):
    sources = {
        "assertion": "def test_total():\n    assert 2 + 3 == 9\n",
        "teardown": "import pytest\n@pytest.fixture\ndef f():\n    yield\n    raise RuntimeError('cleanup failed')\ndef test_total(f):\n    assert 2 + 3 == 5\n",
        "skip": "import pytest\n@pytest.mark.skip(reason='environment not ready')\ndef test_total():\n    assert 2 + 3 == 5\n",
    }
    expected = {"assertion": "failed", "teardown": "error", "skip": "not_run"}
    project = IndependentProject(tmp_path / "project", source=sources[failure])
    run, payload = project.cli()
    assert run.returncode == 1 and unit(payload)["automation"] == expected[failure], payload


def test_ini_filter_cannot_silently_reduce_scope(tmp_path):
    project = IndependentProject(tmp_path / "project")
    (project.root / "pytest.ini").write_text("[pytest]\naddopts = -k total\n", encoding="utf-8")
    run, payload = project.cli()
    assert run.returncode == 1 and unit(payload)["automation"] == "error", payload


def test_changed_artifact_is_error_with_history_preserved(tmp_path):
    project = IndependentProject(tmp_path / "project")
    run, payload = project.cli()
    assert run.returncode == 0
    junit = Path(payload["attempts"][0]["manifest"]).parent / "junit.xml"
    junit.write_text(junit.read_text() + "<!-- independent corruption -->", encoding="utf-8")
    run, status = project.cli("status")
    assert run.returncode == 0 and unit(status)["automation"] == "error"
    assert status["evidence_problems"]


def test_timeout_also_kills_child_that_ignores_sigterm(tmp_path):
    project = IndependentProject(tmp_path / "project")
    pidfile = project.root / ".flowtree" / "stubborn-child.pid"
    child = (
        "import os,signal,time,pathlib;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid()));time.sleep(30)"
    )
    (project.root / "test_balance.py").write_text(
        "import subprocess,sys,time\ndef test_total():\n"
        f"    subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        "    time.sleep(30)\n", encoding="utf-8")
    path = project.maps / "INDEPENDENT-A.yaml"
    mapping = yaml.safe_load(path.read_text())
    mapping["entries"][0]["timeout_s"] = 2
    project.write(path, mapping)
    pid = None
    try:
        run, payload = project.cli()
        assert run.returncode == 1 and payload["attempts"][0]["state"] == "error", payload
        assert pidfile.exists(), "child did not start; timeout cleanup was not exercised"
        pid = int(pidfile.read_text())
        time.sleep(0.3)
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        # 即便产品清理失败也只清理本测试创建、由独有 pid 文件标识的子进程。
        if pid is None and pidfile.exists():
            pid = int(pidfile.read_text())
        if pid is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
