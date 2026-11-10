import json
from pathlib import Path
from typing import Any, Dict


class VerificationNotConfigured(RuntimeError):
    """旧入口没有可信的验收依据。"""


class CircuitRunner:
    """旧电路入口的兼容外壳。

    原实现动态导入 .flowtree/tests 下的脚本并信任其返回的布尔值, 这些脚本含固定 passed = True, 不构成证据。
    现在不再导入/执行任何脚本, 不改写 circuit.json 节点状态, 也不写运行记录。
    真实执行请使用故事与显式测试映射 (flowtree story ...; flowtree verify)。
    """

    def __init__(self, target_dir: Path):
        self.target_dir = Path(target_dir).resolve()
        self.flowtree_dir = self.target_dir / ".flowtree"
        self.circuit_file = self.flowtree_dir / "circuit.json"

    def load_circuit(self) -> Dict[str, Any]:
        if not self.circuit_file.exists():
            raise FileNotFoundError(f"未找到电路配置文件: {self.circuit_file}，请先运行 flowtree init")
        with open(self.circuit_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def run(self) -> Dict[str, Any]:
        self.load_circuit()  # 未初始化时保持原有的 FileNotFoundError 语义
        raise VerificationNotConfigured(
            "没有可执行的验收依据: 旧自动生成脚本不构成证据, 已停用。"
            "请提供故事与测试映射, 先用 `flowtree story validate/plan` 检查, 再用 `flowtree verify` 真实执行。"
        )
