"""真实 flutter test 测试的项目构造器: 会话级模板 (flutter pub get --offline 一次) + 每个测试复制成独立 git 仓库。"""
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from impl_support import FIXTURES, ROOT

FLUTTER = shutil.which("flutter") or (str(Path.home() / "flutter/bin/flutter") if (Path.home() / "flutter/bin/flutter").exists() else None)
PY = sys.executable
GITIGNORE = ".dart_tool/\nbuild/\n.flowtree/\n"

PUBSPEC = """name: probe_app
environment:
  sdk: ^3.10.0
dependencies:
  flutter:
    sdk: flutter
dev_dependencies:
  flutter_test:
    sdk: flutter
"""

DEFAULT_TEST = """
import 'package:flutter_test/flutter_test.dart';
void main() {
  test('zero amount rejected', () { expect(0, 0); });
  group('G', () {
    test('resume after lost response', () { expect(1 + 1, 2); });
  });
}
"""
NID_A = "test/savings_test.dart::zero amount rejected"
NID_B = "test/savings_test.dart::G resume after lost response"


def build_template(path: Path) -> Path:
    (path / "test").mkdir(parents=True)
    (path / "pubspec.yaml").write_text(PUBSPEC)
    env = {**os.environ, "FLUTTER_SUPPRESS_ANALYTICS": "true"}
    r = subprocess.run([FLUTTER, "--no-version-check", "pub", "get", "--offline"], cwd=path, env=env, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout[-600:] + r.stderr[-600:]
    return path


class FlutterProj:
    def __init__(self, template: Path, root: Path, tests: str = DEFAULT_TEST, extra_tests=None, timeout_s=300, flutter_arg=None):
        shutil.copytree(template, root)
        self.root = root
        (root / "test").mkdir(exist_ok=True)
        (root / "test" / "savings_test.dart").write_text(textwrap.dedent(tests))
        for name, content in (extra_tests or {}).items():
            (root / "test" / name).write_text(textwrap.dedent(content))
        (root / ".gitignore").write_text(GITIGNORE)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        self.stories = root / "spec" / "stories"
        self.maps = root / "spec" / "maps"
        self.stories.mkdir(parents=True); self.maps.mkdir(parents=True)
        (self.stories / "sav-001.story.yaml").write_text((FIXTURES / "sav-001.story.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        self.timeout_s = timeout_s
        self.flutter_arg = flutter_arg or FLUTTER
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

    def write_mapping(self, a=NID_A, b=NID_B, files=("test/savings_test.dart",), env_id="env-1", flutter_arg=None, extra_tests_b=None):
        farg = flutter_arg or self.flutter_arg
        argv = "[" + ", ".join([json.dumps(farg), "test", *[json.dumps(f) for f in files]]) + "]"
        self.map_file.write_text(textwrap.dedent(f"""\
            schema_version: "0.1"
            story: SAV-001
            story_digest: "{self.story_digest()}"
            entries:
              - id: M-01
                covers: [SAV-001.CASE-01]
                level: client
                runner: flutter
                cwd: "."
                argv: {argv}
                tests:
                  - {{nodeid: {json.dumps(a)}, match: exact}}
                env: {{id: {env_id}}}
                timeout_s: {self.timeout_s}
              - id: M-02
                covers: [SAV-001.CASE-02, SAV-001.STEP-03]
                level: client
                runner: flutter
                cwd: "."
                argv: {argv}
                tests:
                  - {{nodeid: {json.dumps(b)}, match: exact}}
                env: {{id: {env_id}}}
                timeout_s: {self.timeout_s}
            """))

    def cli(self, *args, env=None):
        e = dict(os.environ); e.update(env or {})
        return subprocess.run([PY, "-m", "cli.main", *args], cwd=ROOT, capture_output=True, text=True, timeout=600, env=e)

    def verify(self, *extra, env=None, mapped_only=True):
        args = ["verify", str(self.stories), "--mappings", str(self.maps), "--project-root", str(self.root), "--json"]
        if mapped_only:
            args.append("--mapped-only")
        r = self.cli(*args, *extra, env=env)
        return r, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else {"raw": r.stdout + r.stderr})

    def status(self, env=None):
        r = self.cli("story", "status", str(self.stories), "--mappings", str(self.maps), "--project-root", str(self.root), "--json", env=env)
        return r, json.loads(r.stdout)

    def manifest(self, entry="M-01"):
        p = next((self.root / ".flowtree/runs").glob(f"*/*/{entry}/manifest.json"))
        return p, json.loads(p.read_text())

    def package_config(self) -> Path:
        return self.root / ".dart_tool" / "package_config.json"
