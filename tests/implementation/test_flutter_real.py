"""真实 `flutter test` 子进程 + 真实 git 仓库。没有 Flutter SDK 时整组明确跳过 (环境缺失, 不是通过)。"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

import flutter_support as fs
from flutter_support import FLUTTER, NID_A, NID_B, FlutterProj
from impl_support import ROOT

pytestmark = pytest.mark.skipif(FLUTTER is None, reason="Flutter SDK not found (install it or put `flutter` on PATH); Flutter runner NOT verified")


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    return fs.build_template(tmp_path_factory.mktemp("fl") / "tpl")


@pytest.fixture
def proj(template, tmp_path):
    return FlutterProj(template, tmp_path / "p")


def mk(template, tmp_path, tests=None, **kw):
    return FlutterProj(template, tmp_path / "p", tests=tests if tests is not None else fs.DEFAULT_TEST, **kw)


def attempt(res, entry):
    return next(a for a in res["attempts"] if a["entry"].endswith("/" + entry))


def automation(res, unit):
    return next(u for s in res["stories"] for u in s["units"] if u["id"] == f"SAV-001.{unit}")["automation"]


def entry_of(res, qid="SAV-001.CASE-01"):
    return next(u for s in res["stories"] for u in s["units"] if u["id"] == qid)["entries"][0]


# ---------------------------------------------------------------- 通过路径

def test_real_pass_with_two_suites_interleaved_and_complete_evidence(template, tmp_path):
    other = "import 'package:flutter_test/flutter_test.dart';\nvoid main() { test('other works', () async { await Future<void>.delayed(const Duration(milliseconds: 300)); expect(2, 2); }); }\n"
    p = mk(template, tmp_path, extra_tests={"other_test.dart": other})
    p.write_mapping(b="test/other_test.dart::other works", files=("test/savings_test.dart", "test/other_test.dart"))
    r, res = p.verify()
    assert r.returncode == 0, res
    assert automation(res, "CASE-01") == "passed" and automation(res, "CASE-02") == "passed"
    pm, m = p.manifest()
    assert m["runner"] == "flutter" and m["state"] == "completed" and m["exit_code"] == 0 and m["changed_during_run"] is False
    assert m["protocol_version"] == "0.1.1" and m["done_success"] is True and m["real_test_count"] == 3
    assert m["suites"] == ["test/other_test.dart", "test/savings_test.dart"]
    assert "single machine source" in m["evidence_kind"]
    assert set(m["artifacts"]) == {"events", "human", "stderr"}
    assert m["runtime"]["flutter_version"] and m["runtime"]["dart_version"] and m["runtime"]["package_count"] > 0
    assert m["command"]["full_argv"][1:7] == ["--no-version-check", "--suppress-analytics", "test", "--no-pub", "--reporter", "json"]
    assert "--file-reporter" in m["command"]["full_argv"]
    events = (pm.parent / "events.jsonl").read_text()
    assert '"protocolVersion":"0.1.1"' in events and '"type":"done"' in events
    assert (pm.parent / "flutter-human.txt").read_text().strip()          # 人读附件存在, 但不参与判定
    assert m["outcomes"][NID_A]["outcome"] == "passed"
    # 状态读取: 同一上下文下证据有效
    r, st = p.status()
    assert entry_of(st)["validity"] == "current" and automation(st, "CASE-01") == "passed"


# ---------------------------------------------------------------- 失败与不能通过

def test_assertion_failure_is_failed_and_keeps_raw_error_and_stacktrace(template, tmp_path):
    p = mk(template, tmp_path, "import 'package:flutter_test/flutter_test.dart';\nvoid main() {\n  test('zero amount rejected', () { expect(1, 2); });\n  group('G', () { test('resume after lost response', () { expect(1, 1); }); });\n}\n")
    r, res = p.verify()
    assert r.returncode == 1 and attempt(res, "M-01")["state"] == "completed" and attempt(res, "M-01")["exit_code"] == 1
    assert automation(res, "CASE-01") == "failed" and automation(res, "CASE-02") == "passed"
    d = p.manifest()[1]["outcomes"][NID_A]
    assert d["outcome"] == "failed" and "Expected: <2>" in d["errors"][0]["error"] and "savings_test.dart" in d["errors"][0]["stackTrace"]


def test_exception_in_test_body_is_error_not_failed(template, tmp_path):
    p = mk(template, tmp_path, "import 'package:flutter_test/flutter_test.dart';\nvoid main() {\n  test('zero amount rejected', () { throw StateError('boom'); });\n  group('G', () { test('resume after lost response', () {}); });\n}\n")
    r, res = p.verify()
    assert automation(res, "CASE-01") == "error" and automation(res, "CASE-02") == "passed"


def test_skipped_test_is_not_run_even_though_result_is_success(template, tmp_path):
    p = mk(template, tmp_path, "import 'package:flutter_test/flutter_test.dart';\nvoid main() {\n  test('zero amount rejected', () { expect(1, 1); }, skip: 'not yet');\n  group('G', () { test('resume after lost response', () {}); });\n}\n")
    r, res = p.verify()
    assert r.returncode == 1 and automation(res, "CASE-01") == "not_run" and automation(res, "CASE-02") == "passed"
    events = (p.manifest()[0].parent / "events.jsonl").read_text()
    assert '"result":"success","skipped":true' in events          # 事实: success + skipped


def test_compile_error_fails_the_whole_attempt_and_preserves_the_raw_facts(template, tmp_path):
    p = mk(template, tmp_path, "void main() { this is not valid dart }\n")
    r, res = p.verify()
    a = attempt(res, "M-01")
    assert r.returncode == 1 and a["state"] == "error" and automation(res, "CASE-01") == "error"
    assert ("load/setup failure" in a["reason"]) or ("no JSON events" in a["reason"]) or ("no real tests" in a["reason"]) or ("done" in a["reason"]), a["reason"]
    pm, m = p.manifest()
    assert (pm.parent / "events.jsonl").exists() and (pm.parent / "stderr.txt").exists()


def test_same_name_twice_in_one_file_is_an_ambiguous_error_for_the_mapped_test_only(template, tmp_path):
    p = mk(template, tmp_path, "import 'package:flutter_test/flutter_test.dart';\nvoid main() {\n  test('zero amount rejected', () {});\n  test('zero amount rejected', () {});\n  group('G', () { test('resume after lost response', () {}); });\n}\n")
    r, res = p.verify()
    assert r.returncode == 0 or r.returncode == 1
    assert automation(res, "CASE-01") == "error" and automation(res, "CASE-02") == "passed"
    assert "ambiguous" in p.manifest()[1]["outcomes"][NID_A]["reason"]


def test_name_containing_double_colon_is_matched_exactly(template, tmp_path):
    p = mk(template, tmp_path, "import 'package:flutter_test/flutter_test.dart';\nvoid main() {\n  test('a::b c', () { expect(1, 1); });\n  group('G', () { test('resume after lost response', () {}); });\n}\n")
    p.write_mapping(a="test/savings_test.dart::a::b c")
    r, res = p.verify()
    assert r.returncode == 0 and automation(res, "CASE-01") == "passed"


def test_unmapped_failing_test_makes_the_command_fail_but_mapped_truth_stays(template, tmp_path):
    p = mk(template, tmp_path, fs.DEFAULT_TEST.replace("void main() {", "void main() {\n  test('unmapped bug', () { expect(1, 2); });"))
    r, res = p.verify()
    assert r.returncode == 1 and res["ok"] is False and res["commands_clean"] is False
    assert automation(res, "CASE-01") == "passed" and attempt(res, "M-01")["state"] == "completed"
    assert attempt(res, "M-01")["unmapped_nonpass"] == {"test/savings_test.dart::unmapped bug": "failed"}


def test_mapped_test_not_present_is_error(template, tmp_path):
    p = mk(template, tmp_path)
    p.write_mapping(a="test/savings_test.dart::does not exist")
    r, res = p.verify()
    assert automation(res, "CASE-01") == "error" and automation(res, "CASE-02") == "passed"


def test_timeout_terminates_the_whole_flutter_process_tree(template, tmp_path):
    p = mk(template, tmp_path, "import 'package:flutter_test/flutter_test.dart';\nvoid main() {\n  test('zero amount rejected', () async { await Future<void>.delayed(const Duration(seconds: 180)); }, timeout: Timeout.none);\n  group('G', () { test('resume after lost response', () {}); });\n}\n", timeout_s=40)
    t0 = time.time()
    r, res = p.verify("--entry", "M-01")
    a = attempt(res, "M-01")
    assert a["state"] == "error" and "timeout" in a["reason"] and a["cleanup"]["cleared"] is True
    assert time.time() - t0 < 120


# ---------------------------------------------------------------- 前置缺失: 阻塞, 不引导、不联网、不改项目

def snapshot(root: Path):
    out = {}
    for f in sorted(root.rglob("*")):
        if f.is_file() and ".git" not in f.parts and ".flowtree" not in f.parts:
            out[str(f.relative_to(root))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def test_missing_package_config_blocks_without_running_pub_get(template, tmp_path):
    p = mk(template, tmp_path)
    p.package_config().unlink()
    before = snapshot(p.root)
    r, res = p.verify()
    a = attempt(res, "M-01")
    assert a["state"] == "blocked" and "package_config.json missing" in a["reason"] and "pub get" in a["reason"]
    assert not p.package_config().exists() and snapshot(p.root) == before          # 没有 pub get, 项目未被改动
    assert not list((p.root / ".flowtree/runs").glob("*/*/M-01/events.jsonl"))       # 没有启动任何 flutter 进程


def test_missing_dependency_cache_blocks_and_recheck_is_unknown(template, tmp_path):
    p = mk(template, tmp_path)
    assert p.verify()[0].returncode == 0
    cfg = json.loads(p.package_config().read_text())
    victim = next(x for x in cfg["packages"] if x["rootUri"].startswith("file:///"))
    victim["rootUri"] = "file:///definitely/missing/cache/" + victim["name"]
    p.package_config().write_text(json.dumps(cfg))
    r, res = p.verify()
    a = attempt(res, "M-01")
    assert a["state"] == "blocked" and "dependency cache missing" in a["reason"] and victim["name"] in a["reason"]
    r, st = p.status()                                   # 最新尝试是 blocked: 保持可见, 不回退到更早的通过
    assert automation(st, "CASE-01") == "blocked" and entry_of(st)["last_result"] == "blocked"


def test_missing_flutter_executable_and_uninitialised_sdk_are_blocked(template, tmp_path):
    p = mk(template, tmp_path, flutter_arg="/nonexistent/flutter/bin/flutter")
    assert attempt(p.verify()[1], "M-01")["state"] == "blocked"
    fake = tmp_path / "fakesdk" / "bin"; fake.mkdir(parents=True)
    (fake / "flutter").write_text("#!/bin/sh\nexit 0\n"); (fake / "flutter").chmod(0o755)
    p.write_mapping(flutter_arg=str(fake / "flutter"))
    a = attempt(p.verify()[1], "M-01")
    assert a["state"] == "blocked" and "SDK facts unreadable" in a["reason"]


def test_runtime_is_bound_to_ignored_dependency_resolution(template, tmp_path):
    p = mk(template, tmp_path)
    assert p.verify()[0].returncode == 0
    r, st = p.status()
    assert entry_of(st)["validity"] == "current"
    p.package_config().write_text(p.package_config().read_text() + "\n")          # .dart_tool 被 git 忽略, 只能靠运行时摘要发现
    r, st = p.status()
    e = entry_of(st)
    assert e["validity"] == "stale" and e["aspects"]["runtime"] == "changed" and e["aspects"]["worktree"] == "same"
    assert e["last_result"] == "passed" and automation(st, "CASE-01") == "not_run"


def test_source_edit_makes_flutter_evidence_stale_but_keeps_history(template, tmp_path):
    p = mk(template, tmp_path)
    p.verify()
    (p.root / "test/savings_test.dart").write_text("// edit\n" + (p.root / "test/savings_test.dart").read_text())
    e = entry_of(p.status()[1])
    assert e["validity"] == "stale" and e["aspects"]["worktree"] == "changed" and e["last_result"] == "passed"


# ---------------------------------------------------------------- 只读重检

def sdk_state():
    root = Path(os.path.realpath(FLUTTER)).parent.parent
    out = {}
    for d in (root / "bin" / "cache", root / "bin" / "internal"):
        for f in sorted(d.iterdir()):
            if f.is_file():
                st = f.stat()
                out[str(f)] = (st.st_size, st.st_mtime_ns)
    out["lockfile_exists"] = (root / "bin" / "cache" / "lockfile").exists()
    return out


def test_readonly_recheck_never_invokes_flutter_or_dart_and_changes_nothing(template, tmp_path, monkeypatch):
    p = mk(template, tmp_path)
    assert p.verify()[0].returncode == 0
    from flowtree import service
    calls = []
    real_run, real_popen = subprocess.run, subprocess.Popen

    def guard(argv):
        head = os.path.basename(str(argv[0] if isinstance(argv, (list, tuple)) else argv))
        if head in ("flutter", "dart", "flutter.bat"):
            calls.append(argv)
            raise AssertionError(f"read-only recheck must not invoke {argv}")

    monkeypatch.setattr(subprocess, "run", lambda argv, *a, **k: (guard(argv), real_run(argv, *a, **k))[1])
    monkeypatch.setattr(subprocess, "Popen", lambda argv, *a, **k: (guard(argv), real_popen(argv, *a, **k))[1])
    proj_before, sdk_before = snapshot(p.root), sdk_state()
    runs_before = sorted(str(x) for x in (p.root / ".flowtree").rglob("*") if x.is_file())
    res = service.status([p.stories], [p.maps], p.root)
    from flowtree import view
    assert not calls
    e = next(u for s in res["stories"] for u in s["units"] if u["id"] == "SAV-001.CASE-01")["entries"][0]
    assert e["validity"] == "current"
    assert snapshot(p.root) == proj_before and sdk_state() == sdk_before
    assert sorted(str(x) for x in (p.root / ".flowtree").rglob("*") if x.is_file()) == runs_before


# ---------------------------------------------------------------- pinned 与 Web

def ws_cfg(tmp_path, p, ctx, name="ws.yaml"):
    cfg = {"workspaces": [{"id": "ws1", "name": "w", "project_root": str(p.root), "stories": [str(p.stories)], "mappings": [str(p.maps)],
                           "execution_context": ctx}]}
    f = tmp_path / name
    f.write_text(yaml.safe_dump(cfg))
    return f


def pinned_ctx():
    return {"mode": "pinned", "pinned_path": f"{Path(FLUTTER).parent}:/usr/bin:/bin", "env_from_host": ["HOME"]}


def test_pinned_flutter_context_is_stable_across_hosts_and_requires_home(template, tmp_path):
    p = mk(template, tmp_path, flutter_arg="flutter")
    cfg = ws_cfg(tmp_path, p, pinned_ctx())

    def wscli(verb, host=None, *extra, drop=()):
        env = {k: v for k, v in os.environ.items() if k not in drop}
        env.update(host or {})
        r = subprocess.run([sys.executable, "-m", "cli.main", "workspace", verb, "ws1", "--config", str(cfg), "--json", *extra],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        return r, json.loads(r.stdout)

    r, res = wscli("verify", {"FT_HOST_ONLY": "a"}, "--mapped-only")
    assert r.returncode == 0, res
    r, st = wscli("status", {"FT_HOST_ONLY": "b", "OTHER": "1"})
    e = entry_of(st)
    assert e["validity"] == "current" and set(e["aspects"].values()) == {"same"}
    # HOME 缺失: 明确阻塞 (否则 flutter 会把状态文件写进项目), 重检 unknown
    before = snapshot(p.root)
    r, res = wscli("verify", None, "--mapped-only", drop=("HOME",))
    assert r.returncode == 1 and res["context_problems"] and "HOME" in " ".join(res["context_problems"])
    assert attempt(res, "M-01")["state"] == "blocked" and snapshot(p.root) == before
    ctx = pinned_ctx(); ctx["env_from_host"] = []
    cfg2 = ws_cfg(tmp_path, p, ctx, "ws2.yaml")
    r = subprocess.run([sys.executable, "-m", "cli.main", "workspace", "verify", "ws1", "--config", str(cfg2), "--json", "--mapped-only"],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    a = attempt(json.loads(r.stdout), "M-01")
    assert a["state"] == "blocked" and "HOME is not set" in a["reason"] and snapshot(p.root) == before


def test_web_shows_flutter_evidence_and_refuses_tampered_artifacts(template, tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient
    import app.main as m
    from flowtree import view
    p = mk(template, tmp_path)
    assert p.verify()[0].returncode == 0
    cfg = ws_cfg(tmp_path, p, {})
    monkeypatch.setenv("FLOWTREE_WORKSPACES", str(cfg)); view._cache.clear()
    c = TestClient(m.app)
    d = c.get("/api/workspaces/ws1/stories/SAV-001").json()
    u = next(x for st in d["flow"] for x in [st] + st["branches"] if x["qid"] == "SAV-001.CASE-01")["unit"]
    e = u["entries"][0]
    assert e["validity"] == "current" and e["tests"][0]["nodeid"] == NID_A and e["tests"][0]["outcome"] == "passed"
    ref = e["ref"]
    base = f"/api/workspaces/ws1/attempts/{ref['run']}/{ref['story']}/{ref['entry']}"
    a = c.get(base).json()
    assert a["runner"] == "flutter" and a["flutter"]["done_success"] is True and a["runtime"]["flutter_version"]
    assert {x["name"] for x in a["artifacts"]} == {"events", "human", "stderr"}
    assert '"type":"done"' in c.get(f"{base}/artifacts/events").json()["text"]
    ev = next((p.root / ".flowtree/runs").glob("*/*/M-01/events.jsonl"))
    ev.write_text(ev.read_text() + " ")
    assert c.get(f"{base}/artifacts/events").status_code == 409
