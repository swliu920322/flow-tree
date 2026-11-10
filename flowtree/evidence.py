"""运行证据存储: `.flowtree/runs/<run_id>/<entry_id>/` 是事实记录, SQLite 只是索引。

- 目录布局: runs/<run_id>/<story_id>/<entry_id>/ (条目 ID 只在故事内唯一, 不能充当全局键); 兼容旧布局 runs/<run_id>/<entry_id>/。
- 执行前先写 manifest (state=running) 与索引行; 终态写入后再回写 manifest 与索引。
- manifest 内记录各产物 (插件报告/JUnit/stdout/stderr) 的 sha256; 读取时复核。
- 索引与文件不一致、产物缺失/被改、manifest 损坏 → 该尝试按 ERROR 呈现并上报问题, 绝不推导为通过。
- 单次尝试无自动重试; 同一 (故事, 条目) 以最新一次尝试为准。running 超过 timeout+宽限仍无终态 → aborted。
"""
import hashlib
import json
import os
import sqlite3
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .status import AttemptState, Baseline, EntryEvidence, TestOutcome

MANIFEST_SCHEMA = 1
RUNNING_GRACE_S = 120
BASELINE_FIELDS = ("story_digest", "entry_digest", "env_id", "worktree_fingerprint",
                   "git_sha", "mapping_digest", "runtime_digest", "verifier", "env_digest")
_RUN_TS = re.compile(r"^run_(\d{8})T(\d{6})_")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%S_") + uuid.uuid4().hex[:8]


def baseline_to_dict(b: Baseline) -> Dict[str, Any]:
    return {k: getattr(b, k) for k in BASELINE_FIELDS}


def baseline_from_dict(d: Dict[str, Any]) -> Baseline:
    return Baseline(**{k: d.get(k) for k in BASELINE_FIELDS})


