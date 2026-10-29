from typing import Dict, List, Set, Tuple
from .schema import NodeModel, NodeStatus, BulbState, CircuitState

class CircuitError(Exception):
    pass

class CircuitEngine:
    """电路导通与电气状态推导引擎"""

    @staticmethod
    def get_bulb_state(node: NodeModel) -> BulbState:
        """根据节点当前状态计算灯泡发光特征"""
        if node.status == NodeStatus.REVIEW_PASS:
            return BulbState.ILLUMINATED_GREEN
        elif node.status == NodeStatus.LOGIC_VERIFIED:
            return BulbState.GLOWING_BLUE
        elif node.status == NodeStatus.DEVING:
            return BulbState.BREATHING_YELLOW
        elif node.status == NodeStatus.REVIEW_REJECT:
            return BulbState.ALERT_RED
        else:
            return BulbState.OFF

    @staticmethod
    def validate_dag(nodes: List[NodeModel]) -> None:
        """拓扑环路检测 (Cycle Detection)"""
        node_map = {n.nodeId: n for n in nodes}
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(node_id: str):
            visited.add(node_id)
            rec_stack.add(node_id)
            node = node_map.get(node_id)
            if node:
                for dep_id in node.deps:
                    if dep_id not in visited:
                        if dfs(dep_id):
                            return True
                    elif dep_id in rec_stack:
                        raise CircuitError(f"检测到循环依赖 (Cycle detected): {dep_id} <-> {node_id}")
            rec_stack.remove(node_id)
            return False

        for n in nodes:
            if n.nodeId not in visited:
                dfs(n.nodeId)

    @staticmethod
    def compute_edge_circuit(source: NodeModel, target: NodeModel) -> Tuple[CircuitState, bool, str]:
        """
        计算源节点到目标节点的连线电气状态
        返回: (CircuitState, flowAnimation, strokeColor)
        """
        # 1. 故障阻断 / 短路
        if source.status == NodeStatus.REVIEW_REJECT:
            return CircuitState.BLOCKED, False, "#EF4444"  # 警示红

        # 2. 完全导通放电: 前置已验收通过，电流注入下游
        if source.status == NodeStatus.REVIEW_PASS:
            if target.status != NodeStatus.PENDING_DEV:
                # 下游已被激活，粒子流动
                return CircuitState.ENERGIZED, True, "#10B981"  # 翡翠绿发光
            else:
                # 下游待开工，但线路已充满能量准备导通
                return CircuitState.ENERGIZED, False, "#34D399"

        # 3. 逻辑验证完成，等待下游
        if source.status == NodeStatus.LOGIC_VERIFIED:
            return CircuitState.DORMANT, False, "#38BDF8"  # 科技亮蓝

        # 4. 前置尚未完成，电路冷态休眠
        return CircuitState.DORMANT, False, "#64748B"  # 冷灰
