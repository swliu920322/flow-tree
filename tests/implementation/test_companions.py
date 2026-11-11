"""伴随运行时 (companion runtime) 绑定: 后端解释器/依赖变化必须使旧证据失效。
全部离线: 用 `python -m venv --without-pip` 建临时 venv, 用伪造的 .dist-info 模拟"依赖变化"; 不联网、不安装。
真实 git 仓库 + 真实 pytest 子进程 + 真实 CLI。"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from b1b_support import PY, Proj
from impl_support import ROOT
from flowtree import companions as C
from flowtree.canon import content_digest
from flowtree.mapping import load_mapping_file
from flowtree.runners import RuntimeProbe
from flowtree.story import load_stories

BIND = "LPB_INT_PYTHON"


# ---------------------------------------------------------------- 夹具

def make_venv(path: Path) -> str:
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(path)], check=True, capture_output=True, timeout=120)
    return str(path / "bin" / "python")


def site_packages(venv: Path) -> Path:
    return next((venv / "lib").glob("python*/site-packages"))


def add_dist(venv: Path, name: str, version: str) -> None:
    d = site_packages(venv) / f"{name}-{version}.dist-info"
    d.mkdir(exist_ok=True)
    (d / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")


class Setup:
    def __init__(self, tmp_path, tests=None, companion_in_mapping=True):
        self.tmp = tmp_path
        self.venv = tmp_path / "cv"
        self.interp = make_venv(self.venv)
        add_dist(self.venv, "fakedb", "1.0")
        self.proj = Proj(tmp_path / "p", **({"tests": tests} if tests else {}))
        if companion_in_mapping:
            self.set_mapping_companions(["backend-python"])

    def set_mapping_companions(self, names):
        mp = yaml.safe_load(self.proj.map_file.read_text())
        for e in mp["entries"]:
            if names:
                e["companions"] = names
            else:
                e.pop("companions", None)
        self.proj.map_file.write_text(yaml.safe_dump(mp, allow_unicode=True))

    def cfg(self, *, declared=True, interpreter=None, bound=None, name="workspaces.yaml", companion_name="backend-python"):
        interp = interpreter or self.interp
        ws = {"id": "ws1", "name": "ws", "project_root": str(self.proj.root), "python": PY,
              "stories": [str(self.proj.stories)], "mappings": [str(self.proj.maps)],
              "execution_context": {"mode": "pinned", "env": {BIND: bound or interp, "CV_SITE": str(site_packages(self.venv))}}}
        if declared:
            ws["companions"] = {companion_name: {"kind": "python", "interpreter": interp, "bind_env": BIND}}
        p = self.tmp / name
        p.write_text(yaml.safe_dump({"workspaces": [ws]}))
        return p

    def run(self, cfg, verb):
        args = ["workspace", verb, "ws1", "--config", str(cfg), "--json"] + (["--mapped-only"] if verb == "verify" else [])
        r = self.proj.cli(*args)
        try:
            return r, json.loads(r.stdout)
        except ValueError:
            return r, {"raw": r.stdout + r.stderr}

    def manifests(self):
        return sorted((self.proj.root / ".flowtree" / "runs").glob("*/*/M-01/manifest.json"))

    def last_manifest(self):
        return json.loads(self.manifests()[-1].read_text())


def entry1(res):
    return next(e for s in res["stories"] for u in s["units"] if u["id"] == "SAV-001.CASE-01" for e in u["entries"])


def auto(res):
    return next(u for s in res["stories"] for u in s["units"] if u["id"] == "SAV-001.CASE-01")["automation"]


# ---------------------------------------------------------------- 单元: 兼容性、绑定、缓存键、探测内容

def test_entry_digest_is_unchanged_when_no_companions_are_declared(tmp_path):
    p = Proj(tmp_path / "p")
    ss = load_stories([p.stories])
    lm = load_mapping_file(p.map_file, ss)
    assert not [i for i in lm.issues if i.severity == "error"]
    for e in lm.mapping.entries:
        legacy = e.model_dump(mode="json")
        legacy.pop("companions")
        assert lm.entry_digests[e.id] == content_digest({"story": "SAV-001", "entry": legacy})   # 与引入该字段前的算法逐字节一致
    raw = yaml.safe_load(p.map_file.read_text())
    raw["entries"][0]["companions"] = ["backend-python"]
    p.map_file.write_text(yaml.safe_dump(raw))
    lm2 = load_mapping_file(p.map_file, ss)
    assert lm2.entry_digests["M-01"] != lm.entry_digests["M-01"] and lm2.entry_digests["M-02"] == lm.entry_digests["M-02"]


class FakeRunner:
    def __init__(self, digest="sha256:base"):
        self.d = digest
        self.calls = 0

    def runtime(self, *a):
        self.calls += 1
        return RuntimeProbe(self.d, {"x": 1})


class E:
    def __init__(self, companions=()):
        self.companions = list(companions)


def spec(interp, name="backend-python"):
    return C.CompanionSpec(name, "python", os.path.abspath(interp), BIND)


def test_runtime_digest_is_exactly_the_runner_digest_without_companions():
    r = FakeRunner()
    out = C.runtime_with_companions(r, E(), None, None, {}, Path("."), Path("."), {"backend-python": spec("/x")})
    assert out.digest == "sha256:base" and out.info == {"x": 1} and out.error is None
    assert C.cache_key(E(), {"backend-python": spec("/x")}, {}) is None   # 缓存键也不变


def test_binding_mismatch_missing_and_unconfigured_are_errors_not_probes(tmp_path):
    a, b = make_venv(tmp_path / "a"), make_venv(tmp_path / "b")
    specs = {"backend-python": spec(a)}
    run = lambda env, sp=specs, names=("backend-python",): C.runtime_with_companions(FakeRunner(), E(names), None, None, env, Path("."), Path("."), sp)
    ok = run({BIND: a})
    assert ok.error is None and ok.digest and ok.info["companions"]["backend-python"]["packages"] >= 0
    mismatch = run({BIND: b})                                   # 声明 A, 测试实际收到 B
    assert mismatch.digest is None and "does not match the declared interpreter" in mismatch.error
    assert a not in mismatch.error and b not in mismatch.error  # 报错不回显路径值
    assert run({}).digest is None and "not set" in run({}).error
    assert run({BIND: a}, {}).digest is None and "not configured" in run({BIND: a}, {}).error
    assert run({BIND: a}, specs, ("nope",)).digest is None


def test_same_base_interpreter_two_venvs_are_different_companions(tmp_path):
    a, b = make_venv(tmp_path / "a"), make_venv(tmp_path / "b")
    da = C.probe_python(spec(a))[0]
    db = C.probe_python(spec(b))[0]
    assert da and db and da != db      # 按声明路径绑定, 不解析到同一个基础解释器


def test_cache_key_includes_companion_config_and_actual_binding(tmp_path):
    a, b = make_venv(tmp_path / "a"), make_venv(tmp_path / "b")
    e = E(["backend-python"])
    k = lambda interp, env: C.cache_key(e, {"backend-python": spec(interp)}, env)
    assert k(a, {BIND: a}) != k(b, {BIND: b}) and k(a, {BIND: a}) != k(a, {BIND: b})
    assert C.cache_key(e, {}, {}) is not None                    # 未配置也有稳定键


def test_probe_reports_sqlite_library_version_and_is_offline_readonly(tmp_path):
    a = make_venv(tmp_path / "a")
    r = subprocess.run([a, "-I", "-c", C._PY_PROBE], capture_output=True, text=True, env=dict(C.PROBE_ENV), timeout=60)
    data = json.loads(r.stdout)
    assert data["sqlite_version"] and data["version"] and "packages" in data
    digest, info, err = C.probe_python(spec(a))
    assert err is None and info["sqlite"] == data["sqlite_version"] and "/" not in json.dumps(info)   # 信息里没有路径
    before = digest
    add_dist(tmp_path / "a", "fakedb", "2.0")
    assert C.probe_python(spec(a))[0] != before                   # 依赖变化 → 摘要变化


def test_workspace_companion_declaration_validation(tmp_path):
    from flowtree.workspace import WorkspaceConfigError, load_workspaces
    base = {"id": "w", "project_root": str(tmp_path), "stories": [str(tmp_path)], "mappings": [str(tmp_path)]}
    def load(c):
        (tmp_path / "c.yaml").write_text(yaml.safe_dump({"workspaces": [{**base, "companions": c}]}))
        return load_workspaces(tmp_path / "c.yaml")
    ok = load({"backend-python": {"kind": "python", "interpreter": "/usr/bin/python3", "bind_env": BIND}})
    assert ok["w"].context().companions["backend-python"].bind_env == BIND
    for bad in ({"x": {"kind": "python", "interpreter": "rel/python", "bind_env": BIND}},
                {"x": {"kind": "python", "interpreter": "/usr/bin/python3"}},
                {"x": {"kind": "ruby", "interpreter": "/usr/bin/ruby", "bind_env": BIND}}):
        with pytest.raises(WorkspaceConfigError):
            load(bad)


# ---------------------------------------------------------------- 端到端 (真实 CLI / 真实子进程)

def test_passing_run_is_current_and_dependency_change_makes_it_stale_then_restores(tmp_path):
    s = Setup(tmp_path)
    cfg = s.cfg()
    r, res = s.run(cfg, "verify")
    assert r.returncode == 0 and auto(res) == "passed", res
    mf = s.last_manifest()
    assert mf["baseline"]["runtime_digest"] and mf["runtime"]["companions"]["backend-python"]["packages"] >= 1
    assert str(tmp_path) not in json.dumps(mf["runtime"])         # 清单里的伴随信息不含路径
    r, st = s.run(cfg, "status")
    assert entry1(st)["validity"] == "current" and auto(st) == "passed"
    assert entry1(st)["aspects"]["runtime"] == "same"

    add_dist(s.venv, "fakedb", "2.0")                             # 伴随依赖变化 (同名新版本)
    r, st = s.run(cfg, "status")
    e = entry1(st)
    assert e["validity"] == "stale" and e["aspects"]["runtime"] == "changed" and e["aspects"]["worktree"] == "same"
    assert auto(st) == "not_run"                                  # 旧通过不再点亮


def test_actual_interpreter_mismatch_blocks_execution_and_is_persisted(tmp_path):
    s = Setup(tmp_path)
    other = make_venv(tmp_path / "other")
    r, res = s.run(s.cfg(bound=other), "verify")                  # 声明 cv, 但测试实际会收到 other
    a = res["attempts"][0]
    assert r.returncode == 1 and a["state"] == "blocked" and "does not match the declared interpreter" in a["reason"]
    assert not list((s.proj.root / ".flowtree/runs").glob("*/*/M-01/stdout.txt"))   # 没有启动任何测试子进程
    assert s.manifests() and s.last_manifest()["state"] == "blocked"                  # blocked 尝试已落盘


def test_blocked_attempt_supersedes_an_older_pass(tmp_path):
    s = Setup(tmp_path)
    cfg = s.cfg()
    assert auto(s.run(cfg, "verify")[1]) == "passed"
    other = make_venv(tmp_path / "other")
    s.run(s.cfg(bound=other, name="bad.yaml"), "verify")        # 之后一次被阻塞的尝试
    r, st = s.run(cfg, "status")
    assert auto(st) != "passed", "旧通过不得在新的 blocked 尝试之后回退点亮"
    assert len(s.manifests()) == 2


def test_missing_declaration_or_missing_interpreter_blocks_and_makes_recheck_unknown(tmp_path):
    s = Setup(tmp_path)
    cfg = s.cfg()
    assert auto(s.run(cfg, "verify")[1]) == "passed"
    # 映射声明了 companions, 工作区没有配置 → 重检 unknown, 执行 blocked
    nocfg = s.cfg(declared=False, name="nodecl.yaml")
    r, st = s.run(nocfg, "status")
    assert entry1(st)["validity"] == "unknown" and auto(st) != "passed"
    r, res = s.run(nocfg, "verify")
    assert res["attempts"][0]["state"] == "blocked" and "not configured" in res["attempts"][0]["reason"]
    # 未知名称
    unknown = s.cfg(companion_name="other-name", name="other.yaml")
    assert s.run(unknown, "verify")[1]["attempts"][0]["state"] == "blocked"


def test_vanished_interpreter_makes_recheck_unknown_and_execution_blocked(tmp_path):
    s = Setup(tmp_path)
    cfg = s.cfg()
    assert auto(s.run(cfg, "verify")[1]) == "passed"
    (s.venv / "bin" / "python").unlink()                          # 解释器消失: 探测失败 → unknown / blocked, 不当作"没变"
    r, st = s.run(cfg, "status")
    assert entry1(st)["validity"] == "unknown" and entry1(st)["aspects"]["runtime"] == "unknown" and auto(st) != "passed"
    r, res = s.run(cfg, "verify")
    assert res["attempts"][0]["state"] == "blocked" and "interpreter not found" in res["attempts"][0]["reason"]


CHANGE_DURING_RUN = """
import os, pathlib
def test_zero_amount_rejected():
    d = pathlib.Path(os.environ["CV_SITE"]) / "midrun-9.9.dist-info"
    d.mkdir(exist_ok=True)
    (d / "METADATA").write_text("Metadata-Version: 2.1\\nName: midrun\\nVersion: 9.9\\n")
