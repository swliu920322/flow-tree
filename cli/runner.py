import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

class CircuitRunner:
    """负责执行 .flowtree/tests/ 自动化验收套件，并回填电路节点状态"""

    def __init__(self, target_dir: Path):
        self.target_dir = Path(target_dir).resolve()
        self.flowtree_dir = self.target_dir / ".flowtree"
        self.circuit_file = self.flowtree_dir / "circuit.json"
        self.test_file = self.flowtree_dir / "tests" / "test_circuit_verification.py"

    def run(self) -> Dict[str, Any]:
        if not self.circuit_file.exists():
            raise FileNotFoundError(f"未找到电路配置文件: {self.circuit_file}，请先运行 flowtree init")

        with open(self.circuit_file, "r", encoding="utf-8") as f:
            circuit_data = json.load(f)

        results = {}
        if self.test_file.exists():
            # 动态载入并运行测试脚本中的 verify_all_nodes()
            spec = importlib.util.spec_from_file_location("circuit_test", str(self.test_file))
            test_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(test_mod)
            if hasattr(test_mod, "verify_all_nodes"):
                results = test_mod.verify_all_nodes()

        nodes = circuit_data.get("nodes", [])
        updated_count = 0
        passed_nodes = []
        blocked_nodes = []

        for node in nodes:
            nid = node["nodeId"]
            if nid == "ROOT-PROJECT":
                continue

            if nid in results:
                test_res = results[nid]
                if test_res.get("passed"):
                    if node.get("status") != "review_pass":
                        node["status"] = "logic_verified"
                    if "review" not in node:
                        node["review"] = {}
                    node["review"]["logicVerified"] = True
                    node["review"]["logicVerifiedBy"] = "cli_agent"
                    passed_nodes.append(nid)
                else:
                    node["status"] = "blocked"
                    if "review" not in node:
                        node["review"] = {}
                    node["review"]["logicVerified"] = False
                    if "comments" not in node["review"]:
                        node["review"]["comments"] = []
                    node["review"]["comments"].append(f"CLI断言失败: {test_res.get('error')}")
                    blocked_nodes.append(nid)
                updated_count += 1

        # 写回本地 circuit.json
        with open(self.circuit_file, "w", encoding="utf-8") as f:
            json.dump(circuit_data, f, ensure_ascii=False, indent=2)

        return {
            "projectId": circuit_data.get("projectId"),
            "projectName": circuit_data.get("projectName"),
            "circuitData": circuit_data,
            "totalTested": len(results),
            "passedNodes": passed_nodes,
            "blockedNodes": blocked_nodes
        }
