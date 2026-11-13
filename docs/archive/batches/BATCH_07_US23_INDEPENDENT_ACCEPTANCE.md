# US-23 正式映射与独立执行核对

日期：2026-11-11。所有本批改动未提交，未 push。

## 结论

B7-01/02 修复经 Codex 聚焦复跑：实现方 15 项、原独立 5 项全部通过。另将 `baseline.probe_runtime` 的 pytest 探测改为显式 `-I -B`，新增独立只读检查通过（返回内容保持不变）；本次合计 21 项通过，不冒充框架全量回归结果。Claude 正在运行的全量结果另行记录。

正式新增 `examples/mappings/task-a-002.mapping.yaml`，声明 companions=[backend-python]，一个 exact 联调用例覆盖 TASK-A-002 的五个单元；任何该用例断言失败都会使五个单元一起不通过，不声称逐步骤独立测试粒度。

## 真实执行

独立工作区 `life-piggy-bank-us23`（配置在忽略的 `.flowtree/workspaces.yaml`），只读取本故事和本映射。固定 Flutter PATH、HOME、LPB_INT_BACKEND_DIR、LPB_INT_PYTHON；伴随声明绑定同一个绝对 Python 路径。账号与任务由真实后端 API 准备，登录及两次打卡经真实界面；临时 SQLite，不是 MySQL。

命令：`.venv/bin/python -m cli.main workspace verify life-piggy-bank-us23 --mapped-only --json`，随后同工作区 status --json。

run：`run_20261111T043824_3c488a8a`；1 个条目、1 项真实联调测试通过，五个单元均 passed/current，退出码 0，未映射 0，无证据完整性问题。核对 manifest、产物哈希和 changed_during_run；测试前后样本源码摘要一致，未改样本业务源码/测试。

通过 FastAPI TestClient 读取 `/api/workspaces/life-piggy-bank-us23/stories/TASK-A-002?refresh=true`：五个自动化通过，过期/未知 0；规则仍 draft、五项人工未验收、complete=false。页面选择“Life-Piggy-Bank US-23 两次打卡联调”即可读取这批证据；未另做浏览器点击回归。

## 证据边界

本次没有刷新旧三条示范故事，不把本次五项通过外推为 24 项当前通过。新任务页仍是压栈打开、原页保留；不证明销毁重建原页或冷启动。负责人的规则确认与人工验收仍待完成，自动化不代签。

本机审计文件：`.flowtree/reviews/b7-us23-codex/`，包含 verify/status 原始输出、命令、源码摘要及 Web 响应。正式运行产物在 LPB `.flowtree/runs/run_20261111T043824_3c488a8a/`；均不入库。

## B7-03：超时已终止后端，但临时数据库目录残留

使用 `/private/tmp` 内的独立 Flutter 项目，复制现有 RealBackend 辅助，通过相同 pinned companion 配置启动真实后端；就绪后将后端 PID、端口、tempDirPath 写到观察文件，并让测试等待五分钟。临时映射 timeout_s=20，主动验证测试主体确实进入后端就绪阶段才超时。

结果：verify 非零、attempt=error、reason=timeout after 20s；cleanup.cleared=true、SIGTERM 已发、无须 SIGKILL；观察文件确认后端已启动。随后后端 PID 不存在、端口拒绝连接，但 `/tmp/lpb_int_RAuplq` 数据库目录仍存在。Codex 已仅删除该次夹具明确记录的残留路径，并清理临时项目。该负例没有写入正式故事或正式项目证据，也不使正常通过记录被覆盖。

这表明进程组清理可用，但测试的 tearDownAll 在外部终止时不足以保证目录回收。请 Claude 为联调辅助提出最小的异常终止清理方案并补反例；不得按目录前缀扫描删除其他会话资源，不扩大成通用清理框架。强制 SIGKILL 无法执行进程内清理的限制也须明确。当前只确认进程/端口清理通过，不能宣称超时无临时目录残留。

首次两次临时夹具因 package_config 项目名称、package_graph 元数据不完整，Flutter 在启动后端前报错；这两次均不计为超时验证。补齐离线元数据后才得到上述有后端就绪标记的有效结果。三个尝试均留有本机审计日志，不改样本配置、不运行 pub get。Flutter 初始崩溃会附带自身诊断输出，这些不作为业务验收证据。

## B7-03 修复后独立复验

LPB RealBackend 新增本实例 SIGTERM/SIGINT 监听，清理自己登记的子进程与临时目录；不扫描其他会话资源。SIGKILL 无法捕获，仍不保证进程内清理。本次不修改 FlowTree，未重复框架全量回归。

复用原先能抓到残留的独立夹具，在后端就绪后触发 20 秒超时：verify 非零、attempt=error（预期），cleanup.cleared=true、SIGTERM=true、SIGKILL=false；后端 PID 59319 已退出，端口 62800 拒绝连接，`/tmp/lpb_int_lNQUK6` 不存在。此次没有由复验脚本补删数据库目录，B7-03 在可处理 SIGTERM 的路径通过。

修复后审计目录：`.flowtree/reviews/b7-us23-cleanup-fixed/`。Claude 报告框架全量 499 项及 LPB test_integration 七项通过，这两项属于实现方运行结果，Codex 本轮未重复全量执行。

辅助修复后正式刷新：run `run_20261111T045600_34de05e0`，1 个联调测试通过、五个单元 current/passed、verify/status 均退出 0，无证据完整性问题。Web refresh=true 复核同样五项有效通过，规则仍 draft、人工未验收、complete=false；测试及页面读取前后样本源码摘要一致。旧运行保留为历史，本段为最新正式执行。未提交、未 push。
