"""只读视图: 把故事 / 映射 / 证据 / 当前基线投影成页面可直接渲染的结构。

约束 (页面浏览不得改变任何事实):
- 不启动测试, 不写被测项目 (证据库以只读方式打开, 环境盐缺失时不创建), 不写验收记录。
- 状态全部来自 flowtree.status.compute_units; 这里只做排版与说明, 不重算状态。
- 把三件事分开: 最近一次执行的结果 (last_result) / 证据对当前上下文是否仍适用 (validity + 分维度 aspects +
  检查时间与上下文) / 当前上下文能否确认 (recheck)。
- 对环境配置只暴露变量名称, 不暴露值。
"""
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import service
from .evidence import EvidenceStore
from .mapping import load_mappings
from .status import AttemptState, Auto, compare_aspects, compute_units, evaluate_validity, summarize
from .story import load_stories
from .workspace import Workspace

TTL_S = 20.0
ARTIFACT_CAP = 256 * 1024
ENV_NAMES_CAP = 40
_cache: Dict[str, Tuple[float, Any]] = {}
_lock = threading.Lock()


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def _build(ws: Workspace):
    """装载故事/映射并收集状态。结果带检查时间, 供页面说明'有效性是何时、在什么上下文里检查的'。"""
    stories = load_stories(ws.stories)
    mappings = load_mappings(ws.mappings, stories) if ws.mappings else []
    issues = list(stories.issues)
    for m in mappings:
        issues.extend(m.issues)
    spec_files = service._spec_files(ws.stories, ws.mappings)
    state = service.collect_state(stories, mappings, ws.project_root, ws.python, spec_files,
                                  ws.context(), readonly=True)
    return {"stories": stories, "mappings": mappings, "issues": issues, "state": state, "problems": ws.problems()}


def cache_key(ws: Workspace) -> str:
    """缓存身份 = 所有会影响结果的工作区配置, 而不只是 id: 配置变化(换项目/路径/解释器/执行上下文)后旧结果不得复用。
    环境变量只参与键, 不会被存储或输出。"""
    return repr((ws.id, str(ws.project_root), ws.python, tuple(map(str, ws.stories)), tuple(map(str, ws.mappings)),
                 ws.context().identity()))


def get_state(ws: Workspace, refresh: bool = False):
    key = cache_key(ws)
    with _lock:
        hit = _cache.get(key)
        if hit and not refresh and time.time() - hit[0] < TTL_S:
            return hit[1]
    data = _build(ws)
    with _lock:
        for k in [k for k in _cache if k.startswith(f"({ws.id!r},")]:  # 同一 id 的旧配置结果不再保留
            del _cache[k]
        _cache[key] = (time.time(), data)
    return data


# ---------------------------------------------------------------- 单元与证据

def _changed_env_names(ev, env_now) -> List[str]:
    old, new = ev.env_vars, env_now
    return sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))


def _entry_out(sid: str, ev_view, state, entries_by_id) -> Dict[str, Any]:
    key = (sid, ev_view.entry_id)
    rec = state.records.get(key)
    m = rec.manifest if rec and rec.manifest else None
    ev = state.evidence.get(key)
    aspects, names = None, []
    if ev is not None and not ev.corrupt and key in state.current:
        aspects = compare_aspects(ev.baseline, state.current[key])
        if aspects["environment"] == "changed":
            names = _changed_env_names(ev, state.env_now.get(key, {}))
    out: Dict[str, Any] = {
        "entry": ev_view.entry_id,
        "has_evidence": ev is not None,
        "run_id": ev_view.run_id,
        "validity": ev_view.validity.value if ev_view.validity else None,
        "validity_reasons": ev_view.validity_reasons,
        "aspects": aspects,
        "changed_env_names": names[:ENV_NAMES_CAP],
        "changed_env_count": len(names),
        "last_result": ev_view.result.value if ev_view.result else None,
        "counts_for_current": ev_view.contributes_current.value if ev_view.contributes_current else None,
        "corrupt": bool(ev and ev.corrupt),
    }
    if m:
        out.update({
            "state": m.get("state"), "reason": m.get("reason"), "started_at": m.get("started_at"),
            "finished_at": m.get("finished_at"), "exit_code": m.get("exit_code"),
            "command_clean": m.get("state") == "completed" and m.get("exit_code") == 0,
            "ref": {"run": m.get("run_id"), "story": m.get("story_id"), "entry": m.get("entry_id")},
            "tests": [{"nodeid": nid, "outcome": (m.get("outcomes", {}).get(nid) or {}).get("outcome"),
                       "reason": (m.get("outcomes", {}).get(nid) or {}).get("reason")}
                      for nid in m.get("required_nodeids", [])],
            "unmapped_nonpass": m.get("unmapped_nonpass") or {},
        })
    return out


