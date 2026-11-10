# 第五批交付记录（Claude）：成功后的页面重进与审批结果/历史

日期：2026-11-11。任务书：`docs/BATCH_05_CLAUDE_TASK_2026-11-11.md`、`docs/OPEN_QUESTIONS.md`。FlowTree 基线 HEAD `0608f18`，样本项目 HEAD `ed81f99`。**只新增了一个测试文件**，未改业务源码、已有测试、夹具，也未改 FlowTree 的 `examples/`、`tests/independent/`、框架实现或流程图；均未暂存、未提交。

## 1. 新增文件

Life-Piggy-Bank：`test/page_reentry_and_review_wire_test.dart`（未跟踪）。6 个测试，真实 `flutter test` 全部通过。

方法：真实的 `HttpSavingsRepository` / `HttpTaskRepository`，以及 `AuthService.refreshProfile` 的真实 HTTP 请求，都跑在同一个**有状态的内存假服务端**上（拦截 `http.Client`，持有数据，记录全部请求）。界面只能通过现有业务路径（控制器 `loadData`、提交、`refreshProfile`）得到服务端状态；测试从不手工写控制器或 `AuthService` 单例的状态（登录后的初始用户态除外，属各用例前置条件，与已有测试做法一致）。"离开再进入"用 `Navigator` push/pop 真实销毁并重建页面 `State`（含自建控制器），并断言旧 `State.mounted == false`、新 `State` 与旧的不是同一个对象。

## 2. 实际核对到的事实（先于实施的简报）

- **积分来源**：`TasksPage` 把 `deps.authService.refreshProfile()` 作为 `onRefreshProfile` 交给控制器；它 GET `/auth/me` 并写入 `AuthService.userNotifier`（应用内单例）。**`TasksController.loadData()` 自己就调用 `onRefreshProfile`**，所以任务页每次进入都会重新取回个人资料——重进时 A 积分是重新从服务端取回的，不只是同会话内存。我最初预设相反并写了一条"表征"测试，运行后发现错误，已改成证明"重新取回"的用例（不保留错误的表征）。
- **B 余额入口**：不在任务页，在 `HomeShell` 账户弹层（AppBar 的用户名入口）的"余额汇总"卡片，按发行人显示 `发行人名: 积分` 的 Chip；弹层读的是全局 `userNotifier`。真实导航：切到商城 tab（`HomeShell` 此时调用 `refreshProfile`）→ 点用户名。账户弹层需要应用级 `LocaleScope`，测试宿主按完整应用的做法提供。
- `AppDependencies.forTesting` 对没传的仓储默认塞入 **Mock 且优先于在线模式**，所以必须显式传入基于同一拦截客户端的 HTTP 仓储（否则页面显示离线 Mock 数据，请求日志为空——我首次运行就踩到了，并据此修正）。

## 3. 实际断言与边界（真实完整测试名在第 4 节）

**SAV-001.STEP-04（仅"已知成功后"）**
- 真实编辑金额 50.00 并提交；服务端因这次真实 POST 变为 250.00 / 6 天 / 2 笔，界面一致。
- 离开：`SavingsPage` 消失、旧 `State.mounted == false`；重进：新 `State`（因而是新的自建控制器），不重用旧的。
- 重进后重新 GET `/savings/my`（计数增加）；余额、连续天数、记录数与**服务端**状态及**离开前**一致；重进**没有任何写请求**（全部请求里只有 1 个 POST），服务端记录仍是 2 条，无重复。
- 第二个用例：离开期间服务端状态变化（另一设备又记了一笔 10 元），重进显示服务端最新的 260.00 / 7 天 / 3 笔——证明是重新取回，而不是沿用旧页面内存。
- **不暗含**未知结果恢复、跨进程持久化；未知结果期间离页的待确认请求见 Q-SAV-NAV-001，本批不触碰。

