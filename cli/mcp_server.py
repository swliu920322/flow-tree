"""
FlowTree MCP (Model Context Protocol) Server
提供给任何 Agent (Claude, Cursor, Antigravity) 原生调用的结构化工具集
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

# 将 virtual-manage 根目录加入 sys.path
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cli.scanner import ProjectScanner
from cli.generator import CircuitGenerator
from cli.runner import CircuitRunner, VerificationNotConfigured
from cli.syncer import CircuitSyncer
from cli.storage import StorageManager
from flowtree import service

class FlowTreeMCPTools:
    """Agent 原生工具集实现"""

    @staticmethod
    def tool_init(project_dir: str, server_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        """【MCP Tool】扫描业务项目并生成旧电路视图骨架 (固定模板, 全部未验证)。不执行任何验收。"""
        target = Path(project_dir).resolve()
        scan_res = ProjectScanner(target).scan()
        circuit_file = CircuitGenerator(target).generate_all(scan_res["projectName"])
        circuit = CircuitRunner(target).load_circuit()
        sync_res = CircuitSyncer(server_url).sync(circuit)
        return {
            "success": True,
            "verified": False,
            "projectName": scan_res["projectName"],
            "circuitFile": str(circuit_file),
            "synced": sync_res.get("synced", False),
            "database": str(target / ".flowtree" / "data.db"),
            "note": "骨架为固定模板, 非验收依据; 请提供故事与测试映射后用 story_validate / story_plan 检查",
        }

    @staticmethod
    def tool_verify(project_dir: str, server_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        """【MCP Tool】旧验收入口: 没有可信验收依据时如实返回未执行。真实执行随 B1b 提供。"""
        try:
            CircuitRunner(Path(project_dir).resolve()).run()
        except (FileNotFoundError, VerificationNotConfigured) as e:
            return {"executed": False, "error": str(e)}
        return {"executed": False, "error": "旧入口不产生验收证据"}

    @staticmethod
    def tool_status(project_dir: str) -> Dict[str, Any]:
        """【MCP Tool】旧电路视图的状态分布 (非验收证据, 不含通过率)"""
        target = Path(project_dir).resolve()
        circuit_file = target / ".flowtree" / "circuit.json"
        if not circuit_file.exists():
            return {"error": f"项目 {project_dir} 尚未初始化 FlowTree"}

        with open(circuit_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        counts: Dict[str, int] = {}
        for n in data.get("nodes", []):
            counts[n.get("status", "unknown")] = counts.get(n.get("status", "unknown"), 0) + 1
        return {
            "projectId": data.get("projectId"),
            "projectName": data.get("projectName"),
            "origin": data.get("origin"),
            "legacyStatusCounts": counts,
            "isVerificationEvidence": False,
        }

    @staticmethod
    def tool_story_validate(stories: List[str], mappings: List[str] = None) -> Dict[str, Any]:
        """【MCP Tool】校验故事(及映射)的格式、引用与摘要"""
        return service.validate([Path(p) for p in stories], [Path(p) for p in mappings] if mappings else None)

    @staticmethod
    def tool_story_plan(stories: List[str], mappings: List[str] = None) -> Dict[str, Any]:
        """【MCP Tool】生成验收计划 (分母、映射、未映射与待确认项), 不执行测试"""
        return service.plan([Path(p) for p in stories], [Path(p) for p in mappings] if mappings else None)

    @staticmethod
    def tool_history(project_dir: str, limit: int = 5) -> List[Dict[str, Any]]:
        """【MCP Tool】查询本地 SQLite 数据库中留存的历史执行批次与度量指标"""
        target = Path(project_dir).resolve()
        storage = StorageManager(target)
        return storage.get_history(limit)

def main():
    """轻量标准 JSON-RPC 处理入口 (用于与 Agent 通信)"""
    import sys
    print("FlowTree MCP Server is ready. Listening on stdio...", file=sys.stderr)
    # 支持命令行测试或标准 Agent 协议握手
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        target = sys.argv[2] if len(sys.argv) > 2 else "."
        print("Testing MCP Verify Tool:", FlowTreeMCPTools.tool_verify(target))
    # 注意: 尚未实现 MCP 协议握手与请求分发, 这里只有工具函数。

if __name__ == "__main__":
    main()
