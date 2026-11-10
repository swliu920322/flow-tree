"""Flutter (`flutter test`) 适配。

证据类型 (如实声明): **单一机器来源** —— `flutter test --reporter json` 的事件流 (package:test JSON 协议 0.1.1),
由本次 attempt 的子进程 stdout 直接捕获。没有 JUnit 这样的独立第二来源; 人读 expanded 日志只作原始附件,
**不参与任何判定** (末行 `+N ~M -K` 不是稳定的机器契约)。判定依据: 事件的 suite/test ID 关联与状态一致性、
会话终态 (`done.success`)、进程退出码。

范围只证明: 映射声明的 exact 测试 (相对文件 + 带分组前缀的完整名称) 在**本次事件流里实际执行并成功**。
Flutter 没有 pytest 式的完整收集集合, 因此不能据此声称参数化完整或整文件场景穷尽。

映射参数是**白名单**而非黑名单: argv 只能是 `flutter test <相对的 *_test.dart 文件>...`, 任何以 `-` 开头的选项都拒绝
(筛选/分片/重试/报告器/提前停止等无法被不完整的黑名单可靠排除)。runner 独占注入
`--no-version-check --suppress-analytics`、`--no-pub`、`--reporter json`、`--file-reporter expanded:<附件>`。

运行时探测只读文件, 不调用任何会建缓存/锁文件或联网的 flutter 命令 (并要求上下文提供 HOME, 否则 flutter 会往工作目录写状态文件):
SDK 的 flutter.version.json / dart-sdk/version / engine.version、pubspec.lock 与 .dart_tool/package_config.json 的摘要。
局限: 依赖缓存 (pub cache) 里源码的完整内容不被校验 —— 只绑定 package_config 所记录的包与版本, 并检查缓存目录存在;
不能声称任意缓存篡改都会使证据失效。
"""
import hashlib
import json
import os
import posixpath
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from ..issues import ERROR, Issue
from ..pytest_report import Classification
from ..status import AttemptState, TestOutcome as O
from . import ClassifyOutput, Runner, RuntimeProbe, register

SUPPORTED_PROTOCOLS = {"0.1.1"}
GLOBAL_FLAGS = ["--no-version-check", "--suppress-analytics"]
ERR_CAP = 4000


# ---------------------------------------------------------------- 事件流解析 (纯函数)

def _rel(path: str, cwd: str) -> Optional[str]:
    try:
        return Path(os.path.realpath(path)).relative_to(os.path.realpath(cwd)).as_posix()
    except ValueError:
        return None


def parse_events(text: str) -> Tuple[List[Dict[str, Any]], List[str], int]:
    """逐行解析。非 `{` 开头的行是噪声 (保留计数); `{` 开头却无法解析的行是损坏/截断 → 问题。"""
    events: List[Dict[str, Any]] = []
    problems: List[str] = []
    noise = 0
    for n, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        if not s.startswith("{"):
            noise += 1
            continue
        try:
            ev = json.loads(s)
        except ValueError:
            problems.append(f"corrupt or truncated event line {n}")
            continue
        if not isinstance(ev, dict) or "type" not in ev:
            problems.append(f"event line {n} has no type")
            continue
        events.append(ev)
    return events, problems, noise