def _unit_out(v, sid, state, entries_by_id) -> Dict[str, Any]:
    return {
        "id": v.unit_id.split(".", 1)[1], "qid": v.unit_id,
        "rule": v.rule.value, "blocked_by": v.blocked_by, "implementation": v.implementation.value,
        "automation": v.automation.value, "human": v.human.value,
        "entries": [_entry_out(sid, e, state, entries_by_id) for e in v.entries],
    }


def is_outdated(u: Dict[str, Any]) -> bool:
    """本次未确认, 但存在一份不适用于当前上下文的历史结果 (stale/unknown/损坏): 与"从未执行"不同。"""
    return u["automation"] == "not_run" and any(
        e["has_evidence"] and e["validity"] in ("stale", "unknown") for e in u["entries"])


def _count(units: List[Dict[str, Any]]) -> Dict[str, Any]:
    auto = {a.value: 0 for a in Auto}
    for u in units:
        auto[u["automation"]] += 1
    outdated = sum(1 for u in units if is_outdated(u))
    return {
        "outdated": outdated, "never_run": auto["not_run"] - outdated,
        "total": len(units), "automation": auto,
        "rule_pending": sum(1 for u in units if u["rule"] == "pending"),
        "human_unverified": sum(1 for u in units if u["human"] == "none"),
        # 需要关注 = 本次没有通过 (含未映射/未执行/未知), 折叠时仍要显示
        "attention": sum(1 for u in units if u["automation"] != "passed"),
        "bad": sum(1 for u in units if u["automation"] in ("failed", "error", "blocked")),
    }


def _context(ws: Workspace, data) -> Dict[str, Any]:
    st = data["state"]
    overview = {"current": 0, "stale": 0, "unknown": 0}
    unknown_aspects = set()
    for key, ev in st.evidence.items():
        if ev.corrupt:
            overview["unknown"] += 1
            continue
        v = None
        if key in st.current:
            v, _ = evaluate_validity(ev.baseline, st.current[key])
            for a, r in compare_aspects(ev.baseline, st.current[key]).items():
                if r == "unknown":
                    unknown_aspects.add(a)
        overview[v.value if v else "unknown"] += 1
    problems = data["problems"] + st.context_problems
    can_determine = not problems and not unknown_aspects
    return {
        "checked_at": st.checked_at,
        "project_root": str(ws.project_root),
        "python": ws.python,
        "execution_context": {"mode": st.context.get("mode"), "env_names": st.context.get("env_names"),
                              "env_from_host": st.context.get("env_from_host"),
                              "git_excludes_configured": st.context.get("git_excludes_configured"),
                              "git_isolated": st.context.get("git_isolated"), "problems": st.context_problems},
        "validity_overview": overview,
        "recheck": {
            "can_determine_validity": can_determine,
            "undetermined_aspects": sorted(unknown_aspects),
            "workspace_problems": problems,
            "note": ("有效性是在上述上下文里对证据做的只读比较, 不是重新执行测试。服务进程的环境不一定等于执行时的环境; "
                     "环境、代码、运行时任一不同都会显示待更新, 不会被忽略。要确认 current, 请在与执行时相同的环境中运行 "
                     "`flowtree story status` 或重新 `flowtree verify`。"),
        },
    }


