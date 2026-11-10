"""CLI / MCP / Web 共用的领域服务。返回可序列化结构, 退出码语义由调用方按命令职责决定。"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .issues import Issue, has_errors
from .mapping import LoadedMapping, load_mappings
from .status import compute_units, summarize
from .story import collect_yaml_files, empty_input_issues, load_stories


def _issues_out(issues: List[Issue]) -> List[Dict[str, Any]]:
    return [i.to_dict() for i in issues]


def _load(story_paths: List[Path], mapping_paths: Optional[List[Path]]):
    stories = load_stories(story_paths)
    mappings: List[LoadedMapping] = load_mappings(mapping_paths, stories) if mapping_paths else []
    issues = empty_input_issues(story_paths, "story.no_files", "story")
    if mapping_paths:  # 未提供映射与提供了却没发现文件是两回事
        issues += empty_input_issues(mapping_paths, "mapping.no_files", "mapping")
    issues += stories.issues
    if not stories.stories and not any(i.severity == "error" for i in issues):
        issues.append(Issue("error", "story.none_loaded", "stories", "no story was loaded from the given inputs"))
    owner: Dict[Any, Any] = {}
    for m in mappings:
        issues.extend(m.issues)
        if m.mapping is None:
            continue
        for e in m.mapping.entries:
            key = (m.mapping.story, e.id)
            if key in owner and owner[key] != m.path:
                issues.append(Issue("error", "mapping.duplicate_entry", f"{m.mapping.story}/{e.id}",
                                    f"entry defined in both {owner[key]} and {m.path}; evidence would be ambiguous"))
            owner.setdefault(key, m.path)
    return stories, mappings, issues


def validate(story_paths: List[Path], mapping_paths: Optional[List[Path]] = None) -> Dict[str, Any]:
    """格式与引用校验。合法的待确认问题 (open_questions) 作为信息报告, 不使校验失败。"""
    stories, mappings, issues = _load(story_paths, mapping_paths)
    story_rows = []
    for sid, ls in stories.stories.items():
        s = ls.story
        typed = sorted(k for k, v in s.inputs.items() if isinstance(v, dict) and "type" in v)
        story_rows.append({
            "id": sid,
            "path": str(ls.path),
            "digest": ls.digest,
            "units": s.unit_ids(),
            "open_questions": [
                {"id": q.id, "text": q.text, "blocks": q.blocks, "legacy": q.legacy}
                for q in s.open_questions
            ],
            "typed_inputs": typed,
            "untyped_inputs": sorted(k for k in s.inputs if k not in typed),
        })
    mapping_rows = [
        {
            "path": str(m.path),
            "story": m.mapping.story if m.mapping else None,
            "digest": m.digest,
            "entries": dict(m.entry_digests),
        }
        for m in mappings
    ]
    return {
        "ok": not has_errors(issues),
        "stories": story_rows,
        "mappings": mapping_rows,
        "issues": _issues_out(issues),
    }


def plan(story_paths: List[Path], mapping_paths: Optional[List[Path]] = None) -> Dict[str, Any]:
    """只生成计划: 列出分母、映射、未映射与待确认项。不执行任何测试, 因此自动验证只会是 unmapped / not_run。"""
    stories, mappings, issues = _load(story_paths, mapping_paths)
    out_stories = []
    # B1a 尚无证据读取; B1b 起由 evidence 层提供 evidence / current_baselines
    for sid, ls in stories.stories.items():
        views = compute_units(ls, mappings, evidence={}, current_baselines={})
        out_stories.append({
            "id": sid,
            "digest": ls.digest,
            "summary": summarize(views),
            "units": [
                {
                    "id": v.unit_id,
                    "rule": v.rule.value,
                    "blocked_by": v.blocked_by,
                    "implementation": v.implementation.value,
                    "automation": v.automation.value,
                    "human": v.human.value,
                    "entries": [e.entry_id for e in v.entries],
                }
                for v in views
            ],
            "unmapped": [v.unit_id for v in views if v.automation.value == "unmapped"],
        })
    return {
        "ok": not has_errors(issues),
        "executed": False,
        "stories": out_stories,
        "issues": _issues_out(issues),
    }


# ---------------------------------------------------------------- B1b: 执行与证据状态

def _units_out(views) -> List[Dict[str, Any]]:
    return [
        {
            "id": v.unit_id, "rule": v.rule.value, "blocked_by": v.blocked_by,
            "implementation": v.implementation.value, "automation": v.automation.value, "human": v.human.value,
            "entries": [
                {"entry": e.entry_id, "run_id": e.run_id, "validity": e.validity.value if e.validity else None,
                 "validity_reasons": e.validity_reasons, "last_result": e.result.value if e.result else None,
                 "counts_for_current": e.contributes_current.value if e.contributes_current else None}
                for e in v.entries
            ],
        }
        for v in views
    ]


def _spec_files(story_paths, mapping_paths) -> frozenset:
    import os
    return frozenset(Path(os.path.realpath(p)) for p in collect_yaml_files(list(story_paths) + list(mapping_paths or [])))


@dataclass
class State:
    """某一时刻、某一执行上下文下的证据与当前基线 (只读收集, 不执行测试, 不写被测项目)。"""
    evidence: Dict[Any, Any] = field(default_factory=dict)      # (story, entry) -> EntryEvidence
    current: Dict[Any, Any] = field(default_factory=dict)       # (story, entry) -> 当前 Baseline
    env_now: Dict[Any, Any] = field(default_factory=dict)       # (story, entry) -> 当前环境变量 HMAC 映射
    records: Dict[Any, Any] = field(default_factory=dict)       # (story, entry) -> 最新 AttemptRecord (含 manifest)
    problems: List[str] = field(default_factory=list)
    checked_at: str = ""


def collect_state(stories, mappings, project_root: Path, python: Optional[str], spec_files: frozenset = frozenset(),
                  extra_env: Optional[Dict[str, str]] = None, readonly: bool = True) -> State:
    from datetime import datetime, timezone
    from .evidence import EvidenceStore, latest_record
    from . import baseline as bl
    from .execution import child_env, current_baseline

    root = Path(project_root).resolve()
    store = EvidenceStore(root, readonly=readonly)
    all_records = store.load_attempts()
    st = State(checked_at=datetime.now(timezone.utc).isoformat())
    runtime_cache: Dict[str, Any] = {}
    salt = bl.env_salt(root, create=not readonly)
    env = child_env(extra_env)
    for lm in mappings:
        if lm.mapping is None or lm.mapping.story not in stories.stories:
            continue
        ls = stories.stories[lm.mapping.story]
        for e in lm.mapping.entries:
            key = (lm.mapping.story, e.id)
            ev, probs = store.latest_evidence(*key, _records=all_records)
            st.problems.extend(probs)
            if ev is not None:
                st.evidence[key] = ev
                st.records[key] = latest_record(all_records[0], *key)
            st.current[key] = current_baseline(ls, lm, e, root, python, runtime_cache, spec_files, extra_env, readonly)
            st.env_now[key] = bl.env_vars_map(env, e.env.ignore, salt) if salt is not None else {}
    st.problems = sorted(set(st.problems))
    return st


def _status_core(stories, mappings, project_root: Path, python: Optional[str], spec_files: frozenset = frozenset(),
                 extra_env: Optional[Dict[str, str]] = None):
    state = collect_state(stories, mappings, project_root, python, spec_files, extra_env, readonly=True)
    evidence, current, env_now, problems = state.evidence, state.current, state.env_now, state.problems
    out, all_views = [], {}
    for sid, ls in stories.stories.items():
        views = compute_units(ls, mappings, evidence, current)
        all_views[sid] = views
        units = _units_out(views)
        for u in units:  # 环境配置变化时指出是哪些变量 (只有名称, 不暴露值)
            for e in u["entries"]:
                if any("environment configuration" in r for r in e["validity_reasons"]):
                    old, new = evidence[(sid, e["entry"])].env_vars, env_now[(sid, e["entry"])]
                    names = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
                    if names:
                        e["validity_reasons"].append("changed environment variables: " + ", ".join(names)
                                                     + " (declare irrelevant ones under env.ignore)")
        out.append({"id": sid, "digest": ls.digest, "summary": summarize(views), "units": units})
    command_failures = [
        {"story": k[0], "entry": k[1], "run_id": ev.run_id, "exit_code": ev.exit_code, "unmapped_nonpass": ev.command_nonpass}
        for k, ev in sorted(evidence.items())
        if not ev.corrupt and ev.state.value == "completed" and ev.exit_code not in (0, None)
    ]
    return out, all_views, problems, command_failures


def status(story_paths: List[Path], mapping_paths: Optional[List[Path]], project_root: Path,
           python: Optional[str] = None) -> Dict[str, Any]:
    """读取已有证据并结合当前基线展示状态。不执行测试; 成功读取即 ok, 与是否存在未验项无关。"""
    stories, mappings, issues = _load(story_paths, mapping_paths)
    out, _, problems, cmd_fail = _status_core(stories, mappings, project_root, python, _spec_files(story_paths, mapping_paths))
    return {"ok": not has_errors(issues), "executed": False, "stories": out, "command_failures": cmd_fail,
            "evidence_problems": problems, "issues": _issues_out(issues)}


def _resolve_entries(mappings, tokens):
    """解析 --entry。`STORY/ENTRY` 精确匹配; 裸 ID 在多个故事中都存在时歧义→报错; 未知→报错。"""
    all_entries = [(lm.mapping.story, e.id) for lm in mappings if lm.mapping for e in lm.mapping.entries]
    if not tokens:
        return set(all_entries), []
    chosen, errors = set(), []
    for t in tokens:
        if "/" in t:
            hit = [k for k in all_entries if f"{k[0]}/{k[1]}" == t]
        else:
            hit = [k for k in all_entries if k[1] == t]
            if len({k[0] for k in hit}) > 1:
                errors.append(f"--entry {t!r} is ambiguous: it exists in stories {sorted({k[0] for k in hit})}; use STORY/ENTRY")
                continue
        if not hit:
            errors.append(f"--entry {t!r} matches no mapping entry")
        chosen.update(hit)
    return chosen, errors


def _not_executed(issues, reason, extra_issues=()):
    all_issues = list(issues) + [Issue("error", "verify.scope", "verify", m) for m in extra_issues]
    return {"ok": False, "executed": False, "run_id": None, "attempts": [], "stories": [],
            "command_failures": [], "evidence_problems": [], "issues": _issues_out(all_issues), "reason": reason}


def verify(story_paths: List[Path], mapping_paths: List[Path], project_root: Path,
           python: Optional[str] = None, mapped_only: bool = False,
           entry_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """对选中的映射条目各执行一次 (单次 attempt, 无自动重试), 然后按当前基线汇总。
    执行前先解析并校验范围: 输入有 error、选择未知/歧义、或没有任何可执行条目/必需单元 → 不执行, 非成功。
    ok 同时要求: 必需范围内每个单元本次自动验证均 passed (默认必需范围=所给故事的全部单元; 选了 --entry 则为
    这些条目覆盖的单元; --mapped-only 则为已映射单元); 无证据问题; 且每次真实命令本身干净 (completed 且 exit 0)
    —— 未被映射的失败测试也属于这条命令, 不能因为缩小验收分母而被忽略。"""
    from .evidence import EvidenceStore, new_run_id
    from .execution import run_attempt

    stories, mappings, issues = _load(story_paths, mapping_paths)
    if has_errors(issues):
        return _not_executed(issues, "input has validation errors; nothing was executed")
    selected, errors = _resolve_entries(mappings, entry_ids)
    if errors:
        return _not_executed(issues, "invalid --entry selection; nothing was executed", errors)
    if not selected:
        return _not_executed(issues, "no mapping entries to execute; an empty scope is not a success",
                             ["the mappings define no entries"])
    covered = {f"{lm.mapping.story}.{c.partition('.')[2]}" for lm in mappings if lm.mapping
               for e in lm.mapping.entries if (lm.mapping.story, e.id) in selected for c in e.covers}

    project_root = Path(project_root).resolve()
    store = EvidenceStore(project_root)
    run_id = new_run_id()
    spec_files = _spec_files(story_paths, mapping_paths)
    attempts = []
    for lm in mappings:
        ls = stories.stories[lm.mapping.story]
        for entry in lm.mapping.entries:
            if (ls.story.id, entry.id) not in selected:
                continue

            def reload(_ls=ls, _lm=lm, _eid=entry.id):
                st2 = load_stories(story_paths)
                mp2 = load_mappings(mapping_paths, st2)
                for m2 in mp2:
                    if m2.mapping and m2.path == _lm.path and _eid in m2.entry_digests and _ls.story.id in st2.stories:
                        return st2.stories[_ls.story.id], m2, next(e for e in m2.mapping.entries if e.id == _eid)
                return None

            m = run_attempt(store, run_id, ls, lm, entry, project_root, python, reload, spec_files)
            clean = m["state"] == "completed" and m["exit_code"] == 0
            attempts.append({"entry": f"{ls.story.id}/{entry.id}", "state": m["state"], "reason": m["reason"],
                             "exit_code": m["exit_code"], "counts": m["counts"], "command_clean": clean,
                             "unmapped_nonpass": m["unmapped_nonpass"], "cleanup": m["cleanup"],
                             "changed_during_run": m["changed_during_run"],
                             "manifest": str(store.attempt_dir(run_id, ls.story.id, entry.id) / "manifest.json")})
    out, all_views, problems, cmd_fail = _status_core(stories, mappings, project_root, python, spec_files)

    required = [v for views in all_views.values() for v in views
                if (v.unit_id in covered if entry_ids else (v.automation.value != "unmapped" if mapped_only else True))]
    if not required:
        return {**_not_executed(issues, "the required scope contains no units"), "executed": True,
                "run_id": run_id, "attempts": attempts}
    required_ok = all(v.automation.value == "passed" for v in required)
    commands_ok = all(a["command_clean"] for a in attempts)
    return {"ok": required_ok and commands_ok and not problems, "executed": True, "run_id": run_id,
            "attempts": attempts, "stories": out, "command_failures": cmd_fail,
            "evidence_problems": problems, "issues": _issues_out(issues),
            "required_units": len(required), "required_passed": sum(v.automation.value == "passed" for v in required),
            "commands_clean": commands_ok}