def test_resume_after_lost_response(): pass
"""


def test_companion_change_during_the_run_invalidates_this_run(tmp_path):
    s = Setup(tmp_path, tests=CHANGE_DURING_RUN)
    cfg = s.cfg()
    r, res = s.run(cfg, "verify")
    mf = s.last_manifest()
    assert "runtime" in mf["changed_during_run"], mf["changed_during_run"]       # 执行后重新探测, 发现与执行前不同
    assert mf["baseline"]["worktree_fingerprint"] is None                         # 基线不可信 → 不贡献当前通过
    assert auto(res) != "passed"
    r, st = s.run(cfg, "status")
    assert entry1(st)["validity"] == "unknown" and auto(st) != "passed"


def test_old_mapping_runtime_digest_is_unchanged_by_workspace_companion_config(tmp_path):
    s = Setup(tmp_path, companion_in_mapping=False)
    plain = s.cfg(declared=False, name="plain.yaml")
    with_cfg = s.cfg(declared=True, name="with.yaml")            # 工作区配置了伴随项, 但映射没有声明
    assert auto(s.run(plain, "verify")[1]) == "passed"
    d1 = s.last_manifest()["baseline"]["runtime_digest"]
    r, st = s.run(with_cfg, "status")
    e = entry1(st)
    assert e["validity"] == "current" and e["aspects"]["runtime"] == "same"   # 旧证据仍有效, 摘要未变
    assert auto(s.run(with_cfg, "verify")[1]) == "passed"
    assert s.last_manifest()["baseline"]["runtime_digest"] == d1
    assert "companions" not in (s.last_manifest().get("runtime") or {})


def test_web_recheck_uses_the_same_companion_binding(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient
    import app.main as m
    from flowtree import view
    s = Setup(tmp_path)
    cfg = s.cfg()
    assert auto(s.run(cfg, "verify")[1]) == "passed"
    c = TestClient(m.app)
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(cfg))
    view._cache.clear()
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    u = next(x for st in d["flow"] for x in [st] + st["branches"] if x["qid"] == "SAV-001.CASE-01")["unit"]
    assert u["entries"][0]["validity"] == "current" and u["automation"] == "passed"
    add_dist(s.venv, "fakedb", "3.0")
    view._cache.clear()
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    u = next(x for st in d["flow"] for x in [st] + st["branches"] if x["qid"] == "SAV-001.CASE-01")["unit"]
    assert u["entries"][0]["validity"] == "stale" and u["automation"] != "passed"
    assert str(s.venv) not in json.dumps(d) and s.interp not in json.dumps(d)   # 页面/API 不暴露伴随项解释器路径