def analyze(text: str, *, cwd: str, returncode: int, required: List[str]) -> Tuple[Classification, Dict[str, Any]]:
    """事件流 + 退出码 → 分类。任何无法解释的矛盾都归为 ERROR, 不会因 exit 0 或"有一个通过"而判通过。"""
    extra: Dict[str, Any] = {}

    def err(reason: str, **kw) -> Tuple[Classification, Dict[str, Any]]:
        return Classification(AttemptState.ERROR, reason, **kw), extra

    events, problems, noise = parse_events(text)
    extra["event_count"], extra["noise_lines"] = len(events), noise
    if problems:
        return err(problems[0] + (f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""))
    if not events:
        return err("no JSON events in output (flutter did not produce a report)")
    first = events[0]
    if first["type"] != "start":
        return err("event stream does not begin with a start event")
    proto = first.get("protocolVersion")
    extra["protocol_version"] = proto
    if proto not in SUPPORTED_PROTOCOLS:
        return err(f"unsupported event protocol version {proto!r}")

    # 单次顺序遍历: 唯一的会话 start、唯一且最后的 done、每个测试 ID 自己的生命周期
    # (testStart → [error...] → testDone, 不同测试可以任意交错, 同一测试内必须有序)。
    # 协议关键字段缺失或类型错误是执行 error, 不会被当作"没有这条事件"而放过。
    suites: Dict[Any, Dict[str, Any]] = {}
    all_suites: List[Dict[str, Any]] = []
    started: Dict[Any, Dict[str, Any]] = {}
    finished: Dict[Any, Dict[str, Any]] = {}
    errors: Dict[Any, List[Dict[str, Any]]] = {}
    done_event: Optional[Dict[str, Any]] = None

    def bad(kind: str, e: Dict[str, Any], what: str):
        extra.setdefault("malformed_events", []).append(json.dumps(e, ensure_ascii=False)[:500])
        return err(f"malformed {kind} event ({what}); raw event kept in the report: {json.dumps(e, ensure_ascii=False)[:200]}")

    for idx, e in enumerate(events[1:], start=1):
        t = e["type"]
        if done_event is not None:
            return err("done event is not unique or not the last event (events follow the final done)")
        if t == "start":
            return err("second session start event (duplicated or concatenated sessions)")
        if t == "suite":
            s = e.get("suite")
            if not isinstance(s, dict) or s.get("id") is None or not isinstance(s.get("path"), str):
                return bad("suite", e, "missing suite id/path")
            if s["id"] in suites:
                return err(f"duplicate suite id {s['id']}")
            suites[s["id"]] = s
        elif t == "allSuites":
            if not isinstance(e.get("count"), int) or isinstance(e.get("count"), bool):
                return bad("allSuites", e, "count is not an integer")
            all_suites.append(e)
        elif t == "testStart":
            tt = e.get("test")
            if not isinstance(tt, dict) or tt.get("id") is None or not isinstance(tt.get("name"), str) or tt.get("suiteID") is None:
                return bad("testStart", e, "missing test id/name/suiteID")
            if tt["id"] in started:
                return err(f"duplicate test id {tt['id']}")
            if tt["suiteID"] not in suites:
                return err(f"test {tt['id']} refers to unknown suite {tt['suiteID']} (suite event must come first)")
            started[tt["id"]] = tt
        elif t == "testDone":
            tid = e.get("testID")
            if tid is None or not isinstance(e.get("result"), str) or not isinstance(e.get("skipped"), bool) \
                    or not isinstance(e.get("hidden"), bool):
                return bad("testDone", e, "missing testID/result/skipped/hidden or wrong types")
            if tid not in started:
                return err(f"testDone for unknown test {tid}: it had not started before it finished (out-of-order events)")
            if tid in finished:
                return err(f"test {tid} finished twice")
            finished[tid] = e
        elif t == "error":
            tid = e.get("testID")
            if tid is None or not isinstance(e.get("error"), str) or not isinstance(e.get("isFailure"), bool) \
                    or ("stackTrace" in e and not isinstance(e["stackTrace"], str)):
                return bad("error", e, "missing testID/error/isFailure or wrong types")
            if tid not in started:
                return err(f"error event for unknown test {tid}: it had not started")
            if tid in finished:
                return err(f"error event for test {tid} after its testDone (out-of-order events)")
            errors.setdefault(tid, []).append(e)
        elif t == "done":
            done_event = e
        # 其他事件 (group / print / debug ...) 不是结果: 忽略
    if done_event is None:
        return err("truncated: no done event (session closed early or output cut)")
    success = done_event.get("success")
    extra["done_success"] = success
    if not isinstance(success, bool):
        return err(f"done.success is {success!r}: session closed early, not a result")
    if len(all_suites) != 1 or all_suites[0].get("count") != len(suites):
        return err(f"allSuites does not match the {len(suites)} suite event(s)")
    suite_file: Dict[Any, str] = {}
    for sid, s in suites.items():
        rel = _rel(str(s.get("path", "")), cwd)
        if rel is None:
            return err(f"suite {s.get('path')!r} is outside the working directory (stale or foreign report)")
        suite_file[sid] = rel
    extra["suites"] = sorted(suite_file.values())
    pending = sorted(set(started) - set(finished))
    if pending:
        return err(f"{len(pending)} test(s) started but never finished (e.g. {started[pending[0]].get('name')!r})")

    # 逐测试: 先检查 skipped (result=success 仍可能是跳过), 再检查 result 与 error 事件一致
    hidden: List[Dict[str, Any]] = []
    real: Dict[Any, Tuple[O, str]] = {}
    for tid, t in started.items():
        d = finished[tid]
        result, skipped, is_hidden = d.get("result"), bool(d.get("skipped")), bool(d.get("hidden"))
        if result not in ("success", "failure", "error"):
            return err(f"test {t.get('name')!r} has unknown result {result!r}")
        errs = errors.get(tid, [])
        if result != "success" and not errs:
            return err(f"test {t.get('name')!r} result {result!r} has no error details (inconsistent report)")
        if result == "success" and any(x.get("isFailure") is not None for x in errs):
            return err(f"test {t.get('name')!r} succeeded but reported errors (inconsistent report)")
        if skipped and result != "success":
            return err(f"test {t.get('name')!r} is both skipped and {result!r}")
        # 加载伪测试按身份识别 (名称 == "loading <该 suite 的路径>"), 与 hidden 标记无关: 真实事件流里
        # 加载失败的 testDone 的 hidden 是 false, 只看 hidden 会把编译失败当成一个普通的 error 测试
        is_loading = t.get("name") == f"loading {suites[t['suiteID']].get('path')}"
        if is_hidden or is_loading:
            hidden.append({"name": t.get("name"), "result": result, "skipped": skipped, "hidden": is_hidden, "loading": is_loading,
                           "error": (errs[0].get("error") or "")[:ERR_CAP] if errs else None})
            continue
        meta_skip = bool((t.get("metadata") or {}).get("skip"))
        if skipped or meta_skip:
            real[tid] = (O.SKIPPED, "skipped")
        elif result == "success":
            real[tid] = (O.PASSED, "passed")
        elif result == "failure":
            real[tid] = (O.FAILED, "assertion/test failure")
        else:
            real[tid] = (O.ERROR, "unexpected exception in test body")
    extra["hidden_events"] = hidden
    # 加载/初始化失败 (含 hidden 与加载伪测试): 阻止命令成功。成功的加载伪测试不进入业务测试分母, 但原始事实保留
    bad_hidden = [h for h in hidden if h["result"] != "success"]
    if bad_hidden:
        h0 = bad_hidden[0]
        return err(f"load/setup failure in {'loading' if h0['loading'] else 'hidden'} test {h0['name']!r}: {(h0['error'] or '').strip()[:300]}")
    if not real:
        return err("no real tests ran (zero tests, or only loading pseudo-tests)")

    # 退出码与会话终态
    if returncode not in (0, 1):
        return err(f"flutter test exit status {returncode} (0=all passed, 1=test failures are the only completed states)")
    bad_real = [o for o, _ in real.values() if o in (O.FAILED, O.ERROR)]
    if success and (returncode != 0 or bad_real):
        return err("contradiction: done.success is true but exit code/test results report failures")
    if not success and (returncode == 0 or not bad_real):
        return err("contradiction: done.success is false but exit code/test results report no failure")

    # 身份: (相对文件, 完整名称); 同文件同名多个真实测试 → 对被映射者明确报错, 不猜测
    by_id: Dict[str, List[Any]] = {}
    for tid in real:
        t = started[tid]
        by_id.setdefault(f"{suite_file[t['suiteID']]}::{t['name']}", []).append(tid)
    outcomes: Dict[str, O] = {}
    details: Dict[str, dict] = {}
    for nid in required:
        ids = by_id.get(nid, [])
        if len(ids) > 1:
            outcomes[nid] = O.ERROR
            details[nid] = {"outcome": "error", "reason": f"ambiguous: {len(ids)} real tests in the same file share this name"}
        elif not ids:
            outcomes[nid] = O.MISSING
            details[nid] = {"outcome": "missing", "reason": "not executed in this run"}
        else:
            tid = ids[0]
            o, why = real[tid]
            outcomes[nid] = o
            d = {"outcome": o.value, "reason": why, "skipped": bool(finished[tid].get("skipped"))}
            if errs := errors.get(tid):
                d["errors"] = [{"error": (x.get("error") or "")[:ERR_CAP], "stackTrace": (x.get("stackTrace") or "")[:ERR_CAP],
                                "isFailure": x.get("isFailure")} for x in errs]
            details[nid] = d
    counts: Dict[str, int] = {}
    for o, _ in real.values():
        counts[o.value] = counts.get(o.value, 0) + 1
    req = set(required)
    unmapped = {nid: real[ids[0]][0].value for nid, ids in by_id.items()
                if nid not in req and real[ids[0]][0] in (O.FAILED, O.ERROR)}
    extra["real_test_count"] = len(real)
    return Classification(AttemptState.COMPLETED, None, outcomes, details, counts, {}, unmapped), extra


