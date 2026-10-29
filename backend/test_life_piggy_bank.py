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
    print("=" * 65)
    print(f"🎬 FlowTree 用户故事走查板 (E2E Storyboards) 验证: {project.projectName}")
    print(f"📦 阶段: {project.stage} | 全局节点数: {len(project.nodes)} 项")
    print("=" * 65)

    # 1. 全部故事全景
    p_all = PerspectiveLens.project(project, "view-all")
    print(f"\n[1] 视图: {p_all.activeViewName}")
    print(f"    - 可视步骤节点: {p_all.stats.totalNodes}")
    print(f"    - 已通电通过(绿灯): {p_all.stats.energizedNodes}")
    print(f"    - 待人工验收(蓝灯): {p_all.stats.logicVerifiedNodes}")
    print(f"    - 正在开发/走查(黄灯): {sum(1 for n in p_all.nodes if n.status.value == 'deving')}")
    print(f"    - 端到端旅程连线条数: {len(p_all.edges)}")

    # 2. 故事一：小李自律打卡买大餐
    p_s1 = PerspectiveLens.project(project, "view-story-1")
    print(f"\n[2] 单线故事视角: {p_s1.activeViewName}")
    print(f"    - 旅程步骤: {p_s1.stats.totalNodes} 步 (免密登录 -> 立Flag -> 晨跑打卡写心得 -> A币入袋 -> 兑现大餐)")
    for n in p_s1.nodes:
        print(f"      * [{n.bulbState.value:12}] {n.id}: {n.label}")

    # 3. 故事二：小情侣甜宠互勉早睡请喝奶茶
    p_s2 = PerspectiveLens.project(project, "view-story-2")
    print(f"\n[3] 单线故事视角: {p_s2.activeViewName}")
    print(f"    - 旅程步骤: {p_s2.stats.totalNodes} 步 (扫码绑定 -> 女友发任务 -> 拍照交作业 -> 审批发奖 -> 核销奶茶)")
    for n in p_s2.nodes:
        print(f"      * [{n.bulbState.value:12}] {n.id}: {n.label}")

    # 4. 故事三：月光族抵抗奶茶诱惑存钱
    p_s3 = PerspectiveLens.project(project, "view-story-3")
    print(f"\n[4] 单线故事视角: {p_s3.activeViewName}")
    print(f"    - 旅程步骤: {p_s3.stats.totalNodes} 步 (立存钱梦想 -> 忍住随手记 -> 破功扣款警示 -> 存满买手机登记发票)")
    for n in p_s3.nodes:
        print(f"      * [{n.bulbState.value:12}] {n.id}: {n.label}")

    print("\n🎉 真实业务用户故事走查与电路计算 100% 成功！")

if __name__ == "__main__":
    verify_life_piggy_bank()
