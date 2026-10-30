import argparse
import os
import sys
import time
from pathlib import Path

# 将 virtual-manage 根目录加入 sys.path
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cli.scanner import ProjectScanner
from cli.generator import CircuitGenerator
from cli.runner import CircuitRunner
from cli.syncer import CircuitSyncer

def cmd_init(args):
    target = Path(args.dir or os.getcwd()).resolve()
    print(f"\n⚡ FlowTree CLI: 正在扫描业务工程目录 -> {target}")

    scanner = ProjectScanner(target)
    scan_res = scanner.scan()
    print(f"📁 识别到工程: {scan_res['projectName']}")
    print(f"📄 发现关键文档: {list(scan_res['docs'].keys())}")
    print(f"🛠️  检测技术栈: Flutter={scan_res['tech']['has_flutter']}, FastAPI={scan_res['tech']['has_fastapi']}")

    print("\n🤖 内置 Agent 正在根据需求文档抽取业务用例与接口断言链条...")
    generator = CircuitGenerator(target)
    circuit_file = generator.generate_all(scan_res["projectName"])
    print(f"✨ 成功在业务工程根目录生成: {circuit_file}")
    print(f"🧪 自动化验收断言套件就绪: {target / '.flowtree' / 'tests' / 'test_circuit_verification.py'}")

    # 尝试同步到 FlowTree 中心服务器
    syncer = CircuitSyncer(args.server)
    runner = CircuitRunner(target)
    run_res = runner.run()
    sync_res = syncer.sync(run_res["circuitData"])
    if sync_res.get("synced"):
        print(f"📡 遥测数据已成功同步至 FlowTree 中心大屏: {args.server}")
    else:
        print(f"⚠️  中心服务器提示 (仅本地离线生效): {sync_res.get('error')}")

    print("\n✅ 项目初始化完成！现在可在该目录运行 `flowtree watch` 开启实时代码巡检。")

def cmd_run(args):
    target = Path(args.dir or os.getcwd()).resolve()
    print(f"\n🚀 FlowTree CLI: 执行自动化验收巡检 -> {target}")
    runner = CircuitRunner(target)
    try:
        res = runner.run()
    except FileNotFoundError as e:
        print(f"❌ 错误: {e}")
        return

    print(f"📊 测试结果: 共断言 {res['totalTested']} 个节点")
    print(f"   🟢 逻辑打通 (Logic Verified): {len(res['passedNodes'])} 个 -> {res['passedNodes']}")
    if res['blockedNodes']:
        print(f"   🔴 物理卡点 (Blocked): {len(res['blockedNodes'])} 个 -> {res['blockedNodes']}")
    else:
        print("   ⚡ 主干电路完全通电，无物理卡点！")

    syncer = CircuitSyncer(args.server)
    sync_res = syncer.sync(res["circuitData"])
    if sync_res.get("synced"):
        print(f"📡 状态已实时同步到大屏: {args.server}/canvas?project={res['projectId']}")
    else:
        print(f"ℹ️  本地离线运行中 (中心大屏未连接)")