# ---------------------------------------------------------------- 运行时 (只读)

def _sha(path: Path) -> Optional[str]:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _flutter_root(exe: str) -> Path:
    return Path(os.path.realpath(exe)).parent.parent


def project_dir(cwd: Path, project_root: Path) -> Optional[Path]:
    cur = cwd.resolve()
    root = project_root.resolve()
    while True:
        if (cur / "pubspec.yaml").exists():
            return cur
        if cur == root or cur.parent == cur:
            return None
        cur = cur.parent


def read_runtime(exe: str, cwd: Path, project_root: Path, env: Optional[Dict[str, str]] = None) -> RuntimeProbe:
    if env is not None and not env.get("HOME"):
        # 没有 HOME 时 flutter 会把 .config/flutter、.flutter 写进工作目录 (污染被测项目)。要求执行上下文显式提供
        return RuntimeProbe(None, None, "HOME is not set in the execution context: flutter would write its tool state (.config/flutter, .flutter) into the working directory; declare HOME under env_from_host")
    root = _flutter_root(exe)
    ver_file = root / "bin" / "cache" / "flutter.version.json"
    dart_file = root / "bin" / "cache" / "dart-sdk" / "version"
    engine_file = root / "bin" / "internal" / "engine.version"
    try:
        v = json.loads(ver_file.read_text(encoding="utf-8"))
        dart = dart_file.read_text(encoding="utf-8").strip()
        engine = engine_file.read_text(encoding="utf-8").strip()
    except (OSError, ValueError) as e:
        return RuntimeProbe(None, None, f"Flutter SDK facts unreadable under {root} ({type(e).__name__}); the SDK is not initialised and FlowTree will not bootstrap it")
    pdir = project_dir(cwd, project_root)
    if pdir is None:
        return RuntimeProbe(None, None, f"no pubspec.yaml at or above {cwd} (inside the project root)")
    lock, pkgcfg = _sha(pdir / "pubspec.lock"), pdir / ".dart_tool" / "package_config.json"
    if lock is None:
        return RuntimeProbe(None, None, f"pubspec.lock missing in {pdir}; FlowTree will not run pub get")
    pc_sha = _sha(pkgcfg)
    if pc_sha is None:
        return RuntimeProbe(None, None, f".dart_tool/package_config.json missing in {pdir}; run `flutter pub get` yourself (FlowTree never resolves dependencies)")
    try:
        pkgs = json.loads(pkgcfg.read_text(encoding="utf-8")).get("packages", [])
    except (OSError, ValueError):
        return RuntimeProbe(None, None, "package_config.json is unreadable")
    missing = []
    for p in pkgs:
        u = urlparse(p.get("rootUri", ""))
        d = Path(unquote(u.path)) if u.scheme == "file" else (pkgcfg.parent / unquote(p.get("rootUri", ""))).resolve()
        if not d.is_dir():
            missing.append(p.get("name"))
    if missing:
        return RuntimeProbe(None, None, f"dependency cache missing for {len(missing)} package(s) (e.g. {', '.join(map(str, missing[:5]))}); FlowTree will not download them")
    info = {
        "flutter_path": os.path.realpath(exe), "flutter_version": v.get("frameworkVersion"),
        "flutter_revision": v.get("frameworkRevision"), "engine_revision": v.get("engineRevision") or engine,
        "dart_version": dart, "channel": v.get("channel"), "pubspec_lock": lock, "package_config": pc_sha,
        "package_count": len(pkgs), "project_dir": str(pdir),
        "limitation": "pub-cache package sources are not content-verified; only package_config (names/versions/paths) and directory existence are bound",
    }
    digest = "sha256:" + hashlib.sha256(json.dumps(
        {k: info[k] for k in ("flutter_path", "flutter_version", "flutter_revision", "engine_revision", "dart_version",
                              "pubspec_lock", "package_config")},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    info["digest"] = digest
    return RuntimeProbe(digest, info, None)


# ---------------------------------------------------------------- runner

class FlutterRunner(Runner):
    name = "flutter"
    stdout_file = "events.jsonl"
    evidence_kind = "flutter test JSON event stream (single machine source; no independent JUnit-style second source; expanded log is an attachment only)"
    artifacts = (("events", "events.jsonl"), ("human", "flutter-human.txt"), ("stderr", "stderr.txt"))

    def validate_entry(self, entry, where, issues):
        argv = entry.argv
        if Path(argv[0]).name not in ("flutter", "flutter.bat"):
            issues.append(Issue(ERROR, "mapping.argv_not_flutter", where, "argv must be [flutter, test, <test files>...]"))
            return
        if len(argv) < 3 or argv[1] != "test":
            issues.append(Issue(ERROR, "mapping.argv_not_flutter", where, "argv must be [flutter, test, <test files>...] with at least one file"))
            return
        files: List[str] = []
        for a in argv[2:]:
            if a.startswith("-"):
                issues.append(Issue(ERROR, "mapping.argv_option_not_allowed", where, f"flutter argv option {a!r} is not allowed: only test file paths are accepted; reporter, filtering, sharding, retry and stop-early options cannot be proven not to change the executed scope"))
            elif a.startswith("/") or ".." in posixpath.normpath(a).split("/") or not a.endswith("_test.dart"):
                issues.append(Issue(ERROR, "mapping.argv_flutter_path", where, f"{a!r} must be a relative *_test.dart file inside the project (directories and globs are not accepted)"))
            else:
                files.append(posixpath.normpath(a))
        for j, t in enumerate(entry.tests):
            tw = f"{where}.tests[{j}]"
            file_part, sep, name = t.nodeid.partition("::")     # 只按第一个 :: 分隔, 其余属于原始名称
            if not sep or not name:
                issues.append(Issue(ERROR, "mapping.bad_nodeid", tw, f"flutter test id {t.nodeid!r} must be '<relative file>::<full test name>'"))
            elif name != name.strip():
                issues.append(Issue(ERROR, "mapping.bad_nodeid", tw, "test name must not have leading/trailing whitespace (cannot be matched reliably)"))
            elif posixpath.normpath(file_part) not in files:
                issues.append(Issue(ERROR, "mapping.test_file_not_in_argv", tw, f"{file_part!r} is not one of the test files in argv; only the listed files are executed"))

    def resolve_executable(self, entry, cwd, python, env):
        head = entry.argv[0]
        if os.path.dirname(head):
            p = (cwd / head).resolve() if not os.path.isabs(head) else Path(head)
            return str(p) if p.exists() else None
        return shutil.which(head, path=env.get("PATH"))

    def runtime_cache_key(self, entry, exe, python, cwd):
        return ("flutter", exe, str(cwd)) if exe else None

    def runtime(self, entry, exe, python, env, cwd, project_root):
        if not exe:
            return RuntimeProbe(None)
        return read_runtime(exe, cwd, project_root, env)

    def build_command(self, entry, exe, adir):
        return [exe, *GLOBAL_FLAGS, "test", "--no-pub", "--reporter", "json",
                "--file-reporter", f"expanded:{adir / 'flutter-human.txt'}", *entry.argv[2:]]

    def classify(self, adir, *, run_id, attempt_id, cwd, returncode, required, runtime_now):
        try:
            text = (adir / self.stdout_file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        c, extra = analyze(text, cwd=cwd, returncode=returncode, required=required)
        probe = runtime_now()
        extra["evidence_kind"] = self.evidence_kind
        extra["runtime"] = probe.info
        return ClassifyOutput(c, extra, probe.digest, runtime_applicable=True)


register(FlutterRunner())
