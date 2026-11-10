"""单次 pytest 尝试的受控执行。

- 以 argv 启动子进程, 不经 shell; 指定 cwd 与超时; 子进程在独立进程组, 超时/中断时只终止本次拥有的进程组。
- 解释器选择显式: 映射 argv[0] 是 python* 时, 用 --python 指定的解释器, 否则按子进程 PATH 解析 argv[0]; 找不到→blocked。
  绝不静默改用 FlowTree 自己的解释器。
- 注入 `-p flowtree_pytest_plugin -p no:cacheprovider --junitxml=<唯一路径>`; 清除 PYTEST_ADDOPTS (并记录);
  生效的范围改变选项 (含配置文件 addopts) 由插件如实上报, 出现即 error。
- 先写开始记录再执行; 任何异常都落终态。单次尝试, 无自动重试。
- blocked 仅用于已知环境前置缺失 (cwd/解释器不存在, 解释器无 pytest); 其余执行/收集/解析故障均为 error。
"""
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import baseline as bl
from .evidence import EvidenceStore, baseline_to_dict, now_iso, sha256_file
from .context import ContextSpec, resolve as resolve_context
from .mapping import Entry, LoadedMapping, _pytest_args
from .pytest_report import classify, parse_junit
from .status import AttemptState, Baseline
from .story import LoadedStory

VERIFIER = "flowtree-b1b/2;plugin/1;report/1"
TERM_GRACE_S = 5
KILL_WAIT_S = 5


def child_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """兼容入口: 等价于 inherit 模式下带覆盖项的 resolve()。新代码应直接使用 flowtree.context.resolve。"""
    return resolve_context(ContextSpec(env=dict(extra or {}))).env


def resolve_interpreter(entry: Entry, project_cwd: Path, python: Optional[str], env: Dict[str, str]) -> Optional[str]:
    """argv[0] 实际要执行的可执行文件; None 表示找不到。"""
    head = entry.argv[0]
    if Path(head).name.startswith("python"):
        if python:
            return python if os.path.exists(python) else None
        return shutil.which(head, path=env.get("PATH")) if not os.path.dirname(head) else (
            str((project_cwd / head).resolve()) if (project_cwd / head).exists() else None)
    if os.path.dirname(head):
        p = (project_cwd / head).resolve() if not os.path.isabs(head) else Path(head)
        return str(p) if p.exists() else None
    return shutil.which(head, path=env.get("PATH"))


def probe_python(entry: Entry, exe: Optional[str], python: Optional[str]) -> Optional[str]:
    """用于探测运行时的 python: python* 形式用其本身; pytest 脚本形式必须显式给 --python。"""
    if Path(entry.argv[0]).name.startswith("python"):
        return exe
    return python


def build_command(entry: Entry, exe: str, junit_path: Path) -> List[str]:
    cmd = [exe, *entry.argv[1:]]
    rest_index = len(entry.argv) - len(_pytest_args(entry.argv))
    inject = ["-p", "flowtree_pytest_plugin", "-p", "no:cacheprovider", f"--junitxml={junit_path}"]
    return cmd[:rest_index] + inject + cmd[rest_index:]


def current_baseline(
    story: LoadedStory, mapping: LoadedMapping, entry: Entry, project_root: Path,
    python: Optional[str], runtime_cache: Optional[Dict[str, Optional[str]]] = None,
    spec_files: frozenset = frozenset(), ctx: Optional[ContextSpec] = None, readonly: bool = False,
) -> Baseline:
    """现在的基线 (用于 verify 前后比较, 以及 status 判断历史证据是否仍适用)。
    readonly=True: 不在被测项目里创建任何文件 (环境盐缺失 → env_digest 为 None → 有效性 unknown)。"""
    rc = resolve_context(ctx)
    env, genv = rc.env, rc.effective_git_env
    cwd = (project_root / entry.cwd).resolve() if not os.path.isabs(entry.cwd) else Path(entry.cwd)
    exe = resolve_interpreter(entry, cwd, python, env)
    py = probe_python(entry, exe, python)
    runtime = None
    if py:
        cache = runtime_cache if runtime_cache is not None else {}
        if py not in cache:
            info, _ = bl.probe_runtime(py, env)
            cache[py] = info["digest"] if info else None
        runtime = cache[py]
    fp = bl.worktree_fingerprint(cwd, spec_files, genv) if cwd.exists() else None
    salt = bl.env_salt(project_root, create=not readonly)
    # 上下文未能完整解析 (缺必需宿主变量等): 实际环境不完整, 不能取摘要 → unknown, 不退回宿主环境
    env_d = bl.env_digest(bl.env_vars_map(env, entry.env.ignore, salt)) if salt is not None and not rc.problems else None
    return Baseline(
        story_digest=story.digest, entry_digest=mapping.entry_digests[entry.id], env_id=entry.env.id,
        worktree_fingerprint=fp, git_sha=bl.git_head(cwd, genv) if cwd.exists() else None,
        mapping_digest=mapping.digest, runtime_digest=runtime, verifier=VERIFIER, env_digest=env_d,
        context_digest=rc.context_digest,
    )


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:  # 组存在但不属于我们: 不会发生于自己创建的会话, 保守按存活处理
        return True


