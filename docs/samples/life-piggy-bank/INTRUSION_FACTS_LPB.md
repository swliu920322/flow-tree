# FlowTree 工作在 Life-Piggy-Bank 中留下的文件：事实清单

日期：2026-11-12。性质：**只是事实清单**，用 `git log`、`git status`、`ls` 核对而来；不是清单格式（MANIFEST）的设计，不决定目录迁移、审计命令、CI 或签字入口。清单范围只到"能从 git 与目录直接确认的事实"；没有逐个判断的地方都标了。

## 1. 已提交进 LPB 的（明确由 FlowTree 验收工作产生）

| 提交 | 文件 | 新增/修改 | 说明 |
|---|---|---|---|
| `6391ce2` | `test_integration/support/real_backend.dart` | 新增 | 隔离后端启动封装（临时 SQLite、随机端口、信号清理） |
| `6391ce2` | `test_integration/support/kit.dart` | 新增 | 联调测试辅助（后端 API 封装、全局状态保存与恢复、有期限的等待） |
| `6391ce2` | `test_integration/real_backend_a_task_test.dart` | 新增 | A 任务联调 |
| `6391ce2` | `test_integration/real_backend_two_checkins_test.dart` | 新增 | US-23 联调 |
| `cba838e` | `test_integration/real_backend_b_review_test.dart` | 新增 | US-24 联调（发行人侧用 API） |
| `cba838e` | `test_integration/support/kit.dart` | **修改**（自己新增的文件，追加辅助函数） | 双账号相关辅助 |
| `12cede1` | `test_integration/real_backend_b_review_two_ui_test.dart` | 新增 | US-24 双界面联调 |
| `199b285` | `test/page_reentry_and_review_wire_test.dart` | 新增 | 页面重进与执行人查看审批结果的客户端测试 |
| `ed81f99` | `test/savings_submission_wire_test.dart` | 新增 | 储蓄提交与重放的精确请求断言 |
| `a4cc0a0` | `FLOWTREE_SESSION_HANDOFF_2026-11-10.md` | 新增 | 交接文档 |
| `a4cc0a0` | `CLAUDE_CODEX_HANDOFF.md`、`MOBILE_LAYOUT_AUDIT.md`、`PRE_SELF_USE_ACCEPTANCE_REVIEW.md`、`USER_STORY_MAP.md` | **修改** | 状态说明与验收状态的澄清 |

**修改过的项目已有文件（本清单已明确归属的范围）**（这是侵入里最需要审查的一类）：`CLAUDE_CODEX_HANDOFF.md`、`MOBILE_LAYOUT_AUDIT.md`、`PRE_SELF_USE_ACCEPTANCE_REVIEW.md`、`USER_STORY_MAP.md`，均为文档，提交 `a4cc0a0`。没有修改任何业务源码或既有测试文件。

**没有判断是否属于 FlowTree 工作的提交**：更早的提交，以及最近 8 次里的 `e97aaa9`、`f8e0041`（依赖锁定、旧入口保护），这些是项目自己此前的工作，没有逐个分析。

## 2. 项目专用工具与未跟踪产物（复验后更新）

| 路径 | 内容 | 状态 |
|---|---|---|
| `tools/manual_acceptance/manual_env.sh` | 人工验收用隔离后端脚本 | 已提交 `3095a98` |
| `tools/manual_acceptance/manual_client.sh` | 人工验收用客户端脚本（临时副本 + 内存会话） | 已提交 `3095a98`，MANUAL-01/02/03 及生成目录范围已独立复验 |
| `tools/manual_acceptance/test_manual_client_scope.sh` | 上一个脚本的清理/复用范围回归 | 已提交 `3095a98` |
| `.flowtree/` | FlowTree 写入的目录（见第 3 节） | 未跟踪 |

## 3. `.flowtree/` 里有什么

| 内容 | 来源 |
|---|---|
| `runs/`（15 次运行记录，含本次刷新） | 证据：每次执行的清单、各测试结果、基线摘要、原始报告与哈希 |
| `circuit.json`、`data.db` | 最早的"电路图"功能遗留 |
| `tests/test_circuit_verification.py`（含 `__pycache__`） | 旧电路验证的遗留测试 |
| `env.salt` | 给环境变量做摘要用的盐值 |

**注意**：LPB 里没有忽略 `.flowtree/` 的规则（`.gitignore` 中没有，`git check-ignore` 也没有命中），在 `git status` 中它是"未跟踪"；只有 FlowTree 自己的仓库忽略它。是否在 LPB 加本地排除规则（如 `.git/info/exclude`），**尚未决定，也没有改动**。

## 4. LPB 之外、但属于这套工作的文件（不在 LPB 里）

| 位置 | 内容 |
|---|---|
| FlowTree 仓库 `examples/stories/`、`examples/mappings/` | LPB 的故事与映射（TASK-A-001、TASK-A-002、TASK-B-001、SAV-001） |
| FlowTree 仓库 `.flowtree/workspaces.yaml`（本机文件，被 FlowTree 忽略） | 各工作区配置：项目路径、解释器、环境、伴随运行时声明；含本机绝对路径 |
| FlowTree 仓库 `docs/` | 方案、复验记录、验收清单、规则确认记录等 |

即：**故事、映射、工作区配置目前不在 LPB 里**。

## 5. 对 LPB 评审与验证状态的影响（事实）

- 新增 tools 曾使旧证据待更新；脚本定稿并提交后已刷新：US-23 `run_20261112T121403_6f6a87eb`（5 项当前有效），US-24 `run_20261112T121416_063a4d2d`（7 项当前有效），其他故事未刷新。
- 副本客户端和隔离后端由人工验收脚本在系统临时目录里创建，用完由脚本删除；它们不在 LPB 里，也不入 git。
- 人工验收脚本在运行期间还会在 `~/Library/Containers/com.lifepiggybank.manualAcceptance` 留下一个只含偏好与引擎缓存的沙盒容器（几十 KB，空壳受系统保护删不掉），不在 LPB 里。
