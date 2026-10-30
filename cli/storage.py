import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

class StorageManager:
    """
    负责本地/远程数据的自动建表、持久化存储与历史追溯
    默认采用 Local-First 模式，零配置启动 SQLite
    """

    def __init__(self, target_dir: Path, db_name: str = "data.db"):
        self.target_dir = Path(target_dir).resolve()
        self.flowtree_dir = self.target_dir / ".flowtree"
        self.flowtree_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.flowtree_dir / db_name
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """自动建表：如果表不存在则无感初始化"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. 运行批次主表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS flowtree_runs (
                run_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                project_name TEXT,
                git_commit TEXT,
                git_branch TEXT,
                total_nodes INTEGER,
                passed_nodes INTEGER,
                blocked_nodes INTEGER,
                duration_ms REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # 2. 节点度量与错误明细表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS flowtree_node_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms REAL,
                error_trace TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES flowtree_runs(run_id)
            )
            """)
            conn.commit()

    def record_run(self, 
                   project_id: str, 
                   project_name: str, 
                   total_nodes: int, 
                   passed_nodes: List[str], 
                   blocked_nodes: List[str], 
                   node_details: Dict[str, Any],
                   duration_ms: float = 0.0) -> str:
        """记录一次巡检批次及其下各节点的执行明细"""
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        status = "ALL_PASS" if len(blocked_nodes) == 0 else "HAS_BLOCKED"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO flowtree_runs (
                run_id, project_id, project_name, total_nodes, 
                passed_nodes, blocked_nodes, duration_ms, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, project_id, project_name, total_nodes,
                len(passed_nodes), len(blocked_nodes), duration_ms, status
            ))

            for nid, detail in node_details.items():
                node_status = "logic_verified" if detail.get("passed") else "blocked"
                err = detail.get("error")
                dur = detail.get("duration_ms", 0.0)
                cursor.execute("""
                INSERT INTO flowtree_node_metrics (
                    run_id, node_id, status, duration_ms, error_trace
                ) VALUES (?, ?, ?, ?, ?)
                """, (run_id, nid, node_status, dur, err))

            conn.commit()
        return run_id

    def get_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取最近的历史执行批次"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT run_id, project_name, total_nodes, passed_nodes, blocked_nodes, status, created_at
            FROM flowtree_runs
            ORDER BY created_at DESC
            LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
