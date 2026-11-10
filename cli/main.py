import argparse
import json
import os
import sys
from pathlib import Path

# 将 virtual-manage 根目录加入 sys.path
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cli.scanner import ProjectScanner
from cli.generator import CircuitGenerator
from cli.runner import CircuitRunner, VerificationNotConfigured
from cli.syncer import CircuitSyncer
from flowtree import service

# 退出码约定 (按命令职责):
#   story validate : 格式与引用有效 -> 0 (合法的待确认问题只报告); 有 error -> 1
#   story plan     : 成功生成计划 -> 0 (未映射项只列出); 输入无效 -> 1
#   status         : 成功读取并展示 -> 0 (不因存在未验项而失败); 无法读取 -> 1
#   verify         : 必需范围内每个单元本次自动验证均 passed -> 0; 否则(含未映射/未执行完整/失败/错误) -> 1
#   run / watch    : 旧入口无可信验收依据 -> 1
#   用法错误       : 2 (argparse)

def cmd_init(args):
    target = Path(args.dir or os.getcwd()).resolve()
    print(f"\n⚡ FlowTree CLI: 正在扫描业务工程目录 -> {target}")

    scanner = ProjectScanner(target)
    scan_res = scanner.scan()
    print(f"📁 识别到工程: {scan_res['projectName']}")
    print(f"📄 发现关键文档: {list(scan_res['docs'].keys())}")
    print(f"🛠️  检测技术栈: Flutter={scan_res['tech']['has_flutter']}, FastAPI={scan_res['tech']['has_fastapi']}")

    print("\nℹ️  扫描只定位候选文档路径, 不读取正文、不抽取故事。")
    print("    故事由外部 Agent 整理成 YAML 并提供测试映射, 之后用 `flowtree story validate/plan` 检查。")
    circuit_file = CircuitGenerator(target).generate_all(scan_res["projectName"])
    print(f"🗂️  已生成旧电路视图骨架 (固定模板, 全部节点为未验证状态, 非验收依据): {circuit_file}")

    circuit = CircuitRunner(target).load_circuit()
    sync_res = CircuitSyncer(args.server).sync(circuit)
    if sync_res.get("synced"):
        print(f"📡 骨架已同步至 FlowTree 中心大屏: {args.server}")
    else:
        print(f"⚠️  中心服务器提示 (仅本地离线生效): {sync_res.get('error')}")

    print("\n✅ 初始化完成。尚未执行任何验收。")
    return 0

def cmd_run(args):
    target = Path(args.dir or os.getcwd()).resolve()
    try:
        CircuitRunner(target).run()
    except FileNotFoundError as e:
        print(f"❌ 错误: {e}")
        return 1
    except VerificationNotConfigured as e:
        print(f"❌ 未执行验收: {e}")
        return 1
    return 0

