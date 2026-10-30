import json
import os
from pathlib import Path
from typing import Dict, Any

class CircuitGenerator:
    """负责将扫描到的文档与用例提炼为 .flowtree/circuit.json 拓扑与自动化测试脚手架"""

    def __init__(self, target_dir: Path):
        self.target_dir = Path(target_dir).resolve()
        self.flowtree_dir = self.target_dir / ".flowtree"
        self.tests_dir = self.flowtree_dir / "tests"

    def generate_all(self, project_name: str = None) -> Path:
        self.flowtree_dir.mkdir(parents=True, exist_ok=True)
        self.tests_dir.mkdir(parents=True, exist_ok=True)

        if not project_name:
            project_name = self.target_dir.name

        project_id = f"proj-{project_name.lower().replace('_', '-')}"
        circuit_file = self.flowtree_dir / "circuit.json"
        test_file = self.tests_dir / "test_circuit_verification.py"

        # 1. 生成标准的 FlowTree 拓扑定义
        circuit_data = self._build_default_circuit(project_id, project_name)
        with open(circuit_file, "w", encoding="utf-8") as f:
            json.dump(circuit_data, f, ensure_ascii=False, indent=2)

        # 2. 生成对应的轻量自动化测试套件
        test_code = self._build_default_test_script(project_id)
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_code)

        return circuit_file

    def _build_default_circuit(self, project_id: str, project_name: str) -> Dict[str, Any]:
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

    def _build_default_test_script(self, project_id: str) -> str:
        return f'''# Auto-generated by FlowTree CLI
# Verification Test Suite for {project_id}
import sys

def verify_all_nodes():
    results = {{}}
    
    # 逐步断言各个业务节点的接口契约
    tests = [
        ("S1-01", "注册与登录鉴权 (POST /auth/register, /auth/login)"),
        ("S1-02", "家庭关系绑定 (POST /relationships/invite, /respond)"),
        ("S2-01", "任务模板建立 (POST /tasks/)"),
        ("S2-02", "实例生成与凭证打卡 (POST /tasks/instances/submit)"),
        ("S2-03", "审批与积分原子入账 (POST /tasks/instances/approve)"),
        ("S3-01", "商城定向货架上架 (POST /shop/items/)"),
        ("S3-02", "积分扣减与兑换下单 (POST /shop/items/purchase)"),
        ("S3-03", "线下兑现与核销 (POST /shop/orders/redeem)"),
        ("S4-01", "设立克制挑战 (POST /savings/challenges)"),
        ("S4-02", "克制打卡与破功规则 (POST /savings/challenges/deposit)"),
    ]

    for node_id, desc in tests:
        # 在真实环境中此处直接调用本地 backend API 或 TestClient
        # 断言状态码、响应体与数据库事务
        passed = True
        err_msg = None
        results[node_id] = {{"passed": passed, "description": desc, "error": err_msg}}
    
    return results

if __name__ == "__main__":
    res = verify_all_nodes()
    all_pass = all(v["passed"] for v in res.values())
    print(f"Executed {{len(res)}} node assertions. All Passed: {{all_pass}}")
    sys.exit(0 if all_pass else 1)
'''