def _wait_group_gone(pgid: int, seconds: float) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if not _group_alive(pgid):
            return True
        time.sleep(0.05)
    return not _group_alive(pgid)


def terminate_group(proc: subprocess.Popen) -> Dict[str, Any]:
    """清理本次拥有的进程组 (只用我们创建的 pgid, 不扫描其他进程): SIGTERM → 有期限等待整组退出 →
    仍存活的成员 SIGKILL → 确认整组清空。只等组长不够: 组长退出后孙进程可能忽略 SIGTERM 继续存活。"""
    pgid = proc.pid
    info = {"sigterm": False, "sigkill": False, "cleared": False}
    deadline = time.time() + TERM_GRACE_S
    if _group_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
            info["sigterm"] = True
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=TERM_GRACE_S)  # 回收组长 (僵尸组长也会使整组显示存活)
        except subprocess.TimeoutExpired:
            pass
        _wait_group_gone(pgid, max(0.0, deadline - time.time()))
    if _group_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
            info["sigkill"] = True
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=KILL_WAIT_S)
        except subprocess.TimeoutExpired:
            pass
        _wait_group_gone(pgid, KILL_WAIT_S)
    info["cleared"] = not _group_alive(pgid)
    return info


def run_attempt(
    store: EvidenceStore, run_id: str, story: LoadedStory, mapping: LoadedMapping, entry: Entry,
    project_root: Path, python: Optional[str] = None,
    reload: Optional[Callable[[], Optional[Tuple[LoadedStory, LoadedMapping, Entry]]]] = None,
    spec_files: frozenset = frozenset(), ctx: Optional[ContextSpec] = None,
) -> Dict[str, Any]:
    """reload: 从磁盘重新读取 (故事, 映射, 条目); 用于发现子进程运行期间输入被修改。缺省视为无法确认。"""
    story_id = story.story.id
    attempt_id = f"{run_id}.{story_id}.{entry.id}"
    adir = store.attempt_dir(run_id, story_id, entry.id)
    adir.mkdir(parents=True, exist_ok=True)
    rc = resolve_context(ctx)
    env = dict(rc.env)
    env_base = dict(env)  # 不含本次尝试专属的 FLOWTREE_* 注入
    cwd = (project_root / entry.cwd).resolve() if not os.path.isabs(entry.cwd) else Path(entry.cwd)
    runtime_cache: Dict[str, Optional[str]] = {}
    before = current_baseline(story, mapping, entry, project_root, python, runtime_cache, spec_files, ctx)
    junit_path = adir / "junit.xml"
    report_path = adir / "plugin-report.json"
    env.update({"FLOWTREE_REPORT": str(report_path), "FLOWTREE_RUN_ID": run_id, "FLOWTREE_ATTEMPT_ID": attempt_id})
    exe = resolve_interpreter(entry, cwd, python, env)
    required = [t.nodeid for t in entry.tests]

    m: Dict[str, Any] = {
        "schema": 1, "run_id": run_id, "attempt_id": attempt_id, "story_id": story_id, "entry_id": entry.id,
        "state": AttemptState.RUNNING.value, "reason": None, "started_at": now_iso(), "finished_at": None,
        "timeout_s": entry.timeout_s, "story_path": str(story.path), "mapping_path": str(mapping.path),
        "command": {"argv": entry.argv, "resolved_executable": exe, "cwd": str(cwd), "project_root": str(project_root),
                    "pytest_addopts_removed": rc.removed_addopts},
        "baseline": baseline_to_dict(before), "baseline_after": None, "changed_during_run": False,
        "required_nodeids": required, "outcomes": {}, "counts": {}, "junit_counts": {}, "unmapped_nonpass": {},
        "exit_code": None, "artifacts": {}, "cleanup": None,
        "env_vars": bl.env_vars_map(env_base, entry.env.ignore, bl.env_salt(project_root)),
        "context": rc.summary(),   # 模式/变量名/布尔, 不含任何值
    }
    store.write_manifest(m)  # 开始记录先于执行落盘

    def finish(state: AttemptState, reason: Optional[str]) -> Dict[str, Any]:
        m["state"], m["reason"], m["finished_at"] = state.value, reason, now_iso()
        arts = {}
        for name, fname in (("plugin_report", "plugin-report.json"), ("junit", "junit.xml"),
                            ("stdout", "stdout.txt"), ("stderr", "stderr.txt")):
            p = adir / fname
            if p.exists():
                arts[name] = {"path": fname, "sha256": sha256_file(p)}
        m["artifacts"] = arts
        store.write_manifest(m)
        return m

    proc = None
    try:
        if rc.problems:   # 必需配置缺失: 明确阻塞, 不退回宿主环境
            return finish(AttemptState.BLOCKED, "execution context unresolved: " + "; ".join(rc.problems))
        if not cwd.exists() or not cwd.is_dir():
            return finish(AttemptState.BLOCKED, f"cwd does not exist: {cwd}")
        try:
            cwd.relative_to(project_root)
        except ValueError:
            return finish(AttemptState.ERROR, f"cwd {cwd} is outside project root {project_root}")
        if exe is None:
            return finish(AttemptState.BLOCKED, f"interpreter for {entry.argv[0]!r} not found (pass --python for the project's environment)")
        py = probe_python(entry, exe, python)
        if py:
            info, perr = bl.probe_runtime(py, env)
            if info is None:
                return finish(AttemptState.BLOCKED, perr)

        cmd = build_command(entry, exe, junit_path)
        m["command"]["full_argv"] = cmd
        t0 = time.time()
        with open(adir / "stdout.txt", "wb") as so, open(adir / "stderr.txt", "wb") as se:
            try:
                proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=so, stderr=se, start_new_session=True)
            except OSError as e:
                return finish(AttemptState.ERROR, f"cannot start process: {e}")
            try:
                rc = proc.wait(timeout=entry.timeout_s)
            except subprocess.TimeoutExpired:
                m["cleanup"] = terminate_group(proc)
                m["exit_code"] = proc.returncode
                tail = "process group cleared" if m["cleanup"]["cleared"] else "PROCESS GROUP NOT FULLY CLEARED (members still alive)"
                return finish(AttemptState.ERROR, f"timeout after {entry.timeout_s}s; {tail}")
            except KeyboardInterrupt:
                m["cleanup"] = terminate_group(proc)
                m["exit_code"] = proc.returncode
                finish(AttemptState.ABORTED, "interrupted by user; " + ("process group cleared" if m["cleanup"]["cleared"] else "PROCESS GROUP NOT FULLY CLEARED"))
                raise
        # 命令正常结束后仍存活的同组成员是测试泄漏的进程: 一并清理并记录
        if _group_alive(proc.pid):
            m["cleanup"] = terminate_group(proc)
        m["exit_code"] = rc
        m["duration_s"] = round(time.time() - t0, 3)

        report = None
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                report = None
        junit, jerr = parse_junit(str(junit_path)) if junit_path.exists() else (None, "junit report missing")
        c = classify(report, junit, jerr, run_id=run_id, attempt_id=attempt_id, cwd=str(cwd),
                     returncode=rc, required_nodeids=required)
        m["outcomes"] = c.details
        m["counts"], m["junit_counts"] = c.counts, c.junit
        m["unmapped_nonpass"] = c.unmapped_nonpass
        if report:
            m["runtime"] = report.get("runtime")
            m["pytest_rootdir"] = report.get("rootdir")
            m["collected_count"] = len(report.get("collected", []))
            m["deselected_count"] = len(report.get("deselected", []))

        # 实际运行时与执行前探测、与执行后基线是否一致
        actual_runtime = (report or {}).get("runtime", {}).get("digest")
        fresh = reload() if reload else None
        changed = []
        if fresh is None:
            changed.append("story/mapping unreadable after run")
            after = before
        else:
            after = current_baseline(*fresh, project_root, python, runtime_cache, spec_files, ctx)
        m["baseline_after"] = baseline_to_dict(after)
        if before.worktree_fingerprint != after.worktree_fingerprint or after.worktree_fingerprint is None:
            changed.append("worktree")
        if before.story_digest != after.story_digest or before.entry_digest != after.entry_digest:
            changed.append("story/mapping")
        # 插件没起来 (无报告) 时没有"实际运行时"可比, 沿用执行前探测值; 有报告则以实际为准并与探测比对
        if report is not None and (actual_runtime is None or (before.runtime_digest and before.runtime_digest != actual_runtime)):
            changed.append("runtime")
        base = dict(m["baseline"])
        if report is not None:
            base["runtime_digest"] = actual_runtime
        if changed:
            # 结果保留, 但基线不可信: 指纹置空 → 有效性 unknown, 不贡献当前通过
            m["changed_during_run"] = changed
            base["worktree_fingerprint"] = None
        m["baseline"] = base
        return finish(c.state, c.reason)
    except BaseException as e:
        if isinstance(e, KeyboardInterrupt):
            raise
        if proc is not None:
            m["cleanup"] = terminate_group(proc)
        return finish(AttemptState.ERROR, f"executor failure: {type(e).__name__}: {e}")
