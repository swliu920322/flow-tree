"""第三批: 统一的工作区执行上下文。CLI 执行/状态与 Web 只读重检用同一份配置、同一解析函数。
全部用真实 git 仓库与真实 pytest 子进程, 并用不同的宿主环境分别驱动 CLI 与 Web。"""
import json
import os
import sys
import time

import pytest
import yaml

from b1b_support import PY, Proj
from impl_support import ROOT
from flowtree.context import ContextSpec, resolve
from flowtree.status import Baseline, Validity, compare_aspects, evaluate_validity

SECRET = "pw1-SECRET-VALUE-xyz"

ENV_TEST = """
import os
def test_zero_amount_rejected():
    # 固定上下文: 未声明的宿主变量不得进入被测子进程
    assert os.environ.get("FT_HOST_ONLY") is None, "undeclared host variable leaked into the pinned test"
    assert os.environ["FT_RATE"] == "2"
    assert os.environ["FT_DB_PASSWORD"]
def test_resume_after_lost_response(): pass
"""


def write_cfg(tmp_path, proj, ctx=None, ws_id="ws1", name="workspaces.yaml"):
    cfg = {"workspaces": [{"id": ws_id, "name": "ws", "project_root": str(proj.root), "python": PY,
                           "stories": [str(proj.stories)], "mappings": [str(proj.maps)],
                           "execution_context": ctx if ctx is not None else {}}]}
    p = tmp_path / name
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


PINNED = {"mode": "pinned", "env": {"FT_RATE": "2"}, "env_from_host": ["FT_DB_PASSWORD"]}


def ws_cli(proj, cfg, verb, host=None, *extra):
    args = ["workspace", verb, "ws1", "--config", str(cfg), "--json", *extra]
    r = proj.cli(*args, env=host or {})
    try:
        return r, json.loads(r.stdout)
    except ValueError:
        return r, {"raw": r.stdout + r.stderr}


def units(res):
    return {u["id"]: u for s in res["stories"] for u in s["units"]}


def entry(res, qid="SAV-001.CASE-01"):
    return units(res)[qid]["entries"][0]


def all_flowtree_text(root):
    return b"".join(p.read_bytes() for p in (root / ".flowtree").rglob("*") if p.is_file() and p.name != "env.salt")


@pytest.fixture
def api(monkeypatch):
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient
    import app.main as m
    from flowtree import view
    view._cache.clear()
    return TestClient(m.app), view


def web(c, monkeypatch, cfg, host=None, drop=()):
    from flowtree import view
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(cfg))
    for k, v in (host or {}).items():
        monkeypatch.setenv(k, v)
    for k in drop:
        monkeypatch.delenv(k, raising=False)
    view._cache.clear()
    return c.get("/api/workspaces/ws1/stories/SAV-001").json()


def wunit(d, qid="SAV-001.CASE-01"):
    for st in d["flow"]:
        for u in [st] + st["branches"]:
            if u["qid"] == qid:
                return u["unit"]


# ---------------------------------------------------------------- 解析本身

def test_inherit_resolution_matches_the_legacy_assembly_exactly():
    host = {"A": "1", "PYTEST_ADDOPTS": "-k x", "PYTHONPATH": "/p", "GIT_CONFIG_COUNT": "2"}
    from flowtree.execution import child_env
    legacy = child_env({"B": "2"})
    rc = resolve(ContextSpec(env={"B": "2"}), host)
    assert rc.removed_addopts == "-k x" and rc.context_digest is None and rc.git_env is None
    assert rc.env["A"] == "1" and rc.env["B"] == "2" and "PYTEST_ADDOPTS" not in rc.env
    assert rc.env["PYTHONPATH"].endswith(os.pathsep + "/p")
    assert child_env()["PYTHONPATH"] == resolve(ContextSpec(), os.environ).env["PYTHONPATH"]
    assert legacy["B"] == "2"


def test_pinned_env_contains_only_declared_and_injected_variables():
    rc = resolve(ContextSpec(mode="pinned", env={"X": "1"}, env_from_host=("H",)), {"H": "host-value-123", "OTHER": "o", "PATH": "/evil"})
    assert set(rc.env) == {"PATH", "X", "H", "PYTHONPATH"} and rc.env["PATH"] != "/evil"
    assert rc.git_env["GIT_CONFIG_NOSYSTEM"] == "1" and rc.git_env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert rc.context_digest and "host-value-123" not in json.dumps(rc.summary()) and rc.env["H"] == "host-value-123"


