"""B1b 真实执行测试的项目构造器: 每个测试在 tmp 目录建一个真实 git 仓库与真实 pytest 测试, 用 FlowTree CLI 子进程执行。"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from impl_support import FIXTURES, ROOT

PY = sys.executable
GITIGNORE = ".flowtree/\n__pycache__/\n.pytest_cache/\n"

NID_A = "tests/test_savings.py::test_zero_amount_rejected"
NID_B = "tests/test_savings.py::test_resume_after_lost_response"

DEFAULT_TESTS = """
def test_zero_amount_rejected():
    assert 0 == 0

def test_resume_after_lost_response():
    assert True
"""


class Proj:
    def __init__(self, root: Path, tests: str = DEFAULT_TESTS, extra_files=None, argv_extra="", timeout_s=120,
                 pytest_ini=None):
        self.root = root
        (root / "tests").mkdir(parents=True)
        (root / ".gitignore").write_text(GITIGNORE)
        (root / "tests" / "test_savings.py").write_text(textwrap.dedent(tests))
        if pytest_ini:
            (root / "pytest.ini").write_text(pytest_ini)
        for name, content in (extra_files or {}).items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        self.stories = root / "spec" / "stories"
        self.maps = root / "spec" / "maps"
        self.stories.mkdir(parents=True)
        self.maps.mkdir(parents=True)
        (self.stories / "sav-001.story.yaml").write_text((FIXTURES / "sav-001.story.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        self.timeout_s = timeout_s
        self.argv_extra = argv_extra
        self.write_mapping()

    @property
    def story_file(self):
        return self.stories / "sav-001.story.yaml"

    @property
    def map_file(self):
        return self.maps / "sav-001.mapping.yaml"

    def story_digest(self):
        from flowtree.story import load_story_file
        return load_story_file(self.story_file).digest

    def write_mapping(self, tests_a=NID_A, tests_b=NID_B, argv=None, cwd=".", env_id="env-1"):
        argv = argv or f"[python, -m, pytest, tests/test_savings.py, -q{self.argv_extra}]"
        self.map_file.write_text(textwrap.dedent(f"""\
            schema_version: "0.1"
            story: SAV-001
            story_digest: "{self.story_digest()}"
            entries:
              - id: M-01
                covers: [SAV-001.CASE-01]
                level: backend
                runner: pytest
                cwd: "{cwd}"
                argv: {argv}
                tests:
                  - {{nodeid: "{tests_a}", match: exact}}
                env: {{id: {env_id}}}
                timeout_s: {self.timeout_s}
              - id: M-02
                covers: [SAV-001.CASE-02, SAV-001.STEP-03]
                level: backend
                runner: pytest
                cwd: "{cwd}"
                argv: {argv}
                tests:
                  - {{nodeid: "{tests_b}", match: exact}}
                env: {{id: {env_id}}}
                timeout_s: {self.timeout_s}
            """))

    def cli(self, *args, python=True, env=None):
        import os
        e = dict(os.environ)
        e.update(env or {})
        cmd = [PY, "-m", "cli.main", *args]
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=e)

    def verify(self, *extra, python=PY, env=None, mapped_only=True):
        args = ["verify", str(self.stories), "--mappings", str(self.maps), "--project-root", str(self.root), "--json"]
        if python:
            args += ["--python", python]
        if mapped_only:
            args += ["--mapped-only"]
        r = self.cli(*args, *extra, env=env)
        return r, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else None)

    def status(self, python=PY):
        args = ["story", "status", str(self.stories), "--mappings", str(self.maps), "--project-root", str(self.root), "--json"]
        if python:
            args += ["--python", python]
        r = self.cli(*args)
        return r, json.loads(r.stdout)


def units(res):
    return {u["id"]: u for s in res["stories"] for u in s["units"]}


def automation(res, unit):
    return units(res)[f"SAV-001.{unit}"]["automation"]


def manifests(root: Path):
    return sorted((root / ".flowtree" / "runs").glob("*/*/*/manifest.json"))
