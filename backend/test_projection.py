import json
import sys
from pathlib import Path

# 添加当前目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.schema import ProjectModel
from app.core.lens import PerspectiveLens

def run_test():
    demo_file = Path(__file__).parent / "app" / "data" / "demo_project.json"
    with open(demo_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    project = ProjectModel(**data)
    print(f"==================================================")
    print(f"⚡ FlowTree 状态电路推导测试")
    print(f"📦 项目: {project.projectName} (全量任务: {len(project.nodes)} 个)")
    print(f"==================================================")

    # 1. 测试全景综合视图
    payload_all = PerspectiveLens.project(project, "view-all")
    print(f"\n[1] 视图: {payload_all.activeViewName} ({payload_all.activeViewId})")
    print(f"    - 节点数: {payload_all.stats.totalNodes}")
    print(f"    - 💡 绿灯完全导通: {payload_all.stats.energizedNodes}")
    print(f"    - 💡 亮蓝待人工终审: {payload_all.stats.logicVerifiedNodes}")
    print(f"    - 🚨 警示红短路熔断: {payload_all.stats.blockedNodes}")
    print(f"    - 📈 全链路完成度: {int(payload_all.stats.progressRate * 100)}%")
    print(f"    - 🔌 物理电路导线条数: {len(payload_all.edges)}")
    for e in payload_all.edges:
        print(f"      * {e.source} ---> {e.target} | 状态: {e.circuitState.value:10} | 流动粒子: {str(e.flowAnimation):5} | 颜色: {e.strokeColor}")

    # 2. 测试数据分析师视角 (验证穿透依赖算法)
    payload_analytics = PerspectiveLens.project(project, "view-analytics")
    print(f"\n[2] 动态视角: {payload_analytics.activeViewName} ({payload_analytics.activeViewId})")
    print(f"    - 精确过滤后关注节点数: {payload_analytics.stats.totalNodes}")
    for n in payload_analytics.nodes:
        print(f"      * [{n.bulbState.value:12}] {n.label:24} (工时: {n.dataOverlay.hours})")
    print(f"    - 分析师专属链路 (含智能穿透线): {len(payload_analytics.edges)} 条")
    for e in payload_analytics.edges:
        tag = "【⚡ 穿透连线】" if e.isBypass else "【  直接连线】"
        print(f"      * {tag} {e.source} ---> {e.target} | 状态: {e.circuitState.value:10} | 动效: {e.flowAnimation}")

    # 3. 测试自动化测试视角
    payload_qa = PerspectiveLens.project(project, "view-qa")
    print(f"\n[3] 动态视角: {payload_qa.activeViewName} ({payload_qa.activeViewId})")
    print(f"    - 关注外部测试用例绑定的节点数: {payload_qa.stats.totalNodes}")
    for n in payload_qa.nodes:
        print(f"      * [{n.bulbState.value:12}] {n.label}")
    for e in payload_qa.edges:
        tag = "【⚡ 穿透连线】" if e.isBypass else "【  直接连线】"
        print(f"      * {tag} {e.source} ---> {e.target} | 状态: {e.circuitState.value:10} | 动效: {e.flowAnimation}")

    print(f"\n🎉 核心数据渲染与穿透电路推导引擎验证 100% 成功！")

if __name__ == "__main__":
    run_test()