def test_missing_required_host_variable_is_a_problem_in_both_modes_never_a_silent_fallback():
    for mode in ("pinned", "inherit"):
        rc = resolve(ContextSpec(mode=mode, env_from_host=("NOPE_X",)), {"PATH": "/usr/bin"})
        assert rc.problems and "NOPE_X" in rc.problems[0]


@pytest.mark.parametrize("env,msg", [
    ({"DB_PASSWORD": "x"}, "looks like a secret"), ({"API_TOKEN": "x"}, "looks like a secret"),
    ({"DATABASE_URL": "postgres://user:pw@host/db"}, "looks like a secret"), ({"bad name": "x"}, "not a valid"),
])
def test_secret_looking_literals_are_rejected_in_configuration(env, msg):
    assert any(msg in p for p in ContextSpec(env=env).validate())
    assert ContextSpec(env={"DATABASE_URL": "sqlite+aiosqlite:///:memory:", "ENVIRONMENT": "test"}).validate() == []


def test_spec_validation_rules():
    assert any("both" in p for p in ContextSpec(env={"A": "1"}, env_from_host=("A",)).validate())
    assert any("pinned_path" in p for p in ContextSpec(pinned_path="/x").validate())
    assert any("mode" in p for p in ContextSpec(mode="weird").validate())


def test_old_evidence_without_context_digest_stays_valid_in_inherit_but_not_in_pinned():
    from flowtree.evidence import baseline_from_dict
    old = baseline_from_dict({"story_digest": "s", "entry_digest": "e", "env_id": "x", "worktree_fingerprint": "w",
                              "runtime_digest": "r", "verifier": "v", "env_digest": "d"})      # 没有 context_digest 键
    inherit_now = Baseline("s", "e", "x", "w", runtime_digest="r", verifier="v", env_digest="d", context_digest=None)
    pinned_now = Baseline("s", "e", "x", "w", runtime_digest="r", verifier="v", env_digest="d", context_digest="sha256:abc")
    assert evaluate_validity(old, inherit_now)[0] == Validity.CURRENT
    v, reasons = evaluate_validity(old, pinned_now)
    assert v == Validity.STALE and "execution context policy changed" in reasons
    assert compare_aspects(old, pinned_now)["context"] == "changed" and compare_aspects(old, inherit_now)["context"] == "same"


# ---------------------------------------------------------------- 真实执行: 两个不同宿主

@pytest.fixture
def pinned(tmp_path):
    p = Proj(tmp_path / "p", tests=ENV_TEST)
    return p, write_cfg(tmp_path, p, PINNED)


HOST_A = {"FT_HOST_ONLY": "a", "FT_DB_PASSWORD": SECRET, "FT_NOISE_A": "1", "HOME": "/tmp/home-a"}
HOST_B = {"FT_HOST_ONLY": "b", "FT_DB_PASSWORD": SECRET, "FT_NOISE_B": "2", "HOME": "/tmp/home-b", "LANG": "C"}


def test_pinned_verify_constrains_the_real_subprocess_environment(pinned):
    p, cfg = pinned
    r, res = ws_cli(p, cfg, "verify", HOST_A, "--mapped-only")
    assert r.returncode == 0, res                      # 测试内断言: FT_HOST_ONLY 未泄入、字面值与宿主凭据已传入
    assert units(res)["SAV-001.CASE-01"]["automation"] == "passed"
    mf = json.loads(next((p.root / ".flowtree/runs").glob("*/*/M-01/manifest.json")).read_text())
    assert set(mf["env_vars"]) == {"PATH", "PYTHONPATH", "FT_RATE", "FT_DB_PASSWORD"}          # 摘要覆盖的就是实际传入的环境
    assert mf["context"]["mode"] == "pinned" and mf["context"]["env_from_host"] == ["FT_DB_PASSWORD"]
    assert mf["baseline"]["context_digest"] and mf["baseline"]["env_digest"]
    assert SECRET.encode() not in all_flowtree_text(p.root) and SECRET not in r.stdout + r.stderr