**TASK-A-001.STEP-04（同一登录会话）**
- 前置：零关系用户（`/auth/relationships/my` 为空），A 积分 0.00，服务端与客户端一致。
- 完成（打卡→确认提交）后：服务端仅 1 次 POST、`points_a = 15.00`；客户端 A 积分 15.00 **只能经 `loadData→refreshProfile→GET /auth/me`** 更新（断言 `/auth/me` 计数在提交后增加，且从未手工写单例）。
- 离开再进入（新 `State`）：重新 GET `/tasks/my` 与 `/auth/me`（计数均增加）；任务仍显示"✓ 已完成"，不再提供"打卡"入口；**没有再次提交/发奖**（仍 1 个 POST、1 条提交记录、服务端积分仍 15.00）；客户端积分与服务端一致且与离开前一致。
- 第二个用例：离开期间服务端积分变为 20.0，重进后客户端显示 20.0。**这证明 A 积分是重进时重新取回的，**不是仅靠同会话内存；但**不证明杀进程后恢复**（本测试在同一进程、同一登录会话内）。

**TASK-B-001.STEP-04（发行人审批由测试模拟）**
- 明确：发行人的驳回/批准由测试直接操作假服务端（`simulateIssuerReject/Approve`）模拟，**不是在测试真实审批服务端**；后端真实审批/事务语义继续引用既有后端测试，本批不冒充端到端联调。
- 阶段验证（每次重新进入由 GET 取回）：首次提交→"审批中"、进度 0/1、B 余额不变；驳回后显示"驳回原因: …"，进度与余额仍不增加；重提 v2→仍不增加；批准后重进显示 1/1、"✓ 已完成"，重进没有再次提交。
- 历史（"查看打卡历史"入口，内容来自 GET `/tasks/instances/{id}/submissions`）：v1 保留原凭证、状态已驳回、驳回原因仍在；v2 为新凭证、已通过、审批人"爸爸"；两条"第 N 次打卡"。
- B 余额：批准发生在服务端后，客户端此刻余额仍是旧的（断言了，不手工灌值）；沿真实导航（切商城 tab 触发 `refreshProfile` → 点用户名打开账户弹层）看到"爸爸: 25"与"妈妈: 5"，且客户端 `balancesB` 为 `dad-1:25.0 / mom-1:5.0`——只记入原发行人，另一发行人账本不变。

## 4. 真实完整测试名（`test/page_reentry_and_review_wire_test.dart::` 之后）

1. `SAV-001.STEP-04 成功记录后离开页面再重新进入: 进度和记录保持一致 (仅已知成功后) 成功后卸载页面与自建控制器, 新页面重新 GET: 余额/连续天数/记录列表与服务端及离开前一致, 重进不发任何写请求、不重复记录`
2. `SAV-001.STEP-04 … 离开期间服务端状态变化(另一设备又记了一笔): 重新进入显示服务端最新状态, 证明是重新取回而不是沿用旧页面内存`
3. `TASK-A-001.STEP-04 零关系本人任务完成后退出任务页面再进入: 完成状态和积分保持一致 (同一登录会话) 完成后离开再进入: 任务仍完成、没有再次提交/发奖请求; A 积分 15.00 来自现有路径 loadData→refreshProfile(GET /auth/me), 重进时重新从服务端取回`
4. `TASK-A-001.STEP-04 … 离开期间服务端积分变化(例如另一设备): 重新进入后客户端显示服务端最新值, 证明 A 积分是重进时重新取回的, 不是仅靠同会话内存`
5. `TASK-B-001.STEP-04 执行人查看审批结果与提交历史 (发行人审批由测试模拟, 不是真实审批服务) 待审/驳回/重提阶段进度与奖励不增加; 批准后才增加; 历史 v1 保留原凭证与驳回原因, v2 为新凭证/已通过; GET 与界面一致`
6. `TASK-B-001.STEP-04 … 批准后 B 奖励只记入原发行人账本: 沿真实导航(切到商城 tab 触发 refreshProfile → 打开账户弹层)看到 爸爸 +25.00, 妈妈 保持 5.00`

