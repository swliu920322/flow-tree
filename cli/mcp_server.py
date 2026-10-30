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
from cli.runner import CircuitRunner
from cli.syncer import CircuitSyncer
from cli.storage import StorageManager

class FlowTreeMCPTools:
    """Agent 原生工具集实现"""

    @staticmethod
    def tool_init(project_dir: str, server_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        """【MCP Tool】扫描业务项目，自动生成 .flowtree/circuit.json 拓扑与测试脚手架"""
        target = Path(project_dir).resolve()
        scanner = ProjectScanner(target)
        scan_res = scanner.scan()

        generator = CircuitGenerator(target)
        circuit_file = generator.generate_all(scan_res["projectName"])

        runner = CircuitRunner(target)
        run_res = runner.run()

        syncer = CircuitSyncer(server_url)
        sync_res = syncer.sync(run_res["circuitData"])

        return {
            "success": True,
            "projectName": scan_res["projectName"],
            "circuitFile": str(circuit_file),
            "totalNodes": run_res["totalTested"],
            "synced": sync_res.get("synced", False),
            "database": str(target / ".flowtree" / "data.db")
        }

    @staticmethod
    def tool_verify(project_dir: str, server_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        """【MCP Tool】触发自动化巡检验收，更新本地电路与 SQLite 数据库，并同步大屏"""
        target = Path(project_dir).resolve()
        runner = CircuitRunner(target)
        run_res = runner.run()

        syncer = CircuitSyncer(server_url)
        sync_res = syncer.sync(run_res["circuitData"])

        return {
            "runId": run_res.get("runId"),
            "durationMs": run_res.get("durationMs"),
            "totalTested": run_res["totalTested"],
            "passedCount": len(run_res["passedNodes"]),
            "blockedCount": len(run_res["blockedNodes"]),
            "blockedNodes": run_res["blockedNodes"],
            "synced": sync_res.get("synced", False)
        }

    @staticmethod
    def tool_status(project_dir: str) -> Dict[str, Any]:
        """【MCP Tool】查询当前工程的健康度、模块通过率与物理卡点"""
        target = Path(project_dir).resolve()
        circuit_file = target / ".flowtree" / "circuit.json"
        if not circuit_file.exists():
            return {"error": f"项目 {project_dir} 尚未初始化 FlowTree"}

        with open(circuit_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        modules = {}
        for n in data.get("nodes", []):
            if n["nodeId"] == "ROOT-PROJECT":
                continue
            mid = n.get("parentId") or "MAIN"
            if mid not in modules:
                modules[mid] = {"total": 0, "verified": 0, "blocked": 0}
            modules[mid]["total"] += 1
            if n.get("status") in ("logic_verified", "review_pass"):
                modules[mid]["verified"] += 1
            elif n.get("status") == "blocked":
                modules[mid]["blocked"] += 1

        return {
            "projectId": data.get("projectId"),
            "projectName": data.get("projectName"),
            "modules": modules
        }

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

if __name__ == "__main__":
    main()