def test_cli_and_web_rechecks_agree_across_different_hosts(pinned, api, monkeypatch):
    p, cfg = pinned
    assert ws_cli(p, cfg, "verify", HOST_A, "--mapped-only")[0].returncode == 0
    # 与执行时不同的宿主 (不同的无关变量、HOME、LANG): CLI 重检仍是 current
    r, st = ws_cli(p, cfg, "status", HOST_B)
    e = entry(st)
    assert r.returncode == 0 and e["validity"] == "current" and set(e["aspects"].values()) == {"same"}
    assert units(st)["SAV-001.CASE-01"]["automation"] == "passed"
    # Web 在第三种宿主下 (只读重检) 结果一致
    c, _ = api
    d = web(c, monkeypatch, cfg, {"FT_HOST_ONLY": "web", "FT_DB_PASSWORD": SECRET, "WEB_ONLY_VAR": "1"})
    we = wunit(d)["entries"][0]
    assert we["validity"] == "current" and set(we["aspects"].values()) == {"same"} and wunit(d)["automation"] == "passed"
    assert d["context"]["execution_context"]["mode"] == "pinned"
    assert SECRET not in json.dumps(d)


def test_undeclared_host_variable_changes_do_not_change_a_pinned_context(pinned):
    p, cfg = pinned
    ws_cli(p, cfg, "verify", HOST_A, "--mapped-only")
    for host in ({**HOST_A, "FT_HOST_ONLY": "zzz"}, {**HOST_A, "NEW_UNDECLARED": "1"}, {"FT_DB_PASSWORD": SECRET}):
        r, st = ws_cli(p, cfg, "status", host)
        assert entry(st)["validity"] == "current", host


def test_declared_literal_change_invalidates_and_names_the_variable(pinned, tmp_path):
    p, cfg = pinned
    ws_cli(p, cfg, "verify", HOST_A, "--mapped-only")
    cfg2 = write_cfg(tmp_path, p, {**PINNED, "env": {"FT_RATE": "3"}})
    r, st = ws_cli(p, cfg2, "status", HOST_B)
    e = entry(st)
    assert e["validity"] == "stale" and e["aspects"]["environment"] == "changed" and e["aspects"]["worktree"] == "same"
    assert "FT_RATE" in e["changed_env_names"] and units(st)["SAV-001.CASE-01"]["automation"] == "not_run"


def test_declared_host_variable_value_change_invalidates_without_leaking_values(pinned, api, monkeypatch):
    p, cfg = pinned
    ws_cli(p, cfg, "verify", HOST_A, "--mapped-only")
    new = "pw2-DIFFERENT-VALUE"
    r, st = ws_cli(p, cfg, "status", {**HOST_B, "FT_DB_PASSWORD": new})
    e = entry(st)
    assert e["validity"] == "stale" and "FT_DB_PASSWORD" in e["changed_env_names"]
    assert new not in r.stdout and SECRET not in r.stdout
    c, _ = api
    d = web(c, monkeypatch, cfg, {"FT_DB_PASSWORD": new})
    assert wunit(d)["entries"][0]["validity"] == "stale" and new not in json.dumps(d)


def test_missing_required_host_variable_blocks_execution_and_makes_recheck_unknown(pinned, api, monkeypatch):
    p, cfg = pinned
    clean = {k: v for k, v in os.environ.items() if k != "FT_DB_PASSWORD"}
    import subprocess
    r = subprocess.run([sys.executable, "-m", "cli.main", "workspace", "verify", "ws1", "--config", str(cfg), "--json", "--mapped-only"],
                       cwd=ROOT, env=clean, capture_output=True, text=True, timeout=120)
    res = json.loads(r.stdout)
    assert r.returncode == 1 and res["executed"] is True
    a = res["attempts"][0]
    assert a["state"] == "blocked" and "FT_DB_PASSWORD" in a["reason"] and "unresolved" in a["reason"]
    assert not list((p.root / ".flowtree/runs").glob("*/*/M-01/stdout.txt"))            # 没有任何子进程被启动
    assert res["context_problems"]
    # 先在满足的宿主里真实执行, 再在缺变量的宿主里重检: 未知, 不退回宿主环境
    assert ws_cli(p, cfg, "verify", HOST_A, "--mapped-only")[0].returncode == 0
    st = json.loads(subprocess.run([sys.executable, "-m", "cli.main", "workspace", "status", "ws1", "--config", str(cfg), "--json"],
                                   cwd=ROOT, env=clean, capture_output=True, text=True, timeout=120).stdout)
    e = entry(st)
    assert e["validity"] == "unknown" and e["aspects"]["environment"] == "unknown" and st["context_problems"]
    assert units(st)["SAV-001.CASE-01"]["automation"] != "passed"
    c, _ = api
    d = web(c, monkeypatch, cfg, drop=("FT_DB_PASSWORD",))
    assert wunit(d)["entries"][0]["validity"] == "unknown" and wunit(d)["automation"] != "passed"
    rc = d["context"]["recheck"]
    assert rc["can_determine_validity"] is False and any("FT_DB_PASSWORD" in x for x in rc["workspace_problems"])