def workspace_card(ws: Workspace, refresh: bool = False) -> Dict[str, Any]:
    data = get_state(ws, refresh)
    return {
        "id": ws.id, "name": ws.name, "project_root": str(ws.project_root),
        "stories": len(data["stories"].stories), "problems": data["problems"],
        "config_issues": [i.to_dict() for i in data["issues"] if i.severity == "error"],
    }


def story_list(ws: Workspace, refresh: bool = False) -> Dict[str, Any]:
    data = get_state(ws, refresh)
    out = []
    for sid, ls in data["stories"].stories.items():
        views = compute_units(ls, data["mappings"], data["state"].evidence, data["state"].current)
        out.append({"id": sid, "title": ls.story.title, "actor": ls.story.actor, "digest": ls.digest,
                    "summary": summarize(views)})
    return {"workspace": ws.id, "checked_at": data["state"].checked_at, "stories": out,
            "evidence_problems": data["state"].problems, "issues": [i.to_dict() for i in data["issues"]]}


def story_detail(ws: Workspace, story_id: str, refresh: bool = False) -> Dict[str, Any]:
    data = get_state(ws, refresh)
    ls = data["stories"].stories.get(story_id)
    if ls is None:
        raise NotFound(f"story {story_id!r} not found in workspace {ws.id!r}")
    st = data["state"]
    s = ls.story
    views = compute_units(ls, data["mappings"], st.evidence, st.current)
    entries_by_id = {e.id: e for lm in data["mappings"] if lm.mapping and lm.mapping.story == story_id for e in lm.mapping.entries}
    by_unit = {v.unit_id.split(".", 1)[1]: _unit_out(v, story_id, st, entries_by_id) for v in views}
    steps = {x.id: x for x in s.main_flow}

    flow = []
    for step in s.main_flow:
        branches = []
        for b in (b for b in s.branches if b.at == step.id):
            tgt = b.continuation.target
            branches.append({
                "id": b.id, "qid": s.qualified(b.id), "kind": b.kind, "condition": b.condition, "expected": b.expected,
                "continuation": {"type": b.continuation.type, "target": tgt,
                                 "target_action": steps[tgt].action if tgt in steps else None},
                "unit": by_unit[b.id],
            })
        flow.append({"id": step.id, "qid": s.qualified(step.id), "action": step.action, "expected": step.expected,
                     "unit": by_unit[step.id], "branches": branches,
                     "branch_summary": _count([b["unit"] for b in branches])})
    all_units = list(by_unit.values())
    summary = summarize(views)
    story_issues = [i.to_dict() for i in data["issues"] if i.where.startswith(story_id) or i.where.startswith(str(ls.path))]
    command_failures = [
        {"entry": k[1], "run_id": ev.run_id, "exit_code": ev.exit_code, "unmapped_nonpass": ev.command_nonpass}
        for k, ev in sorted(st.evidence.items())
        if k[0] == story_id and not ev.corrupt and ev.state == AttemptState.COMPLETED and ev.exit_code not in (0, None)
    ]
    return {
        "workspace": {"id": ws.id, "name": ws.name},
        "story": {"id": s.id, "title": s.title, "actor": s.actor, "goal": s.goal, "digest": ls.digest,
                  "sources": [x.model_dump() for x in s.sources], "preconditions": s.preconditions,
                  "inputs": s.inputs, "invariants": s.invariants,
                  "open_questions": [q.model_dump() for q in s.open_questions]},
        "summary": summary,
        "totals": _count(all_units),
        "flow": flow,
        "context": _context(ws, data),
        "evidence_problems": st.problems,
        "command_failures": command_failures,
        "issues": story_issues,
    }


# ---------------------------------------------------------------- 证据详情

def _find_record(ws: Workspace, run: str, story: str, entry: str):
    store = EvidenceStore(ws.project_root, readonly=True)
    records, _ = store.load_attempts()
    for r in records:
        if r.story_id == story and r.entry_id == entry and r.attempt_id and r.attempt_id.startswith(run + "."):
            return store, r
    raise NotFound("attempt not found")


