from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict
from .schema import (
    NodeModel, NodeStatus, BulbState, CircuitState,
    BottleneckImpact, ModuleSummary, PersonalSupplyChain
)

class CircuitError(Exception):
    pass

class CircuitEngine:
    """电路导通、电气状态推导与组织责任链分析引擎"""

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
    def compute_power_reachability(nodes: List[NodeModel]) -> Dict[str, bool]:
        """
        物理电源连通性检测（严格因果律：前面不通，后面也不能通）：
        从电源根节点 (ROOT 或无依赖的已放电节点) 出发，
        仅当前置所有依赖节点均通过终审 (REVIEW_PASS) 且已获电时，下游节点才能通电。
        """
        node_map = {n.nodeId: n for n in nodes}
        powered: Dict[str, bool] = {}

        in_degree = {n.nodeId: 0 for n in nodes}
        downstream = defaultdict(list)
        for n in nodes:
            for d in n.deps:
                if d in node_map:
                    in_degree[n.nodeId] += 1
                    downstream[d].append(n.nodeId)

        from collections import deque
        queue = deque([n.nodeId for n in nodes if in_degree[n.nodeId] == 0])

        for nid in queue:
            node = node_map[nid]
            if node.nodeType.value == "root":
                powered[nid] = (node.status == NodeStatus.REVIEW_PASS)
            else:
                powered[nid] = (node.status == NodeStatus.REVIEW_PASS)

        while queue:
            curr_id = queue.popleft()
            curr_powered = powered.get(curr_id, False)

            for next_id in downstream[curr_id]:
                in_degree[next_id] -= 1
                if in_degree[next_id] == 0:
                    next_node = node_map[next_id]
                    # 必须所有前置依赖都已放电 (REVIEW_PASS) 且通电
                    all_deps_passed = True
                    for dep_id in next_node.deps:
                        if dep_id in node_map:
                            dep_node = node_map[dep_id]
                            if dep_node.status != NodeStatus.REVIEW_PASS or not powered.get(dep_id, False):
                                all_deps_passed = False
                                break
                    powered[next_id] = all_deps_passed
                    queue.append(next_id)

        for n in nodes:
            if n.nodeId not in powered:
                powered[n.nodeId] = False

        return powered

    @staticmethod
    def get_module_color_by_percentage(pct: float, has_reject: bool = False) -> Tuple[BulbState, str]:
        """
        根据模块完成百分比计算模块根节点的颜色与发光特征：
        0%: 冷灰休眠 | 1~29%: 活力橙 | 30~69%: 施工金黄 | 70~89%: 冲刺天蓝 | 90~99%: 准通翠绿 | 100%: 翡翠霓虹绿
        """
        if has_reject:
            return BulbState.ALERT_RED, "#EF4444"        # 故障短路红
        if pct <= 0.0:
            return BulbState.OFF, "#64748B"              # 待开工冷灰
        elif pct < 0.30:
            return BulbState.BREATHING_YELLOW, "#F97316" # 初步通电活力橙
        elif pct < 0.70:
            return BulbState.BREATHING_YELLOW, "#EAB308" # 施工放电金黄
        elif pct < 0.90:
            return BulbState.GLOWING_BLUE, "#0EA5E9"     # 冲刺阶段天蓝
        elif pct < 1.0:
            return BulbState.ILLUMINATED_GREEN, "#10B981"# 准通阶段翠绿
        else:
            return BulbState.ILLUMINATED_GREEN, "#059669"# 100% 满电翡翠绿

    @staticmethod
    def compute_edge_circuit(source: NodeModel, target: NodeModel, source_powered: bool = True) -> Tuple[CircuitState, bool, str]:
        """
        计算源节点到目标节点的连线电气状态（前面不通，导线绝不放电）
        返回: (CircuitState, flowAnimation, strokeColor)
        """
        if not source_powered:
            # 源端失压断电，导线熄灭
            return CircuitState.DORMANT, False, "#334155"

        if source.status == NodeStatus.REVIEW_REJECT:
            return CircuitState.BLOCKED, False, "#EF4444"  # 警示红

        if source.status == NodeStatus.REVIEW_PASS:
            # 源端已导通，强劲电流涌向下游
            return CircuitState.ENERGIZED, True, "#10B981"  # 翡翠绿发光流动粒子

        if source.status == NodeStatus.LOGIC_VERIFIED:
            return CircuitState.DORMANT, False, "#38BDF8"  # 科技亮蓝等待放电

        return CircuitState.DORMANT, False, "#475569"  # 冷灰未通电

    @staticmethod
    def analyze_bottlenecks(nodes: List[NodeModel]) -> List[BottleneckImpact]:
        """
        卡点归属与阻断分析：
        精确识别“到底卡在谁手里、卡住了下游哪些人、影响程度如何”
        """
        node_map = {n.nodeId: n for n in nodes}
        downstream_map = defaultdict(list)
        for n in nodes:
            for dep_id in n.deps:
                if dep_id in node_map:
                    downstream_map[dep_id].append(n)

        bottlenecks: List[BottleneckImpact] = []

        for n in nodes:
            # 只有尚未终审通过的节点可能构成阻断
            if n.status != NodeStatus.REVIEW_PASS:
                downstream = downstream_map.get(n.nodeId, [])
                if downstream:
                    blocked_assignees = list(set(
                        d.assignee for d in downstream if d.assignee and d.assignee != n.assignee
                    ))
                    blocked_node_ids = [d.nodeId for d in downstream]

                    is_critical = (
                        n.status == NodeStatus.REVIEW_REJECT or
                        len(downstream) >= 2 or
                        any(d.status == NodeStatus.DEVING for d in downstream)
                    )

                    reason = (
                        f"节点状态为【{n.status.value}】，导致下游 {len(downstream)} 个后续节点无法放电推进"
                    )

                    bottlenecks.append(BottleneckImpact(
                        blockerNodeId=n.nodeId,
                        blockerNodeLabel=n.name,
                        blockerAssignee=n.assignee or "未指定",
                        blockerRole=n.assignRole or "待定",
                        status=n.status,
                        blockedDownstreamCount=len(downstream),
                        blockedAssignees=blocked_assignees,
                        blockedNodeIds=blocked_node_ids,
                        severity="high" if is_critical else "medium",
                        reason=reason
                    ))

        # 按照严重程度与阻断下游数量倒序排序
        bottlenecks.sort(key=lambda b: (0 if b.severity == "high" else 1, -b.blockedDownstreamCount))
        return bottlenecks

    @staticmethod
    def compute_module_summaries(nodes: List[NodeModel]) -> List[ModuleSummary]:
        """
        计算模块/业务舱层级聚合数据：
        支持树形下钻、多负责人盘点与模块级健康度
        """
        module_groups = defaultdict(list)
        for n in nodes:
            m_id = n.parentId or "MAIN"
            module_groups[m_id].append(n)

        summaries: List[ModuleSummary] = []
        for m_id, m_nodes in module_groups.items():
            assignees = list(set(n.assignee for n in m_nodes if n.assignee))
            assign_roles = list(set(n.assignRole for n in m_nodes if n.assignRole))
            total = len(m_nodes)
            energized = sum(1 for n in m_nodes if n.status == NodeStatus.REVIEW_PASS)
            bottlenecks_count = sum(1 for n in m_nodes if n.status in (NodeStatus.REVIEW_REJECT, NodeStatus.PENDING_DEV))
            rate = round(energized / total, 2) if total > 0 else 0.0

            summaries.append(ModuleSummary(
                moduleId=m_id,
                moduleName=f"模块：{m_id}",
                assignees=assignees,
                assignRoles=assign_roles,
                totalNodes=total,
                energizedNodes=energized,
                progressRate=rate,
                isHealthy=(bottlenecks_count == 0),
                bottlenecksCount=bottlenecks_count
            ))

        return summaries

    @staticmethod
    def compute_personal_supply_chains(nodes: List[NodeModel]) -> Dict[str, PersonalSupplyChain]:
        """
        计算每个参与者的全局工位上下游关系：
        清晰回答“我的业务在全局的哪一环？谁卡我？我又在卡谁？”
        """
        node_map = {n.nodeId: n for n in nodes}
        downstream_map = defaultdict(list)
        for n in nodes:
            for dep_id in n.deps:
                if dep_id in node_map:
                    downstream_map[dep_id].append(n)

        # 提取所有参与者（支持逗号或斜杠分割）
        raw_assignees = set()
        for n in nodes:
            if n.assignee:
                for part in n.assignee.replace("+", ",").replace("/", ",").split(","):
                    name = part.strip()
                    if name:
                        raw_assignees.add(name)

        result: Dict[str, PersonalSupplyChain] = {}

        for person in raw_assignees:
            my_nodes = [n for n in nodes if n.assignee and person in n.assignee]
            my_node_ids = [n.nodeId for n in my_nodes]

            # 1. 上游输入：依赖的前置节点中由他人负责的
            upstream_feeders = []
            seen_up = set()
            for n in my_nodes:
                for dep_id in n.deps:
                    dep_node = node_map.get(dep_id)
                    if dep_node and (not dep_node.assignee or person not in dep_node.assignee):
                        key = (dep_node.nodeId, n.nodeId)
                        if key not in seen_up:
                            seen_up.add(key)
                            upstream_feeders.append({
                                "nodeId": dep_node.nodeId,
                                "label": dep_node.name,
                                "assignee": dep_node.assignee or "未指定",
                                "status": dep_node.status.value,
                                "isReady": (dep_node.status == NodeStatus.REVIEW_PASS),
                                "forMyNode": n.nodeId
                            })

            # 2. 下游交付：等待我放电的后续节点中由他人负责的
            downstream_waiters = []
            seen_down = set()
            for n in my_nodes:
                for down_node in downstream_map.get(n.nodeId, []):
                    if not down_node.assignee or person not in down_node.assignee:
                        key = (n.nodeId, down_node.nodeId)
                        if key not in seen_down:
                            seen_down.add(key)
                            downstream_waiters.append({
                                "nodeId": down_node.nodeId,
                                "label": down_node.name,
                                "assignee": down_node.assignee or "未指定",
                                "status": down_node.status.value,
                                "isBlocked": (n.status != NodeStatus.REVIEW_PASS),
                                "fromMyNode": n.nodeId
                            })

            result[person] = PersonalSupplyChain(
                assignee=person,
                upstreamFeeders=upstream_feeders,
                myNodes=my_node_ids,
                downstreamWaiters=downstream_waiters
            )

        return result