def cmd_status(args):
    target = Path(args.dir or os.getcwd()).resolve()
    circuit_file = target / ".flowtree" / "circuit.json"
    if not circuit_file.exists():
        print(f"❌ 目录 {target} 尚未初始化 FlowTree，请先运行 flowtree init")
        return

    import json
    with open(circuit_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n=======================================================")
    print(f"⚡ FlowTree 业务电路健康看板: {data.get('projectName')} ({data.get('projectId')})")
    print(f"=======================================================")
    nodes = data.get("nodes", [])

    MODULE_NAMES = {
        "MOD-AUTH": "连接与家庭约定",
        "MOD-TASK": "任务派发与审批",
        "MOD-SHOP": "愿望与商城兑现",
        "MOD-SAVINGS": "克制欲望储蓄"
    }

    # 按模块分类统计
    modules = {}
    for n in nodes:
        if n["nodeId"] == "ROOT-PROJECT":
            continue
        mid = n.get("parentId") or n.get("moduleId") or "MAIN"
        mname = MODULE_NAMES.get(mid, n.get("moduleName", mid))
        if mid not in modules:
            modules[mid] = {"name": mname, "total": 0, "verified": 0, "blocked": 0}
        modules[mid]["total"] += 1
        if n.get("status") in ("logic_verified", "review_pass"):
            modules[mid]["verified"] += 1
        elif n.get("status") == "blocked":
            modules[mid]["blocked"] += 1

    print(f"{'模块ID':<15} {'模块名称':<18} {'通过率':<12} {'状态'}")
    print("-" * 60)
    for mid, m in modules.items():
        pct = int((m["verified"] / m["total"]) * 100) if m["total"] > 0 else 0
        state_icon = "🟢 正常通电" if m["blocked"] == 0 else "🔴 存在卡点"
        print(f"{mid:<15} {m['name']:<18} {pct:>3}% ({m['verified']}/{m['total']})    {state_icon}")
    print("=" * 60)

def cmd_watch(args):
    target = Path(args.dir or os.getcwd()).resolve()
    print(f"\n👀 FlowTree Watcher 启动中: 正在监听工程目录 -> {target}")
    print(f"💡 修改代码或测试后将自动执行断言并点亮电路看板 (按 Ctrl+C 退出)...")

    # 首次启动先跑一次
    cmd_run(args)

    watch_dirs = [target / "backend", target / "lib", target / ".flowtree" / "tests"]
    existing_dirs = [d for d in watch_dirs if d.exists()]
    if not existing_dirs:
        existing_dirs = [target]

    def get_max_mtime():
        max_t = 0.0
        for wd in existing_dirs:
            for root, _, files in os.walk(wd):
                if any(ignored in root for ignored in [".git", "__pycache__", "build", ".dart_tool"]):
                    continue
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        t = os.path.getmtime(fp)
                        if t > max_t:
                            max_t = t
                    except OSError:
                        pass
        return max_t

    last_mtime = get_max_mtime()
    try:
        while True:
            time.sleep(1.5)
            curr_mtime = get_max_mtime()
            if curr_mtime > last_mtime:
                last_mtime = curr_mtime
                print(f"\n🔄 [{time.strftime('%H:%M:%S')}] 检测到代码或用例文件变更，触发自动化巡检...")
                cmd_run(args)
    except KeyboardInterrupt:
        print("\n👋 FlowTree Watcher 已安全停止。")

def main():
    parser = argparse.ArgumentParser(
        prog="flowtree",
        description="FlowTree CLI - 面向业务开发的自主测试中枢与电路健康看板"
    )
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="FlowTree 中心看板服务地址")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="扫描工程目录并初始化 .flowtree 拓扑与测试脚手架")
    p_init.add_argument("dir", nargs="?", default=".", help="业务工程目录路径 (默认当前目录)")
    p_init.set_defaults(func=cmd_init)

    # run
    p_run = subparsers.add_parser("run", help="执行自动化断言套件并更新本地电路与中心大屏")
    p_run.add_argument("dir", nargs="?", default=".", help="业务工程目录路径 (默认当前目录)")
    p_run.set_defaults(func=cmd_run)

    # status
    p_status = subparsers.add_parser("status", help="在终端打印当前工程的电路健康度与卡点")
    p_status.add_argument("dir", nargs="?", default=".", help="业务工程目录路径 (默认当前目录)")
    p_status.set_defaults(func=cmd_status)

    # watch
    p_watch = subparsers.add_parser("watch", help="监听代码变更，实时触发测试断言并点亮电路")
    p_watch.add_argument("dir", nargs="?", default=".", help="业务工程目录路径 (默认当前目录)")
    p_watch.set_defaults(func=cmd_watch)

    parsed = parser.parse_args()
    parsed.func(parsed)

if __name__ == "__main__":
    main()
