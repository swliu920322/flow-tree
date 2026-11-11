"""伴随运行时独立核对：探测只读、路径绑定及摘要变化。"""
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from flowtree.companions import (
    CompanionSpec, _binding_problem, probe_python, runtime_with_companions,
)
from flowtree.runners import RuntimeProbe


@pytest.fixture
def backend(tmp_path):
    root = tmp_path / "backend-env"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(root)],
                   check=True, capture_output=True, timeout=60)
    site = next((root / "lib").glob("python*/site-packages"))
    return CompanionSpec("backend", "python", str(root / "bin/python"), "BACKEND_PYTHON"), site


def test_probe_does_not_create_bytecode_in_the_inspected_environment(backend):
    spec, site = backend
    # 普通启动定制模块没有副作用；其字节码只能由探测解释器生成。
    (site / "sitecustomize.py").write_text("pass\n")
    before = {str(p.relative_to(site)): p.read_bytes() for p in site.rglob("*") if p.is_file()}
    digest, _, error = probe_python(spec)
    assert digest and error is None
    after = {str(p.relative_to(site)): p.read_bytes() for p in site.rglob("*") if p.is_file()}
    assert after == before, "只读重检向被探测环境写入了文件"


def test_binding_rejects_relative_paths_before_any_probe(backend, tmp_path, monkeypatch):
    spec, _ = backend
    monkeypatch.chdir(tmp_path)
    bound = os.path.relpath(spec.interpreter, tmp_path)
    other_cwd = tmp_path / "client"
    other_cwd.mkdir()
    assert (other_cwd / bound).absolute() != Path(spec.interpreter)
    assert _binding_problem(spec, {spec.bind_env: bound}) is not None, (
        "相对路径在验证器与被测子进程的 cwd 下含义不同，必须拒绝或统一后再传给进程"
    )


def test_absolute_binding_accepts_only_the_declared_environment(backend, tmp_path):
    spec, _ = backend
    assert _binding_problem(spec, {spec.bind_env: spec.interpreter}) is None
    assert _binding_problem(spec, {}) is not None
    assert _binding_problem(spec, {spec.bind_env: str(tmp_path / "other-python")}) is not None


def test_distribution_metadata_changes_the_companion_digest(backend):
    spec, site = backend
    before, _, error = probe_python(spec)
    assert before and error is None
    dist = site / "codex_review_dep-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: codex-review-dep\nVersion: 1.0\n")
    after, info, error = probe_python(spec)
    assert after and after != before and error is None
    assert info["sqlite"]


def test_no_companions_preserves_the_original_probe_object():
    original = RuntimeProbe("sha256:original", {"version": "unchanged"})
    runner = SimpleNamespace(runtime=lambda *args: original)
    assert runtime_with_companions(
        runner, SimpleNamespace(companions=[]), None, None, {}, Path("."), Path("."), {}
    ) is original


def test_pytest_probe_is_readonly_and_preserves_report_contents(tmp_path, monkeypatch):
    from flowtree import baseline
    plugin = tmp_path / "probe_plugin.py"
    plugin.write_text('def runtime_info():\n    return {"version": "review", "packages": []}\n')
    monkeypatch.setattr(baseline, "PLUGIN_FILE", plugin)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    info, error = baseline.probe_runtime(sys.executable, dict(os.environ))
    assert error is None and info == {"version": "review", "packages": []}
    after = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before
