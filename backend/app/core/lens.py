from typing import List, Dict, Set
from collections import defaultdict, deque
from .schema import (
    ProjectModel, PerspectiveModel, NodeModel, NodeStatus, BulbState,
    CanvasPayload, CanvasNode, CanvasEdge, CanvasStats, CanvasNodeOverlay
)
from .circuit import CircuitEngine

class PerspectiveLens:
    """动态视角透镜投影器"""

    @classmethod
    def is_node_matched(cls, node: NodeModel, perspective: PerspectiveModel) -> bool:
        """
        判断节点是否命中视角透镜规则
        - 如果视角为空，展示全量
        - 如果指定了 includeTags，节点必须包含其中至少一个 tag
        - 如果指定了 includeNodeTypes，节点类型必须在其中
        """
        # 全量综合视图
        if not perspective.includeTags and not perspective.includeNodeTypes:
            return True

        # 1. 检查标签条件
        if perspective.includeTags:
            has_tag = any(tag in perspective.includeTags for tag in node.tags)
            if not has_tag:
                return False

        # 2. 检查节点类型条件
        if perspective.includeNodeTypes:
            if node.nodeType not in perspective.includeNodeTypes:
                return False

        return True

    @classmethod
    def project(cls, project: ProjectModel, view_id: str) -> CanvasPayload:
        """
        根据指定的 view_id 动态裁剪与投影任务拓扑网络
        """
        # 1. 查找视角配置，若无则使用全局视角
        perspective = next((p for p in project.perspectives if p.viewId == view_id), None)
        if not perspective:
            perspective = PerspectiveModel(
                viewId="view-all",
                name="全景综合视图",
                description="项目全量任务与电路拓扑全貌",
                bypassUnmatched=False
            )

        # 2. 校验有向无环图
        CircuitEngine.validate_dag(project.nodes)

        node_map: Dict[str, NodeModel] = {n.nodeId: n for n in project.nodes}
        matched_node_ids: Set[str] = {
            n.nodeId for n in project.nodes if cls.is_node_matched(n, perspective)
        }

        # 3. 构建邻接表
        # downstream_map[source] -> [targets]
        downstream_map: Dict[str, List[str]] = defaultdict(list)
        for n in project.nodes:
            for dep_id in n.deps:
                if dep_id in node_map:
                    downstream_map[dep_id].append(n.nodeId)

        # 4. 电源连通性预计算（严格因果律：前面不通，后面也不能通）
        powered_map = CircuitEngine.compute_power_reachability(project.nodes)
        all_module_summaries = CircuitEngine.compute_module_summaries(project.nodes)
        module_summary_map = {m.moduleId: m for m in all_module_summaries}

        # 5. 穿透算法：计算视角下的连线 (Edges)
        edges: List[CanvasEdge] = []
        edge_set: Set[tuple] = set()

        for source_id in matched_node_ids:
            source_node = node_map[source_id]
            source_powered = powered_map.get(source_id, False)

            if not perspective.bypassUnmatched:
                # 不穿透：只保留两端都在视角内的直接依赖
                for target_id in downstream_map[source_id]:
                    if target_id in matched_node_ids:
                        target_node = node_map[target_id]
                        c_state, flow, color = CircuitEngine.compute_edge_circuit(source_node, target_node, source_powered)
                        edge_pair = (source_id, target_id)
                        if edge_pair not in edge_set:
                            edge_set.add(edge_pair)
                            edges.append(CanvasEdge(
                                id=f"e_{source_id}_{target_id}",
                                source=source_id,
                                target=target_id,
                                circuitState=c_state,
                                flowAnimation=flow,
                                strokeColor=color,
                                isBypass=False
                            ))
            else:
                # 穿透模式 (Bypass Transitive Search)
                visited_in_search: Set[str] = set()
                queue = deque([(target_id, False) for target_id in downstream_map[source_id]])

                while queue:
                    curr_id, bypassed = queue.popleft()
                    if curr_id in visited_in_search:
                        continue
                    visited_in_search.add(curr_id)

                    if curr_id in matched_node_ids:
                        edge_pair = (source_id, curr_id)
                        if edge_pair not in edge_set:
                            edge_set.add(edge_pair)
                            target_node = node_map[curr_id]
                            c_state, flow, color = CircuitEngine.compute_edge_circuit(source_node, target_node, source_powered)
                            edges.append(CanvasEdge(
                                id=f"e_{source_id}_{curr_id}",
                                source=source_id,
                                target=curr_id,
                                circuitState=c_state,
                                flowAnimation=flow,
                                strokeColor=color,
                                isBypass=bypassed
                            ))
                    else:
                        for next_id in downstream_map[curr_id]:
                            if next_id not in visited_in_search:
                                queue.append((next_id, True))

        # 6. 生成渲染节点卡片 (CanvasNodes)
        canvas_nodes: List[CanvasNode] = []
        total_estimate_hours = 0.0
        passed_estimate_hours = 0.0

        for nid in matched_node_ids:
            node = node_map[nid]
            is_node_powered = powered_map.get(nid, False)

            # 模块根节点随百分比变色逻辑
            if node.nodeType.value == "module":
                m_info = module_summary_map.get(node.nodeId) or module_summary_map.get(node.parentId or "")
                rate = m_info.progressRate if m_info else 0.0
                has_reject = (m_info.bottlenecksCount > 0) if m_info else False
                bulb, color_hex = CircuitEngine.get_module_color_by_percentage(rate, has_reject)
                module_pct = rate
                module_color = color_hex
            elif node.nodeType.value == "root":
                bulb = BulbState.ILLUMINATED_GREEN
                module_pct = 1.0
                module_color = "#10B981"
            else:
                module_pct = None
                module_color = None
                # 常规任务节点：前面不通，后面失压断电
                if not is_node_powered:
                    if node.status == NodeStatus.REVIEW_PASS:
                        # 自身通过但前置失压
                        bulb = BulbState.OFF
                    else:
                        bulb = CircuitEngine.get_bulb_state(node)
                else:
                    bulb = CircuitEngine.get_bulb_state(node)

            total_estimate_hours += node.estimateHours
            if node.status == NodeStatus.REVIEW_PASS:
                passed_estimate_hours += node.estimateHours

            overlay = CanvasNodeOverlay(
                assignee=node.assignee,
                hours=f"{node.actualHours}/{node.estimateHours}h",
                hasExternalBinding=node.externalBinding is not None,
                isLogicVerified=node.review.logicVerified,
                isHumanApproved=node.review.humanSignOff,
                isPowered=is_node_powered,
                powerPathBroken=(not is_node_powered and len(node.deps) > 0),
                moduleProgressPct=module_pct,
                moduleColorHex=module_color
            )

            canvas_nodes.append(CanvasNode(
                id=node.nodeId,
                label=node.name,
                nodeType=node.nodeType,
                status=node.status,
                bulbState=bulb,
                dataOverlay=overlay,
                raw=node
            ))

        # 6. 计算统计指标与卡点归属、模块聚合、个人供应链分析
        matched_raw_nodes = [node_map[nid] for nid in matched_node_ids]
        bottlenecks = CircuitEngine.analyze_bottlenecks(matched_raw_nodes)
        module_summaries = CircuitEngine.compute_module_summaries(matched_raw_nodes)
        personal_chains = CircuitEngine.compute_personal_supply_chains(project.nodes)

        stats = CanvasStats(
            totalNodes=len(canvas_nodes),
            energizedNodes=sum(1 for n in canvas_nodes if n.status == NodeStatus.REVIEW_PASS),
            blockedNodes=sum(1 for n in canvas_nodes if n.status == NodeStatus.REVIEW_REJECT),
            logicVerifiedNodes=sum(1 for n in canvas_nodes if n.status == NodeStatus.LOGIC_VERIFIED),
            progressRate=round(passed_estimate_hours / total_estimate_hours, 2) if total_estimate_hours > 0 else 0.0,
            bottlenecks=bottlenecks,
            modules=module_summaries
        )

        return CanvasPayload(
            projectId=project.projectId,
            projectName=project.projectName,
            activeViewId=perspective.viewId,
            activeViewName=perspective.name,
            stats=stats,
            nodes=canvas_nodes,
            edges=edges,
            personalSupplyChains=personal_chains
        )