def test_inherit_mode_is_unchanged_and_host_variables_still_matter(tmp_path):
    p = Proj(tmp_path / "p", tests="import os\ndef test_zero_amount_rejected():\n    assert os.environ['FT_HOST_ONLY'] == 'a'\ndef test_resume_after_lost_response(): pass\n")
    cfg = write_cfg(tmp_path, p, {})
    r, res = ws_cli(p, cfg, "verify", {"FT_HOST_ONLY": "a"}, "--mapped-only")
    assert r.returncode == 0                                       # 默认继承: 宿主变量进入测试
    mf = json.loads(next((p.root / ".flowtree/runs").glob("*/*/M-01/manifest.json")).read_text())
    assert mf["baseline"]["context_digest"] is None and mf["context"]["mode"] == "inherit" and len(mf["env_vars"]) > 10
    r, st = ws_cli(p, cfg, "status", {"FT_HOST_ONLY": "b"})
    e = entry(st)
    assert e["validity"] == "stale" and e["aspects"]["environment"] == "changed" and "FT_HOST_ONLY" in e["changed_env_names"]


def test_legacy_commands_still_work_and_their_evidence_is_current_under_inherit_workspace(tmp_path):
    p = Proj(tmp_path / "p")
    assert p.verify()[0].returncode == 0                           # 旧命令 `flowtree verify`
    cfg = write_cfg(tmp_path, p, {})
    r, st = ws_cli(p, cfg, "status", {})                           # 新命令读取旧命令产生的证据
    assert entry(st)["validity"] == "current" and entry(st)["aspects"]["context"] == "same"


def test_switching_mode_invalidates_old_evidence_both_ways(tmp_path):
    p = Proj(tmp_path / "p", tests=ENV_TEST.replace('assert os.environ.get("FT_HOST_ONLY") is None, "undeclared host variable leaked into the pinned test"', "pass"))
    inh = write_cfg(tmp_path, p, {"env": {"FT_RATE": "2"}, "env_from_host": ["FT_DB_PASSWORD"]}, name="inh.yaml")
    assert ws_cli(p, inh, "verify", HOST_A, "--mapped-only")[0].returncode == 0
    pin = write_cfg(tmp_path, p, PINNED, name="pin.yaml")
    r, st = ws_cli(p, pin, "status", HOST_A)
    e = entry(st)
    assert e["validity"] == "stale" and e["aspects"]["context"] == "changed"
    assert ws_cli(p, pin, "verify", HOST_A, "--mapped-only")[0].returncode == 0
    r, st = ws_cli(p, inh, "status", HOST_A)                       # 回到 inherit: 最新证据是 pinned 的 → 失效
    assert entry(st)["validity"] == "stale" and entry(st)["aspects"]["context"] == "changed"
    r, st = ws_cli(p, pin, "status", HOST_B)
    assert entry(st)["validity"] == "current"


def test_pinned_git_isolation_makes_the_fingerprint_independent_of_host_git_config(tmp_path):
    p = Proj(tmp_path / "p", tests=ENV_TEST)
    cfg = write_cfg(tmp_path, p, PINNED)
    (p.root / "scratch_untracked.txt").write_text("x")
    global_ignore = tmp_path / "global_ignore"; global_ignore.write_text("scratch_untracked.txt\n")
    gitcfg = tmp_path / "gitconfig"; gitcfg.write_text(f"[core]\n\texcludesFile = {global_ignore}\n")
    host_with_global_ignore = {**HOST_A, "GIT_CONFIG_GLOBAL": str(gitcfg), "GIT_CONFIG_NOSYSTEM": "0"}
    assert ws_cli(p, cfg, "verify", host_with_global_ignore, "--mapped-only")[0].returncode == 0
    r, st = ws_cli(p, cfg, "status", HOST_B)                       # 另一个宿主没有该全局忽略规则: 指纹仍一致
    assert entry(st)["validity"] == "current" and entry(st)["aspects"]["worktree"] == "same"


def test_git_excludes_file_content_is_part_of_the_context_policy(tmp_path):
    p = Proj(tmp_path / "p", tests=ENV_TEST)
    ex = tmp_path / "excl"; ex.write_text("*.log\n")
    ctx = {**PINNED, "git_excludes_file": str(ex)}
    cfg = write_cfg(tmp_path, p, ctx)
    assert ws_cli(p, cfg, "verify", HOST_A, "--mapped-only")[0].returncode == 0
    assert entry(ws_cli(p, cfg, "status", HOST_B)[1])["validity"] == "current"
    ex.write_text("*.log\n*.tmp\n")                                 # 排除规则内容变了 → 上下文策略变了
    e = entry(ws_cli(p, cfg, "status", HOST_B)[1])
    assert e["validity"] == "stale" and e["aspects"]["context"] == "changed"


