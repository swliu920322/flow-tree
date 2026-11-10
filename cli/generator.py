import json
import os
from pathlib import Path
from typing import Dict, Any

class CircuitGenerator:
    """生成 .flowtree/circuit.json 旧电路视图骨架 (模板, 非验收依据; 全部节点为未验证状态)"""

    def __init__(self, target_dir: Path):
        self.target_dir = Path(target_dir).resolve()
        self.flowtree_dir = self.target_dir / ".flowtree"

    def generate_all(self, project_name: str = None) -> Path:
        self.flowtree_dir.mkdir(parents=True, exist_ok=True)

        if not project_name:
            project_name = self.target_dir.name

        project_id = f"proj-{project_name.lower().replace('_', '-')}"
        circuit_file = self.flowtree_dir / "circuit.json"

        # 拓扑骨架: 固定模板, 不是从项目文档/代码中抽取的事实, 仅供旧电路视图占位。
        # 不再生成任何验收脚本; 验收依据来自外部提供的故事与显式测试映射 (flowtree story ...)。
        if "piggy" in project_name.lower():
            circuit_data = self._build_piggy_circuit(project_id, project_name)
        else:
            circuit_data = self._build_generic_circuit(project_id, project_name)
        self._neutralize(circuit_data)

        with open(circuit_file, "w", encoding="utf-8") as f:
            json.dump(circuit_data, f, ensure_ascii=False, indent=2)

        return circuit_file

    @staticmethod
    def _neutralize(circuit_data: Dict[str, Any]) -> None:
        """模板里预填的通过/人工签字不是证据: 统一退回旧电路模型中最保守的合法状态 (pending_dev),
        清空自动验证与人工签字。'未执行'等新状态只存在于新领域模型 (flowtree.status), 不写入旧 NodeStatus。"""
        circuit_data["origin"] = "template_unverified"
        for node in circuit_data.get("nodes", []):
            node["status"] = "pending_dev"
            node["actualHours"] = 0.0
            node["review"] = {}

    def _build_generic_circuit(self, project_id: str, project_name: str) -> Dict[str, Any]:
        """为任意未知通用项目生成标准的 3 级渐进式物理电路拓扑"""
        return {
            "projectId": project_id,
            "projectName": project_name,
            "description": f"{project_name} 业务连通性与交付流水线",
            "version": "1.0.0",
            "stage": "staging_review",
            "perspectives": [
                {
                    "viewId": "view-all",
                    "name": "全局流线 (All)",
                    "description": "项目全量节点与物理通电总览",
                    "icon": "Eye",
                    "includeTags": ["init", "core", "delivery", "root"],
                    "bypassUnmatched": True
                },
                {
                    "viewId": "view-core",
                    "name": "核心业务 (Core)",
                    "description": "核心业务逻辑流线",
                    "icon": "Activity",
                    "includeTags": ["core", "delivery"],
                    "bypassUnmatched": True
                }
            ],
            "nodes": [
                {
                    "nodeId": "ROOT-PROJECT",
                    "name": f"{project_name} 启动总线",
                    "nodeType": "root",
                    "tags": ["root"],
                    "assignRole": "架构组",
                    "assignee": "Lead",
                    "description": "项目基线与初始总线",
                    "status": "review_pass",
                    "deps": [],
                    "estimateHours": 0.0,
                    "actualHours": 0.0,
                    "review": {"humanSignOff": True, "logicVerified": True},
                    "acceptanceCriteria": ["工程脚手架就绪"]
                },
                {
                    "nodeId": "N1-01",
                    "parentId": "MOD-INIT",
                    "name": "配置解析与依赖就绪",
                    "nodeType": "feature",
                    "tags": ["init"],
                    "assignRole": "基础设施",
                    "assignee": "DevOps",
                    "description": "环境变量载入与依赖版本自检",
                    "status": "logic_verified",
                    "deps": ["ROOT-PROJECT"],
                    "estimateHours": 1.0,
                    "actualHours": 0.8,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": ["环境变量正确解析", "外部依赖加载成功"]
                },
                {
                    "nodeId": "N1-02",
                    "parentId": "MOD-INIT",
                    "name": "持久化存储与连接池连通",
                    "nodeType": "api",
                    "tags": ["init"],
                    "assignRole": "后端开发",
                    "assignee": "Backend",
                    "description": "数据库/缓存连通性检测",
                    "status": "logic_verified",
                    "deps": ["N1-01"],
                    "estimateHours": 2.0,
                    "actualHours": 1.5,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": ["数据表结构初始化完成", "连接健康检测通过"]
                },
                {
                    "nodeId": "N2-01",
                    "parentId": "MOD-CORE",
                    "name": "业务主干请求与契约路由",
                    "nodeType": "api",
                    "tags": ["core"],
                    "assignRole": "后端开发",
                    "assignee": "Backend",
                    "description": "核心 API 接收业务输入与格式校验",
                    "status": "logic_verified",
                    "deps": ["N1-02"],
                    "estimateHours": 3.0,
                    "actualHours": 2.5,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": ["输入参数合法性校验", "业务路由正确分发"]
                },
                {
                    "nodeId": "N2-02",
                    "parentId": "MOD-CORE",
                    "name": "核心状态流转与数据变更",
                    "nodeType": "feature",
                    "tags": ["core"],
                    "assignRole": "全栈开发",
                    "assignee": "Fullstack",
                    "description": "业务模型状态流转与事务落地",
                    "status": "logic_verified",
                    "deps": ["N2-01"],
                    "estimateHours": 4.0,
                    "actualHours": 3.5,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": ["业务状态正确跳转", "事务一致性断言通过"]
                },
                {
                    "nodeId": "N3-01",
                    "parentId": "MOD-DELIVERY",
                    "name": "自动化验收套件自验",
                    "nodeType": "feature",
                    "tags": ["delivery"],
                    "assignRole": "QA测试",
                    "assignee": "QA",
                    "description": "端到端自动化契约回归",
                    "status": "logic_verified",
                    "deps": ["N2-02"],
                    "estimateHours": 2.0,
                    "actualHours": 1.8,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": ["回归用例 100% 通过", "无严重阻断性缺陷"]
                },
                {
                    "nodeId": "N3-02",
                    "parentId": "MOD-DELIVERY",
                    "name": "人工终审与正式通电签字",
                    "nodeType": "feature",
                    "tags": ["delivery"],
                    "assignRole": "业务终审",
                    "assignee": "PO/Lead",
                    "description": "负责人体验走查与终审放行",
                    "status": "review_pass",
                    "deps": ["N3-01"],
                    "estimateHours": 1.0,
                    "actualHours": 0.5,
                    "review": {"humanSignOff": True, "humanSignOffBy": "PO", "logicVerified": True},
                    "acceptanceCriteria": ["产品体验走查通过", "负责人签署确认"]
                }
            ]
        }

    def _build_piggy_circuit(self, project_id: str, project_name: str) -> Dict[str, Any]:
        return {
            "projectId": project_id,
            "projectName": f"{project_name} (人生储蓄罐)",
            "description": "基于延迟满足与双轨积分的家庭行为经济学系统",
            "version": "1.0.0",
            "stage": "staging_review",
            "perspectives": [
                {
                    "viewId": "view-all",
                    "name": "全局无交叉流线 (All)",
                    "description": "所有业务模块无交叉瀑布流",
                    "icon": "Eye",
                    "includeTags": ["auth", "task", "shop", "savings", "root"],
                    "bypassUnmatched": True
                },
                {
                    "viewId": "view-product",
                    "name": "用户真实体验旅程 (Product)",
                    "description": "面向产品与业务的端到端旅程",
                    "icon": "Compass",
                    "includeTags": ["auth", "task", "shop"],
                    "bypassUnmatched": True
                },
                {
                    "viewId": "view-backend",
                    "name": "后端事务与API链条 (Backend)",
                    "description": "面向后端研发的契约状态机",
                    "icon": "Server",
                    "includeTags": ["auth", "task", "shop", "savings"],
                    "bypassUnmatched": True
                }
            ],
            "nodes": [
                {
                    "nodeId": "ROOT-PROJECT",
                    "name": "Life-Piggy-Bank 核心旅程启动",
                    "nodeType": "root",
                    "tags": ["root"],
                    "assignRole": "架构组",
                    "assignee": "架构师",
                    "description": "全链路起点总线，各业务流线自此无交叉并行展开",
                    "status": "review_pass",
                    "deps": [],
                    "estimateHours": 0.0,
                    "actualHours": 0.0,
                    "review": {
                        "humanSignOff": True,
                        "humanSignOffBy": "architect",
                        "logicVerified": True,
                        "logicVerifiedBy": "agent"
                    },
                    "acceptanceCriteria": ["基线环境就绪"]
                },
                # ---------- 链条 1: 账户与家庭关系 (auth) ----------
                {
                    "nodeId": "S1-01",
                    "parentId": "MOD-AUTH",
                    "name": "注册登录与凭证下发",
                    "nodeType": "api",
                    "tags": ["auth"],
                    "assignRole": "全栈开发",
                    "assignee": "李全栈",
                    "description": "爸爸与大宝分别注册并获得 JWT Token",
                    "status": "logic_verified",
                    "deps": ["ROOT-PROJECT"],
                    "estimateHours": 2.0,
                    "actualHours": 1.5,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": [
                        "POST /auth/register 成功落库且密码 bcrypt 截断",
                        "POST /auth/login 返回有效 HS256 JWT"
                    ]
                },
                {
                    "nodeId": "S1-02",
                    "parentId": "MOD-AUTH",
                    "name": "家庭协作绑定与激活",
                    "nodeType": "feature",
                    "tags": ["auth"],
                    "assignRole": "后端开发",
                    "assignee": "张后端",
                    "description": "爸爸发起邀请，大宝接受，关系转为 active",
                    "status": "logic_verified",
                    "deps": ["S1-01"],
                    "estimateHours": 2.5,
                    "actualHours": 2.0,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": [
                        "POST /relationships/invite 创建 pending 关系",
                        "POST /relationships/respond/{id} 激活专属账本"
                    ]
                },
                # ---------- 链条 2: 任务派发与审批 (task) ----------
                {
                    "nodeId": "S2-01",
                    "parentId": "MOD-TASK",
                    "name": "任务模板创建",
                    "nodeType": "feature",
                    "tags": ["task"],
                    "assignRole": "全栈开发",
                    "assignee": "李全栈",
                    "description": "爸爸创建期末冲刺任务模板",
                    "status": "logic_verified",
                    "deps": ["ROOT-PROJECT"],
                    "estimateHours": 3.0,
                    "actualHours": 2.5,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": ["POST /tasks/ 成功落库且周期配置有效"]
                },
                {
                    "nodeId": "S2-02",
                    "parentId": "MOD-TASK",
                    "name": "待办实例生成与打卡",
                    "nodeType": "feature",
                    "tags": ["task"],
                    "assignRole": "全栈开发",
                    "assignee": "李全栈",
                    "description": "大宝名下生成 pending 实例并提交做题凭证",
                    "status": "logic_verified",
                    "deps": ["S1-02", "S2-01"],
                    "estimateHours": 4.0,
                    "actualHours": 3.2,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": ["POST /tasks/instances/{id}/submit 状态变为 submitted"]
                },
                {
                    "nodeId": "S2-03",
                    "parentId": "MOD-TASK",
                    "name": "审批核准与积分原子入账",
                    "nodeType": "api",
                    "tags": ["task"],
                    "assignRole": "后端开发",
                    "assignee": "张后端",
                    "description": "爸爸审批通过，事务触发大宝 points_b +20 并记流水",
                    "status": "logic_verified",
                    "deps": ["S2-02"],
                    "estimateHours": 4.0,
                    "actualHours": 3.8,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": [
                        "POST /tasks/instances/{id}/approve 实例状态变为 approved",
                        "大宝 points_b 原子增加 20 分，非发行人操作返回 403"
                    ]
                },
                # ---------- 链条 3: 商城兑换与核销 (shop) ----------
                {
                    "nodeId": "S3-01",
                    "parentId": "MOD-SHOP",
                    "name": "商城定向货架上架",
                    "nodeType": "feature",
                    "tags": ["shop"],
                    "assignRole": "全栈开发",
                    "assignee": "李全栈",
                    "description": "爸爸上架玩游戏2小时奖励，限大宝可见",
                    "status": "logic_verified",
                    "deps": ["S2-03"],
                    "estimateHours": 2.5,
                    "actualHours": 2.0,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": ["POST /shop/items/ 创建成功且可见性符合规则"]
                },
                {
                    "nodeId": "S3-02",
                    "parentId": "MOD-SHOP",
                    "name": "积分扣减与兑换下单",
                    "nodeType": "api",
                    "tags": ["shop"],
                    "assignRole": "后端开发",
                    "assignee": "张后端",
                    "description": "大宝使用赚取的 20 B分兑换，扣减余额生成待核销单",
                    "status": "logic_verified",
                    "deps": ["S3-01"],
                    "estimateHours": 3.5,
                    "actualHours": 3.0,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": [
                        "POST /shop/items/{id}/purchase 余额充足成功扣减",
                        "生成 pending_redemption 订单"
                    ]
                },
                {
                    "nodeId": "S3-03",
                    "parentId": "MOD-SHOP",
                    "name": "线下兑现与凭证核销",
                    "nodeType": "feature",
                    "tags": ["shop"],
                    "assignRole": "业务终审",
                    "assignee": "家长审核员",
                    "description": "爸爸核销订单，完成闭环",
                    "status": "review_pass",
                    "deps": ["S3-02"],
                    "estimateHours": 2.0,
                    "actualHours": 1.5,
                    "review": {"humanSignOff": True, "humanSignOffBy": "dad_reviewer", "logicVerified": True},
                    "acceptanceCriteria": ["POST /shop/orders/{id}/redeem 状态变为 redeemed"]
                },
                # ---------- 链条 4: 欲望储蓄挑战 (savings) ----------
                {
                    "nodeId": "S4-01",
                    "parentId": "MOD-SAVINGS",
                    "name": "设立克制挑战",
                    "nodeType": "feature",
                    "tags": ["savings"],
                    "assignRole": "全栈开发",
                    "assignee": "王前端",
                    "description": "设立克制冲动数码外设挑战，目标 ¥2000",
                    "status": "logic_verified",
                    "deps": ["ROOT-PROJECT"],
                    "estimateHours": 2.0,
                    "actualHours": 1.8,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": ["POST /savings/challenges 返回 active 状态"]
                },
                {
                    "nodeId": "S4-02",
                    "parentId": "MOD-SAVINGS",
                    "name": "克制打卡与破功惩罚机制",
                    "nodeType": "api",
                    "tags": ["savings"],
                    "assignRole": "后端开发",
                    "assignee": "张后端",
                    "description": "克制存入增加连续天数，破功则按规则清零惩罚",
                    "status": "logic_verified",
                    "deps": ["S4-01"],
                    "estimateHours": 3.0,
                    "actualHours": 2.5,
                    "review": {"logicVerified": True, "logicVerifiedBy": "agent_cli"},
                    "acceptanceCriteria": [
                        "POST /savings/challenges/{id}/deposit streak_days + 1",
                        "POST /savings/challenges/{id}/breach 清零或扣减"
                    ]
                }
            ]
        }