def attempt_detail(ws: Workspace, run: str, story: str, entry: str) -> Dict[str, Any]:
    store, r = _find_record(ws, run, story, entry)
    m = r.manifest
    if m is None:
        return {"ref": {"run": run, "story": story, "entry": entry}, "integrity_problems": r.problems,
                "manifest_readable": False}
    arts = []
    for name, a in (m.get("artifacts") or {}).items():
        p = (r.dir / a["path"]) if r.dir else None
        arts.append({"name": name, "path": a.get("path"), "sha256": a.get("sha256"),
                     "size": p.stat().st_size if p and p.exists() else None})
    rt = m.get("runtime") or {}
    return {
        "manifest_readable": True,
        "ref": {"run": m.get("run_id"), "story": m.get("story_id"), "entry": m.get("entry_id"), "attempt_id": m.get("attempt_id")},
        "state": m.get("state"), "reason": m.get("reason"), "started_at": m.get("started_at"), "finished_at": m.get("finished_at"),
        "duration_s": m.get("duration_s"), "exit_code": m.get("exit_code"),
        "command_clean": m.get("state") == "completed" and m.get("exit_code") == 0,
        "command": m.get("command"), "timeout_s": m.get("timeout_s"),
        "baseline": m.get("baseline"), "baseline_after": m.get("baseline_after"),
        "changed_during_run": m.get("changed_during_run"),
        "required_nodeids": m.get("required_nodeids"), "outcomes": m.get("outcomes"),
        "counts": m.get("counts"), "junit_counts": m.get("junit_counts"), "unmapped_nonpass": m.get("unmapped_nonpass"),
        "cleanup": m.get("cleanup"), "pytest_rootdir": m.get("pytest_rootdir"),
        "runner": m.get("runner") or "pytest", "evidence_kind": m.get("evidence_kind"),
        "flutter": ({k: m.get(k) for k in ("protocol_version", "done_success", "suites", "real_test_count",
                                           "hidden_events", "event_count", "noise_lines")}
                    if m.get("runner") == "flutter" else None),
        "collected_count": m.get("collected_count"), "deselected_count": m.get("deselected_count"),
        "runtime": {k: rt.get(k) for k in ("executable", "python_version", "pytest_version", "plugin_version", "digest",
                                           "flutter_path", "flutter_version", "flutter_revision", "engine_revision",
                                           "dart_version", "pubspec_lock", "package_config", "package_count", "limitation")},
        "runtime_distribution_count": len(rt.get("distributions", [])),
        "env_variable_names": sorted((m.get("env_vars") or {}))[:200],
        "story_path": m.get("story_path"), "mapping_path": m.get("mapping_path"),
        "artifacts": arts, "integrity_problems": r.problems,
    }


def read_artifact(ws: Workspace, run: str, story: str, entry: str, name: str) -> Dict[str, Any]:
    from .evidence import sha256_file
    store, r = _find_record(ws, run, story, entry)
    if r.manifest is None:
        raise NotFound("manifest unreadable")
    if r.problems:
        # manifest 与索引不一致、身份不符等: manifest 自身不可信, 不能用它记录的哈希来证明产物 (详情接口仍可看到诊断)
        raise Conflict("attempt record failed integrity checks (" + "; ".join(r.problems) + "); artifact is not served as evidence")
    a = (r.manifest.get("artifacts") or {}).get(name)
    if not a or r.dir is None:
        raise NotFound(f"artifact {name!r} not recorded")
    p = (r.dir / a["path"]).resolve()
    try:
        p.relative_to(r.dir.resolve())
    except ValueError:
        raise NotFound("artifact path escapes the attempt directory")
    if not p.exists():
        raise Conflict("artifact file is missing")
    if sha256_file(p) != a["sha256"]:
        raise Conflict("artifact was modified after the run (sha256 mismatch); not displayed as evidence")
    raw = p.read_bytes()
    return {"name": name, "sha256": a["sha256"], "size": len(raw), "truncated": len(raw) > ARTIFACT_CAP,
            "text": raw[:ARTIFACT_CAP].decode("utf-8", "replace")}