def cmd_status(args):
    target = Path(args.dir or os.getcwd()).resolve()
    circuit_file = target / ".flowtree" / "circuit.json"
    if not circuit_file.exists():
        print(f"❌ 目录 {target} 尚未初始化 FlowTree，请先运行 flowtree init")
        return 1

    with open(circuit_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n⚡ FlowTree 旧电路视图: {data.get('projectName')} ({data.get('projectId')})")
    print("   注意: 这是旧电路模型的状态投影, 不是验收证据, 不代表通过率。")
    if data.get("origin") == "template_unverified":
        print("   节点来自固定模板骨架, 尚未与任何故事或真实测试关联。")
    counts = {}
    for n in data.get("nodes", []):
        counts[n.get("status", "unknown")] = counts.get(n.get("status", "unknown"), 0) + 1
    for status, c in sorted(counts.items()):
        print(f"   {status:<16} {c}")
    print("\n   故事验收计划请用: flowtree story plan <故事目录> --mappings <映射目录>")
    return 0

def cmd_watch(args):
    print("❌ watch 暂不可用: 它原先重复触发会固定通过的模板脚本。")
    print("   请使用 `flowtree verify` 执行真实验收; 监听模式后续再恢复。")
    return 1

def _print_issues(issues):
    for i in issues:
        mark = "❌" if i["severity"] == "error" else "⚠️ "
        print(f"  {mark} [{i['code']}] {i['where']}: {i['message']}")

def _story_paths(args):
    return [Path(p) for p in args.stories], ([Path(p) for p in args.mappings] if args.mappings else None)

def cmd_story_validate(args):
    stories, mappings = _story_paths(args)
    res = service.validate(stories, mappings)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    for s in res["stories"]:
        print(f"📖 {s['id']}  {s['digest']}  ({len(s['units'])} 个可验证单元)")
        for q in s["open_questions"]:
            tag = "旧格式, 保守阻塞整个故事" if q["legacy"] else f"阻塞 {q['blocks']}"
            print(f"   ❓ 待确认 {q['id']}: {q['text']}  [{tag}]")
        if s["untyped_inputs"]:
            print(f"   ℹ️  未声明类型的输入(未做类型校验): {s['untyped_inputs']}")
    for m in res["mappings"]:
        print(f"🔗 映射 {m['path']}  story={m['story']}  {m['digest']}")
    if res["issues"]:
        print("问题:")
        _print_issues(res["issues"])
    print("✅ 格式与引用有效" if res["ok"] else "❌ 校验未通过")
    return 0 if res["ok"] else 1

def cmd_story_plan(args):
    stories, mappings = _story_paths(args)
    res = service.plan(stories, mappings)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    print("📋 验收计划 (未执行任何测试)")
    for s in res["stories"]:
        sm = s["summary"]
        a = sm["automation"]
        print(f"\n{s['id']}  {s['digest']}")
        print(f"  已定义 {sm['units_total']} 个单元 | 未映射 {a['unmapped']} | 已映射未执行 {a['not_run']} | 规则待确认 {sm['rule_pending']} | 人工未验收 {sm['human_unverified']}")
        for u in s["units"]:
            print(f"   {u['id']:<24} 规则={u['rule']:<8} 自动验证={u['automation']:<9} 人工={u['human']}  映射={u['entries'] or '-'}")
        print("  未完成原因: " + "; ".join(sm["incomplete_reasons"]))
    if res["issues"]:
        print("\n问题:")
        _print_issues(res["issues"])
    if not res["ok"]:
        print("❌ 输入存在 error, 计划可能不完整")
    return 0 if res["ok"] else 1

def _print_units(res):
    for s in res["stories"]:
        sm = s["summary"]
        a = sm["automation"]
        counts = " ".join(f"{k}={v}" for k, v in a.items() if v)
        print(f"\n{s['id']}  {s['digest']}")
        print(f"  已定义 {sm['units_total']} 个单元 | {counts} | 证据过期/未知 {sm['units_with_stale_or_unknown_evidence']} | 规则待确认 {sm['rule_pending']} | 人工未验收 {sm['human_unverified']}")
        for u in s["units"]:
            extra = ""
            for e in u["entries"]:
                if e["validity"] not in (None, "current"):
                    extra += f" [{e['entry']}: 历史={e['last_result']} 证据{e['validity']}: {'; '.join(e['validity_reasons'])}]"
            print(f"   {u['id']:<24} 自动验证={u['automation']:<9} 规则={u['rule']:<8} 人工={u['human']}{extra}")
        print("  未完成原因: " + "; ".join(sm["incomplete_reasons"]))
    if res.get("command_failures"):
        print("\n最近一次真实命令存在失败 (与逐场景结果分开呈现):")
        for c in res["command_failures"]:
            print(f"  ⚠️  {c['story']}/{c['entry']} exit={c['exit_code']} 未映射失败={c['unmapped_nonpass']}")
    if res.get("evidence_problems"):
        print("\n证据问题 (这些尝试按 error 处理):")
        for p in res["evidence_problems"]:
            print(f"  ❌ {p}")
    if res["issues"]:
        print("\n问题:")
        _print_issues(res["issues"])

def cmd_verify(args):
    stories, mappings = _story_paths(args)
    res = service.verify(stories, mappings, Path(args.project_root), args.python, args.mapped_only, args.entry)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    if not res["executed"]:
        print(f"❌ 未执行: {res.get('reason')}")
        _print_issues(res["issues"])
        return 1
    print(f"🚀 run {res['run_id']}")
    for a in res["attempts"]:
        extra = f" ({a['reason']})" if a["reason"] else ""
        print(f"  {a['entry']:<28} {a['state']:<10} exit={a['exit_code']} {a['counts']}{extra}")
        if a["unmapped_nonpass"]:
            print(f"      ⚠️  命令中未被映射的测试已失败/出错: {a['unmapped_nonpass']}")
        if a["cleanup"] and (a["cleanup"]["sigterm"] or a["cleanup"]["sigkill"]):
            print(f"      🧹 清理了遗留的进程组成员: {a['cleanup']}")
    _print_units(res)
    print("\n✅ 必需范围本次自动验证全部通过(人工验收与规则确认另计)" if res["ok"] else "\n❌ 必需范围未全部通过或未完整执行")
    return 0 if res["ok"] else 1

def cmd_story_status(args):
    stories, mappings = _story_paths(args)
    res = service.status(stories, mappings, Path(args.project_root), args.python)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    print("📊 当前证据状态 (不执行测试)")
    _print_units(res)
    return 0 if res["ok"] else 1

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="flowtree",
        description="FlowTree CLI - 故事驱动的验收契约与证据工具"
    )
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="FlowTree 中心看板服务地址")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="扫描工程目录并生成旧电路视图骨架 (不执行验收)")
    p_init.add_argument("dir", nargs="?", default=".", help="业务工程目录路径 (默认当前目录)")
    p_init.set_defaults(func=cmd_init)

    p_run = subparsers.add_parser("run", help="[旧入口] 无可信验收依据, 将报告未执行并返回非零")
    p_run.add_argument("dir", nargs="?", default=".", help="业务工程目录路径 (默认当前目录)")
    p_run.set_defaults(func=cmd_run)

    p_status = subparsers.add_parser("status", help="展示旧电路视图的状态分布 (非验收证据)")
    p_status.add_argument("dir", nargs="?", default=".", help="业务工程目录路径 (默认当前目录)")
    p_status.set_defaults(func=cmd_status)

    p_watch = subparsers.add_parser("watch", help="[暂不可用] 待真实执行 (B1b) 提供后恢复")
    p_watch.add_argument("dir", nargs="?", default=".", help="业务工程目录路径 (默认当前目录)")
    p_watch.set_defaults(func=cmd_watch)

    p_story = subparsers.add_parser("story", help="故事契约: 校验与验收计划")
    story_sub = p_story.add_subparsers(dest="story_command", required=True)
    for name, fn, helptext in (
        ("validate", cmd_story_validate, "校验故事(及映射)的格式、引用与摘要"),
        ("plan", cmd_story_plan, "生成验收计划: 分母、映射、未映射与待确认项 (不执行测试)"),
    ):
        sp = story_sub.add_parser(name, help=helptext)
        sp.add_argument("stories", nargs="+", help="故事 YAML 文件或目录")
        sp.add_argument("--mappings", nargs="+", help="测试映射 YAML 文件或目录")
        sp.add_argument("--json", action="store_true", help="输出 JSON")
        sp.set_defaults(func=fn)

    def add_exec_args(sp):
        sp.add_argument("stories", nargs="+", help="故事 YAML 文件或目录")
        sp.add_argument("--mappings", nargs="+", required=True, help="测试映射 YAML 文件或目录")
        sp.add_argument("--project-root", required=True, help="被测项目根目录; 映射的 cwd 相对它解析, 证据写入其 .flowtree/")
        sp.add_argument("--python", help="被测项目的解释器 (映射 argv[0] 为 python* 时使用); 不会静默改用 FlowTree 自己的解释器")
        sp.add_argument("--json", action="store_true", help="输出 JSON")

    p_verify = subparsers.add_parser("verify", help="按映射真实执行一次 pytest 并保存证据")
    add_exec_args(p_verify)
    p_verify.add_argument("--mapped-only", action="store_true", help="必需范围只含已映射单元 (默认: 故事全部单元)")
    p_verify.add_argument("--entry", action="append", help="只执行指定映射条目: STORY/ENTRY, 或在各故事间不重名的裸 ENTRY (可重复; 未知或歧义会报错并不执行)")
    p_verify.set_defaults(func=cmd_verify)

    sp = story_sub.add_parser("status", help="读取已有证据并结合当前基线展示状态 (不执行)")
    add_exec_args(sp)
    sp.set_defaults(func=cmd_story_status)

    parsed = parser.parse_args(argv)
    sys.exit(parsed.func(parsed) or 0)

if __name__ == "__main__":
    main()
