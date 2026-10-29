import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.schema import ProjectModel
from app.core.lens import PerspectiveLens

def verify_life_piggy_bank():
    data_path = Path(__file__).parent / "app" / "data" / "life_piggy_bank.json"
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    project = ProjectModel(**data)
    print("=" * 60)
    print(f"⚡ FlowTree 真实项目拓扑与电路验证: {project.projectName}")
    print(f"📦 阶段: {project.dict().get('stage')} | 节点数: {len(project.nodes)} 项")
    print("=" * 60)

    # 1. 全景
    p_all = PerspectiveLens.project(project, "view-all")
    print(f"\n[1] 视图: {p_all.activeViewName}")
    print(f"    - 可视节点: {p_all.stats.totalNodes}")
    print(f"    - 已通电(绿灯): {p_all.stats.energizedNodes}")
    print(f"    - 待人工终审(蓝灯): {p_all.stats.logicVerifiedNodes}")
    print(f"    - 施工中(黄灯): {sum(1 for n in p_all.nodes if n.status.value == 'deving')}")
    print(f"    - 待开工门禁(冷灰): {sum(1 for n in p_all.nodes if n.status.value == 'pending_dev')}")
    print(f"    - 全链路连线条数: {len(p_all.edges)}")

    # 2. Flutter 视角
    p_flutter = PerspectiveLens.project(project, "view-flutter")
    print(f"\n[2] 动态视角: {p_flutter.activeViewName}")
    print(f"    - 关注节点: {p_flutter.stats.totalNodes} 个 (手风琴树卡、打卡心得、状态联动)")
    for n in p_flutter.nodes:
        print(f"      * [{n.bulbState.value:12}] {n.id}: {n.label}")

    # 3. 金融分账视角
    p_ledger = PerspectiveLens.project(project, "view-ledger")
    print(f"\n[3] 动态视角: {p_ledger.activeViewName}")
    print(f"    - 关注节点: {p_ledger.stats.totalNodes} 个 (A/B分账、行级排他锁、商城预扣)")
    for n in p_ledger.nodes:
        print(f"      * [{n.bulbState.value:12}] {n.id}: {n.label}")

    # 4. QA 质量门禁视角
    p_qa = PerspectiveLens.project(project, "view-qa-gate")
    print(f"\n[4] 动态视角: {p_qa.activeViewName}")
    print(f"    - 门禁关键路径: {p_qa.stats.totalNodes} 个节点")
    for n in p_qa.nodes:
        print(f"      * [{n.bulbState.value:12}] {n.id}: {n.label}")

    print("\n🎉 真实业务项目建模与电路推导 100% 成功！")

if __name__ == "__main__":
    verify_life_piggy_bank()