# ---------------------------------------------------------------- Web 缓存与只读性

def test_cache_identity_includes_the_context_policy(pinned, api, monkeypatch, tmp_path):
    p, cfg = pinned
    ws_cli(p, cfg, "verify", HOST_A, "--mapped-only")
    c, view = api
    d = web(c, monkeypatch, cfg, {"FT_DB_PASSWORD": SECRET})
    assert wunit(d)["entries"][0]["validity"] == "current"
    other = write_cfg(tmp_path, p, {**PINNED, "env": {"FT_RATE": "3"}})
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(other))              # 同 id, 只改上下文策略, 不强制刷新
    d2 = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    assert wunit(d2)["entries"][0]["validity"] == "stale"
    inh = write_cfg(tmp_path, p, {"env": {"FT_RATE": "2"}})
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(inh))
    assert c.get("/api/workspaces/ws1/stories/SAV-001").json()["context"]["execution_context"]["mode"] == "inherit"


def test_web_recheck_in_pinned_mode_writes_nothing_even_without_salt(tmp_path, api, monkeypatch):
    p = Proj(tmp_path / "p", tests=ENV_TEST)
    cfg = write_cfg(tmp_path, p, PINNED)
    c, _ = api
    before = sorted(str(x.relative_to(p.root)) for x in p.root.rglob("*") if ".git" not in x.parts)
    d = web(c, monkeypatch, cfg, {"FT_DB_PASSWORD": SECRET})
    assert wunit(d)["automation"] == "not_run"
    after = sorted(str(x.relative_to(p.root)) for x in p.root.rglob("*") if ".git" not in x.parts)
    assert after == before and not (p.root / ".flowtree").exists()


def test_old_environment_independent_evidence_is_never_edited_to_become_current(pinned):
    p, cfg = pinned
    ws_cli(p, cfg, "verify", HOST_A, "--mapped-only")
    mp = next((p.root / ".flowtree/runs").glob("*/*/M-01/manifest.json"))
    before = mp.read_bytes()
    ws_cli(p, cfg, "status", HOST_B); ws_cli(p, write_cfg(p.root.parent, p, {**PINNED, "env": {"FT_RATE": "9"}}), "status", HOST_B)
    assert mp.read_bytes() == before


# ---------------------------------------------------------------- CLI 与配置

def test_workspace_cli_commands_and_error_exit_codes(pinned, tmp_path):
    p, cfg = pinned
    r = p.cli("workspace", "list", "--config", str(cfg), "--json")
    assert r.returncode == 0 and json.loads(r.stdout)[0]["mode"] == "pinned"
    r = p.cli("workspace", "context", "ws1", "--config", str(cfg), "--json", env={"FT_DB_PASSWORD": SECRET})
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["mode"] == "pinned" and out["env_from_host"] == ["FT_DB_PASSWORD"] and SECRET not in r.stdout
    clean = {k: v for k, v in os.environ.items() if k != "FT_DB_PASSWORD"}
    import subprocess
    r = subprocess.run([sys.executable, "-m", "cli.main", "workspace", "context", "ws1", "--config", str(cfg)], cwd=ROOT, env=clean, capture_output=True, text=True)
    assert r.returncode == 1 and "FT_DB_PASSWORD" in r.stdout
    assert p.cli("workspace", "status", "nope", "--config", str(cfg)).returncode == 1
    assert p.cli("workspace", "verify", "ws1", "--config", str(tmp_path / "absent.yaml")).returncode == 1


def test_config_rejects_secret_literals_unknown_fields_and_bad_shapes(tmp_path):
    from flowtree.workspace import WorkspaceConfigError, load_workspaces
    p = Proj(tmp_path / "p")
    for ctx, msg in [({"env": {"DB_PASSWORD": "x"}}, "secret"), ({"env": {"DATABASE_URL": "mysql://u:p@h/d"}}, "secret"),
                     ({"mode": "weird"}, "mode"), ({"nope": 1}, "unknown execution_context"),
                     ({"env_from_host": "A"}, "list of variable names"), ({"pinned_path": "/x"}, "pinned_path")]:
        cfg = write_cfg(tmp_path, p, ctx)
        with pytest.raises(WorkspaceConfigError, match=msg):
            load_workspaces(cfg)