def _atomic_json(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@dataclass
class AttemptRecord:
    """一次尝试的磁盘/索引视图。身份 (故事/条目/时间) 即使 manifest 不可读也尽量从路径与索引恢复,
    使"最新一次尝试损坏"不会被跳过而回退到更早的通过。"""
    dir: Optional[Path]
    manifest: Optional[Dict[str, Any]]
    problems: List[str] = field(default_factory=list)
    story_id: Optional[str] = None
    entry_id: Optional[str] = None
    attempt_id: Optional[str] = None
    started_at: Optional[str] = None


def _ts_from_run_id(run_id: str) -> Optional[str]:
    m = _RUN_TS.match(run_id)
    if not m:
        return None
    d, t = m.groups()
    return f"{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:]}+00:00"


class EvidenceStore:
    def __init__(self, project_root: Path):
        self.root = Path(project_root).resolve()
        self.base = self.root / ".flowtree"
        self.runs_dir = self.base / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base / "data.db"
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS flowtree_attempts (
                attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, story_id TEXT NOT NULL, entry_id TEXT NOT NULL,
                state TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, manifest_sha256 TEXT NOT NULL)""")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def attempt_dir(self, run_id: str, story_id: str, entry_id: str) -> Path:
        return self.runs_dir / run_id / story_id / entry_id

    def _index(self, m: Dict[str, Any], manifest_path: Path) -> None:
        with self._conn() as c:
            c.execute("""INSERT INTO flowtree_attempts VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(attempt_id) DO UPDATE SET state=excluded.state, finished_at=excluded.finished_at,
                manifest_sha256=excluded.manifest_sha256""",
                      (m["attempt_id"], m["run_id"], m["story_id"], m["entry_id"], m["state"],
                       m["started_at"], m.get("finished_at"), sha256_file(manifest_path)))

    def write_manifest(self, m: Dict[str, Any]) -> Path:
        d = self.attempt_dir(m["run_id"], m["story_id"], m["entry_id"])
        d.mkdir(parents=True, exist_ok=True)
        path = d / "manifest.json"
        _atomic_json(path, m)
        self._index(m, path)
        return path

    # ---------- 读取与一致性核对 ----------
    @staticmethod
    def _inspect(d: Path, row: Optional[sqlite3.Row]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        mp = d / "manifest.json"
        if not mp.exists():
            return None, ["manifest missing"]
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
            if not isinstance(m, dict):
                raise ValueError("manifest is not an object")
            for k in ("attempt_id", "story_id", "entry_id", "state", "started_at"):
                if not isinstance(m[k], str):
                    raise ValueError(f"manifest field {k} has the wrong type")
            if not isinstance(m["baseline"], dict):
                raise ValueError("manifest baseline has the wrong type")
        except (OSError, ValueError, KeyError) as e:
            return None, [f"manifest unreadable: {e}"]
        problems: List[str] = []
        if m.get("schema") != MANIFEST_SCHEMA:
            problems.append(f"unsupported manifest schema {m.get('schema')!r}")
        if row is None:
            problems.append("no index row for this attempt")
        else:
            if row["manifest_sha256"] != sha256_file(mp):
                problems.append("manifest changed since it was indexed")
            if row["state"] != m["state"]:
                problems.append(f"index state {row['state']!r} != manifest state {m['state']!r}")
        if m["state"] != AttemptState.RUNNING.value:
            arts = m.get("artifacts") or {}
            if not isinstance(arts, dict):
                problems.append("manifest artifacts has the wrong type")
                arts = {}
            for name, art in arts.items():
                try:
                    p = d / art["path"]
                    if not p.exists():
                        problems.append(f"artifact {name} missing")
                    elif sha256_file(p) != art["sha256"]:
                        problems.append(f"artifact {name} was modified")
                except (KeyError, TypeError):
                    problems.append(f"artifact {name} record malformed")
        return m, problems

    def load_attempts(self) -> Tuple[List[AttemptRecord], List[str]]:
        """所有尝试 (目录与索引的并集) 及无法归属到任何 (故事, 条目) 的全局问题。"""
        with self._conn() as c:
            rows = {r["attempt_id"]: r for r in c.execute("SELECT * FROM flowtree_attempts")}
        records: List[AttemptRecord] = []
        global_problems: List[str] = []
        seen_ids = set()

        def add(d: Path, run_id: str, story_from_path: Optional[str], entry: str) -> None:
            attempt_id = f"{run_id}.{story_from_path}.{entry}" if story_from_path else f"{run_id}.{entry}"
            row = rows.get(attempt_id)
            m, problems = self._inspect(d, row)
            story = story_from_path or (m or {}).get("story_id") or (row["story_id"] if row else None)
            if m is not None:
                if m["attempt_id"] != attempt_id:
                    problems.append(f"manifest attempt_id {m['attempt_id']!r} does not match its location")
                if story_from_path and m["story_id"] != story_from_path:
                    problems.append("manifest story_id does not match its location")
            started = (m or {}).get("started_at") or (row["started_at"] if row else None) or _ts_from_run_id(run_id)
            seen_ids.add(attempt_id)
            records.append(AttemptRecord(d, m, problems, story, entry, attempt_id, started))

        for run in sorted(x for x in self.runs_dir.iterdir() if x.is_dir()):
            for child in sorted(x for x in run.iterdir() if x.is_dir()):
                subdirs = [x for x in child.iterdir() if x.is_dir()]
                files = [x for x in child.iterdir() if x.is_file()]
                if subdirs and not files:           # 新布局: child 是故事目录
                    for att in sorted(subdirs):
                        add(att, run.name, child.name, att.name)
                else:                                # 旧布局或空目录: child 本身是尝试目录
                    add(child, run.name, None, child.name)
        for aid, r in rows.items():
            if aid not in seen_ids:
                records.append(AttemptRecord(None, None, ["indexed attempt has no directory on disk"],
                                             r["story_id"], r["entry_id"], aid, r["started_at"]))
        for r in records:
            if r.story_id is None:
                global_problems.append(f"{r.attempt_id}: attempt cannot be attributed to a story ({'; '.join(r.problems)})")
        return records, global_problems

    def latest_evidence(self, story_id: str, entry_id: str) -> Tuple[Optional[EntryEvidence], List[str]]:
        records, global_problems = self.load_attempts()
        mine = [r for r in records if r.story_id == story_id and r.entry_id == entry_id]
        if not mine:
            return None, global_problems
        # 时间未知的记录当作最新: 无法确认它更旧, 就不能越过它去取更早的通过
        r = max(mine, key=lambda x: (x.started_at is None, x.started_at or ""))
        problems = [f"{x.attempt_id}: {p}" for x in mine for p in x.problems]
        m = r.manifest
        placeholder = Baseline("", "", "", None)
        if m is None or r.problems:
            return EntryEvidence(entry_id, AttemptState.ERROR, placeholder, {}, (m or {}).get("run_id"), corrupt=True), \
                global_problems + problems
        try:
            state = AttemptState(m["state"])
            if state == AttemptState.RUNNING:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(m["started_at"])).total_seconds()
                if age > m.get("timeout_s", 600) + RUNNING_GRACE_S:
                    state = AttemptState.ABORTED
            tests = {} if state != AttemptState.COMPLETED else {
                nid: TestOutcome(d["outcome"]) for nid, d in (m.get("outcomes") or {}).items()}
            ev = EntryEvidence(entry_id, state, baseline_from_dict(m["baseline"]), tests, m["run_id"],
                               exit_code=m.get("exit_code"), command_nonpass=dict(m.get("unmapped_nonpass") or {}),
                               env_vars=dict(m.get("env_vars") or {}))
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            return EntryEvidence(entry_id, AttemptState.ERROR, placeholder, {}, m.get("run_id"), corrupt=True), \
                global_problems + problems + [f"{r.attempt_id}: manifest content invalid: {e}"]
        return ev, global_problems + problems