（"…"处是同组的组名；精确 JSON 已导出到本机 scratchpad `b5/ids.json`，也可用 `flutter test --no-pub --reporter json <文件>` 取 `testStart.test.name`。）

## 5. 命令、计数与证据

在最小环境（与 pinned 一致：`env -i`，`PATH`=Flutter+系统目录，`HOME`），`--no-pub`，不升级、不部署、不碰真实库：

```
flutter --no-version-check --suppress-analytics test --no-pub --reporter expanded test/page_reentry_and_review_wire_test.dart
```
**6 passed、0 failed、0 skipped**；JSON 事件流：协议 0.1.1，`done.success=true`，6 个真实测试均 `success` 且未 skip。`flutter analyze --no-pub` 对本文件与上批新增文件均"No issues found"。证据（本机，不入库）：scratchpad `b5/run6.txt`（expanded 日志）、`b5/events.jsonl`、`b5/ids.json`。只运行了新增文件，没有重跑其他测试（除变异对照里列出的直接相关文件）。本批没有通过 FlowTree 运行：按任务书，等 Codex 正式映射后统一刷新。

## 6. 变异核对（只在样本项目的副本里破坏；每个场景一个关键变异，只对照直接相关的已有测试）

| 变异（副本） | 新文件 | 直接相关的已有测试 |
|---|---|---|
| SAV：重进沿用旧数据（静态缓存，不重新 GET） | 4 过 / **2 失败** | `savings_controller_test` 18/**5 失败**、`savings_closed_loop_test` 19/**4 失败**（该变异会破坏它们的假仓储，区分度不高；已有测试里本来就没有任何"页面重进"用例） |
| TASK-A：`loadData` 不再刷新个人资料 | 4 过 / **2 失败** | `tasks_controller_test` 35/0、`task_vertical_slice_test` 15/0：**全部漏过** |
| TASK-B：历史只返回最后一版提交 | 5 过 / **1 失败** | `task_history_followup_test` 3/0、`family_tasks_closed_loop_test` 12/0：**漏过** |
| TASK-B：B 余额显示在错误的发行人名下 | 5 过 / **1 失败** | `family_tasks_closed_loop_test` 12/0、`tasks_approval_and_progress_test` 6/0：**漏过** |

副本改动已还原并逐文件比较确认；原仓库源码未被触碰。

## 7. 源码完整性

Life-Piggy-Bank：HEAD `ed81f99` 不变；`git diff` 为空（没有任何已跟踪文件被改）；`git status --short` 为 `?? .flowtree/` 与 `?? test/page_reentry_and_review_wire_test.dart`。变异实验与调试用的临时文件都在 scratchpad 副本里，仓库内没有遗留的 `zz_debug` 文件。

## 8. 遗留与注意

1. **新增文件会改变样本项目的仓库指纹**：此前所有 FlowTree 证据（含 Codex 刚建立的 51 项那一批）将变为"待更新"，需要在 Codex 正式映射后统一重跑；这是设计行为。
2. **未知结果期间离页后的待确认请求**不在本批：见 `Q-SAV-NAV-001`，不是已确认缺陷，不阻塞这些成功后重进测试，也没有为此写预期行为的测试。
3. 假服务端是测试替身：只验证客户端与 HTTP 契约的交互；真实服务端的审批/积分记账语义由后端测试覆盖。"离开再进入"是同一进程内页面销毁重建，不等于杀进程后的冷启动恢复。
4. 测试依赖已有的 `AuthService.customClient` 注入点与 `HomeShell` 的 AppBar 入口/Chip 文案；这些 UI 文案（如"✓ 已完成""审批中"）变更会使本文件需要同步，故状态文案用 `textContaining`。
5. TASK-B 的 B 余额是通过"切到商城 tab 触发 `refreshProfile`"看到的——这是现有导航里更新余额的路径之一；任务页重进（`loadData`）同样会刷新个人资料。
6. 规则确认与人工验收仍未完成；自动测试通过不等于验收。
