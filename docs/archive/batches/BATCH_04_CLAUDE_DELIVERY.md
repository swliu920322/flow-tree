# 第四批交付记录（Claude）：Flutter 已有测试接入

日期：2026-11-10。任务书：`docs/BATCH_04_CLAUDE_TASK_2026-11-10.md`。基线 HEAD `eabda3a`，本批改动**未提交**。不修改 `examples/`、`tests/independent/`、`docs/flowchart.mermaid`；样本项目的五项真实客户端映射留给 Codex。

## 1. 设计变化

新增 `flowtree/runners/` 包，把"命令、参数/标识校验、运行时探测、机器报告解析"收进 runner 适配器；公共执行器（attempt、超时、进程组清理、前后基线、落盘、索引）不变，只通过 runner 接口调用。`PytestRunner` 是原有 pytest 逻辑的原样搬迁（`mapping.py` 中的 pytest 校验、`execution.py` 中的解释器/命令/分类/运行时），**pytest 语义不变**（87 项真实子进程 pytest 回归在重构后通过）。`FlutterRunner` 是新增。`mapping.runner` 现在可取 `pytest` 或 `flutter`；映射 schema 未变。

## 2. 精确标识与命令样例

映射条目（`runner: flutter`）：

```yaml
- id: M-FLUTTER-TOCTOU
  covers: [SAV-001.CASE-02]
  level: client
  runner: flutter
  cwd: "."
  argv: [flutter, test, test/savings_controller_test.dart]     # 只能是: flutter test <相对的 *_test.dart 文件>...
  tests:
    - nodeid: "test/savings_controller_test.dart::Task 19 Phase C: SavingsController 单元测试 5. TOCTOU idempotent replay: 网络超时失败后修改输入，必须使用原 Key 与原 payload 重放"
      match: exact
  env: {id: life-piggy-bank-flutter-isolated}
  timeout_s: 900
```

- **标识** = `<相对 cwd 的文件>::<带分组前缀的完整测试名>`，**只按第一个 `::` 分隔**，其余字符属于原始名称（含 `::` 的名称有测试）。完整名称取自事件流里的 `test.name`（已含全部 group 前缀）。不同文件允许同名；**同文件存在多个同名真实测试**时，被映射的那一项判 `error`（`ambiguous`），不猜、不只取一项，同文件其他被映射的测试不受影响。运行内的数字 ID 只用于关联事件。
- **argv 是白名单**：必须是 `[flutter, test, <文件>...]`；任何以 `-` 开头的选项（筛选、分片、重试、报告器、提前停止、`--no-pub` 等）、目录、通配、绝对路径、`..`、非 `_test.dart` 文件一律拒绝（`mapping.argv_option_not_allowed` / `mapping.argv_flutter_path` / `mapping.argv_not_flutter`）；被映射的测试所在文件必须在 argv 里（`mapping.test_file_not_in_argv`）。不依赖不完整的黑名单；48 项映射校验测试，含 26 个被拒选项。
- **runner 实际执行的命令**（独占注入）：`<flutter> --no-version-check --suppress-analytics test --no-pub --reporter json --file-reporter expanded:<本次 attempt 目录>/flutter-human.txt <文件...>`。`--no-pub` 避免运行中改动 `pubspec.lock`；映射无法覆盖报告器/报告路径。
- 命令/CLI：与 pytest 完全相同，`flowtree verify …`、`flowtree workspace verify <id> --entry STORY/ENTRY`。

## 3. 证据类型与判定规则（如实声明）

**证据类型：单一机器来源**——`flutter test --reporter json` 事件流（package:test 协议 `0.1.1`），由本次 attempt 子进程的 stdout 直接捕获为 `events.jsonl`。**没有 JUnit 式的独立第二来源，也不伪造。** 人读 expanded 日志只作原始附件（`flutter-human.txt`），**不参与任何判定**，不看其末行 `+N ~M -K`。manifest 与页面都显示该证据类型。判定依据：事件 ID 关联与状态一致性、会话终态 `done.success`、进程退出码。

`flowtree/runners/flutter_runner.py:analyze` 的规则（任何无法解释的矛盾都归为 `error`，不会因 exit 0 或"有一个通过"而通过）：

| 检查 | 结论 |
|---|---|
| 非 `{` 开头的行 | 噪声，计数并保留；`{` 开头却无法解析 → 报告损坏/截断 → error |
| 首事件非 `start` / 协议版本不是 `0.1.1` | error |
| 缺 `done`、`done` 不唯一或不是最后一个、**`done.success` 为 null/非布尔** | error（提前关闭，不是结果） |
| `allSuites.count` 与 suite 事件数不符；suite 路径在工作目录之外（旧报告/串用） | error |
| 重复 suite/test ID、`testDone` 无对应 `testStart`、重复 `testDone`、`testStart` 无 `testDone`、`error` 事件指向未知测试 | error |
| `result` 非 success 却没有 `error` 事件；success 却带 `error` 事件；既 skipped 又失败 | error（报告内部不一致） |
| **`result=success` 但 `skipped=true`（或 metadata.skip）** | **skipped → `not_run`**，先检查 skipped 再看 result |
| **加载伪测试**（名称 == `loading <该 suite 路径>`，**按身份识别，与 `hidden` 标记无关**）失败，或任何 hidden 测试失败 | 整个 attempt error（`load/setup failure …`，保留原始 error 文本）；成功的加载伪测试不进入业务测试分母，原始事实保留在 manifest `hidden_events` |
| 进程退出码不在 {0,1}；`done.success=true` 却有失败/非 0 退出码；`done.success=false` 却无失败 | error（矛盾） |
| 零个真实测试 | error |
| `failure`（断言失败） / `error`（测试体异常） / `success` | `failed` / `error` / `passed`；原始 `error` 与 `stackTrace` 保留在逐项详情 |
| 映射声明的测试不在本次事件流里 | `missing` → `error` |
| 映射外的失败 | 记入 `unmapped_nonpass`，使命令级失败（`verify` 非零），不因映射场景通过而成功 |
| `print` 事件 | 仅日志，不是结果 |

**实际踩到的事实**：真实 Flutter 3.38 里，**加载/编译失败时加载伪测试的 `testDone.hidden` 是 `false`**（成功时才是 `true`）。只看 `hidden` 标记会把编译失败当成一个普通 error 测试并让 attempt 显示 `completed`。首次真实编译失败测试就暴露了它，已改为按名称身份识别（解析器单元测试 `test_real_flutter_shape_load_failure_…` 固化，并有测试保证用户测试不会被误认为加载伪测试）。

**范围的局限**（沿用任务书）：Flutter 没有 pytest 式的完整收集集合，本批只证明"显式映射的 exact 测试在本次事件流中实际执行"；不声称参数化完整，也不声称整文件场景穷尽。

## 4. 运行时、环境与只读

- **运行时摘要只读文件**，不调用任何会建缓存/锁文件或联网的 flutter 命令：`<SDK>/bin/cache/flutter.version.json`（框架版本与修订、引擎修订、Dart 版本）、`bin/cache/dart-sdk/version`、`bin/internal/engine.version`、flutter 可执行文件的真实路径、`pubspec.lock` 与 `.dart_tool/package_config.json` 的 SHA-256。CLI 重检与 Web 重检调用同一个函数（`read_runtime`）。执行前后各取一次，变化即"运行中变化"→ 有效性 unknown。
- **前置缺失一律阻塞，不引导、不联网**：SDK 事实文件不可读（SDK 未初始化，FlowTree 不会 bootstrap）、`pubspec.lock` 或 `package_config.json` 缺失（FlowTree 绝不运行 `pub get`）、`package_config` 指向的依赖缓存目录缺失、找不到 flutter 可执行文件、**上下文里没有 `HOME`**。重检时这些情况得到 `unknown`（环境前置缺失的尝试保持显示为 `blocked`，不回退到更早的通过）。
- **`HOME` 要求是实测得出的**：不带 `HOME` 时 flutter 把 `.config/flutter/tool_state` 和 `.flutter` 写进**工作目录**（污染被测项目）；原有的"运行期间工作区变化"守卫当时已把结果判为 unknown，现在改为执行前就明确阻塞，并有测试断言项目快照前后相同。
- **pinned 模式**：`env_from_host: [HOME]`，`pinned_path` 放入 flutter 的 bin 目录（让映射里的 `flutter` 解析到固定 SDK），沿用第三批的上下文与 `context_digest`；配置示例见 `config/workspaces.example.yaml`（`life-piggy-bank-flutter`）。
- **局限（明确声明）**：pub cache 里依赖包**源码的完整内容不做校验**——只绑定 `package_config` 记录的包/版本/路径与目录存在；不声称任意缓存篡改都会使证据失效。FlowTree 无法沙箱网络，只是避开已知触发（`--no-pub`、`--no-version-check`、`--suppress-analytics`）。
- **只读重检**：测试以 monkeypatch 拦截所有 `subprocess` 调用，断言重检**从未调用 `flutter`/`dart`**，并断言读取前后被测项目所有文件的哈希、SDK `bin/cache` 与 `bin/internal` 下所有文件的 (大小, mtime)、`lockfile` 是否存在、`.flowtree` 文件集合均不变。

## 5. 页面（只读）

证据详情新增：运行器与证据类型、事件协议版本、真实测试数、`done.success`、隐藏事件数、测试文件、Flutter/Dart 版本与引擎修订、包数量与"缓存源码未做内容校验"的说明；产物 `events`/`human`/`stderr` 可读取，读取时复核 SHA-256（被改动则 409）。仍无任何执行、重检或签字入口。

## 6. 实际验证（单批计数，不相加）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/implementation -q -p no:cacheprovider` | **407 passed**，0 skipped，0 failed（约 510 秒；含 18 项真实 `flutter test` 子进程测试，本机 Flutter 3.38.3 实际执行）。此前 315 项（B1–B3，断言未改动，仅把我自己用 `flutter` 当"不支持 runner"示例的一条测试改为 `jest`）+ 本批新增 92 项 |
| `.venv/bin/python -m pytest tests/independent -q -p no:cacheprovider`（Codex，未改动） | **47 passed**，0 skipped，0 failed |

说明：若验收环境没有 Flutter SDK，`test_flutter_real.py` 整组会明确跳过（reason 写明"Flutter runner NOT verified"），不能记为通过；若禁止回环端口，Chrome 渲染测试同理需在允许的环境补跑。

新增 3 个测试文件：
- `test_flutter_parser.py`（26，纯函数）：通过；断言失败带原始 error/stackTrace 与测试体异常分开；`success+skipped`、metadata skip；映射外失败；名称含 `::`；不同文件同名允许/同文件同名 ambiguous；**交错事件**与 print；噪声行与损坏 JSON；截断、`done.success=null`、协议版本、done 重复、allSuites 不符、suite 在工作目录外（旧报告/串用）、缺 `testDone`；退出码矛盾与 79；加载失败（含真实 hidden=false 形态）；零真实测试与映射缺失；result 与 error 事件不一致；重复/未知 ID；用户测试不被误认为加载伪测试。
- `test_flutter_mapping.py`（48）：白名单、26 个选项、路径/glob/绝对/`..`、argv 形态、标识精确性、跨 runner 校验互不适用。
- `test_flutter_real.py`（18，**真实 `flutter test` 子进程 + 真实 git 仓库**；无 Flutter 时整组明确跳过并说明原因）：两个测试文件并发运行（交错事件）且证据完整；断言失败；测试体异常；skip；**真实编译错误**；同文件同名；名称含 `::`；映射外失败使命令失败；映射的测试不存在；**超时终止整棵 flutter 进程树**（用 `Timeout.none` 避开 Dart 自带的 30 秒超时）；`package_config` 缺失→阻塞且不 `pub get`、项目快照不变；依赖缓存缺失→阻塞；flutter 缺失/SDK 未初始化→阻塞；**`.dart_tool`（被 git 忽略）被改动→运行时 stale 而工作区一致**；源码改动→stale 且历史保留；**只读重检不调用 flutter/dart 且 SDK/项目不变**；pinned 下两个宿主重检 current、缺 `HOME` 阻塞且项目不变；Web 显示 flutter 证据、产物读取与篡改→409。

变异核对：去掉 `skipped` 检查、去掉加载伪测试的身份识别、放过 `done.success=null` 后 4 项解析器测试失败；还原后通过。pytest 回归：重构后 `test_b1b_execution`、`test_b1b_fixes`、`test_b3_context` 共 87 项真实子进程测试通过。

## 7. 真实项目：Life-Piggy-Bank 的 Flutter 测试（可行性，非正式映射）

只使用样本现有工具链与缓存（Flutter 3.38.3 / Dart 3.10.1，既有 `.dart_tool`），未 `pub get`、未升级、未联网、未改业务源码或夹具，不部署、不碰真实库。先用与 pinned 一致的最小环境直接跑 `test/savings_controller_test.dart`（事件流写到 scratchpad、`--no-pub`）：约 3 秒，24 个测试（1 个加载伪测试 + 23 个真实测试）全成功，`git status` 不变。再用**临时映射**（放在 scratchpad，不入库，不在 `examples/`）经 FlowTree 在 pinned 上下文真实执行 SAV-001.CASE-02 对应的 `5. TOCTOU idempotent replay…` 测试：

- run `run_20261110T112758_a882bb22`，`SAV-001/M-FLUTTER-TOCTOU` completed、exit 0、**23 passed**（整文件都被执行，命令干净）、`context_problems=[]`。
- **不同宿主下重检**（`workspace status`）：当前 shell 与 `env -i` 加无关变量两个宿主均 `current / passed`；宿主缺 `HOME` 时 `unknown`（`not_run`，不退回宿主环境）。
- 目标项目：HEAD `a4cc0a0…` 不变；源文件（tracked + 非忽略 untracked，不含 `.flowtree/`）哈希前后一致；`git status` 仍只有原有 `?? .flowtree/`（新增的是本次 run 的证据目录）。
- 证据：`<LPB>/.flowtree/runs/run_20261110T112758_a882bb22/SAV-001/M-FLUTTER-TOCTOU/{events.jsonl,flutter-human.txt,manifest.json,stderr.txt}`（该证据只在本机的 `life-piggy-bank-flutter-pinned` 工作区可见，现有 `life-piggy-bank` 工作区看不到；是否把 CASE-02 正式映射到该测试、断言是否足以支撑，由 Codex 判断）。

## 8. 给 Codex 整理五项真实映射时的提示

- 五项（SAV-001.STEP-01/02/CASE-02、TASK-A-001.STEP-01、TASK-B-001.STEP-01）的候选测试线索见第二批交付第 7 节。真实完整名称需从事件流取得，不是 `test(...)` 里的字面量（带分组前缀，例如 `Task 19 Phase C: SavingsController 单元测试 5. …`）；可用 `flutter test --no-pub --reporter json <文件>` 读 `testStart.test.name`。
- 一个文件里的所有测试会一起执行（整文件 23 个），其中任何一个失败会使命令失败；映射同一文件内多个测试时应放在同一条目或使用相同 argv。
- 样本的 Flutter 应用在仓库根（`pubspec.yaml` 在根），映射 `cwd` 用 `.`（其 pytest 映射 `cwd` 是 `backend`，两者不同）。
- 需要 pinned 上下文并声明 `HOME`；`pinned_path` 要包含 flutter 的 bin 目录。

## 9. 遗留

1. 单一机器来源：事件流没有独立的第二来源可交叉校验（已如实声明）；协议版本只支持 `0.1.1`，其他版本明确 error，需要时再扩。
2. 依赖缓存源码内容未校验；FlutterRunner 不沙箱网络。
3. 项目内的 `dart_test.yaml`/`flutter_test_config.dart` 能影响测试（标签、重试、超时、全局初始化）：它们在工作区指纹里，改动会使证据失效；但其"实际生效的配置"不像 pytest 插件那样被上报，范围只由"事件流里映射的 exact 测试确实执行成功"证明。
4. 超时上限仍是 3600 秒，未改。页面与 Web 仍只读，`human` 恒未验收、`rule` 恒草稿。
5. 本批改动与本机 `.flowtree/workspaces.yaml`（含新增的 `life-piggy-bank-flutter-pinned`）均未提交。

## 10. Codex 独立验收 B4-01：协议生命周期与字段校验

依据 `docs/BATCH_04_INDEPENDENT_REVIEW.md`。三个反例属实：`testDone` 先于 `testStart`、重复会话 `start`、缺字段的 `error` 事件，原实现都判 completed/passed。原因：`analyze` 分多轮扫描收集 `testStart`/`testDone`/`error` 再配对，丢失了事件先后约束；`error` 字段不完整时被当作"没有这条事件"。

**修复**（`flowtree/runners/flutter_runner.py:analyze`）：改为**单次顺序遍历**，维护会话与每个测试 ID 的生命周期，不同测试仍可任意交错：
- 首事件必须是 `start` 且唯一；之后任何 `start`（含完整拼接的第二个会话）→ error。`done` 必须唯一且是最后一个，其后的任何事件 → error。
- `testStart`：`id`、`name`(str)、`suiteID` 必填，suite 必须**已在此前出现**，ID 不得重复。`testDone` 只能结束**已开始且未结束**的测试（先于 start、未知、重复 → error）。
- `error` 事件：`testID`、`error`(str)、`isFailure`(bool) 必填，`stackTrace` 若存在必须是字符串；测试必须已开始且**尚未 testDone**（在 testDone 之后到达的 error → error，属于乱序）。缺字段/类型错误 → `malformed error event`，**原始事件保留**在 manifest `malformed_events`，不被静默丢弃。同样校验 `suite`(id/path)、`testDone`(testID/result/`skipped`、`hidden` 为布尔)、`allSuites`(整数 count)。
- 既有语义不变：success+skip、加载伪测试（含 `hidden=false` 的真实形态）、同文件重名、含 `::` 的名称、交错事件、映射外失败。

取舍（如实）：`stackTrace` 字段不强制存在（协议文档列出但不作为判定关键字段，存在则校验类型）；`error` 事件晚于 `testDone` 一律按乱序 error 处理——对真实 Flutter 流量这是安全方向（只会多报 error，不会放过），若将来发现合法的迟到错误，需要另行评估而不是放宽校验。

**回归**（`test_flutter_parser.py` 新增 19 项，与 Codex 反例构造不同）：testDone 先于 testStart（总数与配对都完整的交换）；第二个 start 出现在三个不同位置及两个完整会话拼接；`error` 缺 `testID`/`error`/`isFailure` 逐一 + 8 种类型错误/缺字段的 testStart/testDone/suite/allSuites/error；error 晚于 testDone 或指向未开始测试；done 之后的事件；**正常交错仍通过而同样事件把 done 排到 start 之前则 error**。变异核对：撤销这三项检查后 Codex 的 3 个反例与我的 10 项回归共 13 项失败；还原后通过。并已用新校验器重放样本项目的**真实**事件流（55 个事件、23 个真实测试）：仍为 completed/23 passed。

### 10.1 验证（单批计数，不相加）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/implementation/test_flutter_real.py tests/implementation/test_flutter_mapping.py tests/implementation/test_flutter_parser.py -q` | **111 passed**，0 skipped，0 failed（约 183 秒）：真实 `flutter test` 18 + 映射校验 48 + 解析器 45（26 + 本轮新增 19） |
| `.venv/bin/python -m pytest tests/independent -q`（Codex，未改动） | **53 passed**，0 skipped，0 failed（含 B4-01 的 3 个反例与其余 3 个正向控制） |

只改了 `flutter_runner.py` 与 Flutter 相关测试：pytest 路径、公共执行器、页面均未变，因此**未重跑**其余 315 项实现测试（上一次完整结果为 407 passed，其中 315 项不涉及本次改动）。真实 `flutter test` 子进程测试在新校验下全部通过，说明真实事件流未被误伤。

## 11. 样本项目客户端测试补强（STEP-01/02 与 CASE-02 的断言不足）

Codex 复验后只接入了三项客户端映射，另两项（弹窗：编辑分类/金额/备注并检查实际提交参数；重放：改了输入后实际发送的 Key 与完整载荷仍为原值）因候选断言不足而保持未映射，交给我补强测试。**不改故事要求、不改业务源码、不改已有测试与夹具。**

### 11.1 做了什么

在 Life-Piggy-Bank **新增一个测试文件**（唯一的写入）：`test/savings_submission_wire_test.dart`。它用真实的 `HttpSavingsRepository` + 拦截 `http.Client`，在页面里真实编辑分类/金额/备注，然后检查**实际发出的每个 HTTP 请求**的 `Idempotency-Key` 头与完整 JSON 请求体（逐字节比较）。6 个测试，真实 `flutter test` 全部通过：

| 完整测试名（`test/savings_submission_wire_test.dart::` 之后） | 证明了什么 |
|---|---|
| `克制记录弹窗: 编辑分类/金额/备注并检查实际提交的请求 STEP-01/02 弹窗提供分类、金额、备注三项输入, 编辑后提交的 HTTP 请求逐字段等于所填内容且带非空 Idempotency-Key` | 弹窗有 ≥3 个分类、金额（默认 15）、备注（空，且标签来自本地化文案）；编辑后只发出 1 个 POST，路径、鉴权头、非空 Key、请求体**精确等于** `{action, category, amount, note}`（无多余字段、无默认值混入） |
| `克制记录弹窗: 编辑分类/金额/备注并检查实际提交的请求 两次独立提交使用两个不同的 Key, 各自请求体是各自所填内容` | 独立提交使用不同 Key，各自载荷是各自所填 |
| `CASE-02 未知结果期间修改输入后再次提交: 重放的必须是原 Key 与原完整载荷 改了分类+金额+备注: 第二次实际请求与第一次逐字节相同, 修改后的值从未出现在任何请求里; 随后的新意图才使用新 Key 与新载荷` | 首次连接中断→用户把**三项都改了**再提交：第二个请求的 Key 与请求体与第一个**逐字节相同**，修改后的值在任何请求的体或头里都不出现；原请求确认后，新意图才用新 Key 和新的完整载荷 |
| `CASE-02 … 重放仍然失败: 仍保持原 Key 与原载荷, 反复修改输入再提交也只会重放原请求 (修改值始终不被发送)` | 重放持续失败、反复改输入，4 次请求始终是原 Key + 原载荷 |
| `CASE-02 … 只修改金额(分类与备注不变)也必须重放原载荷, 不能把新金额当作原请求` | 只改金额的情形 |
| `CASE-02 … 原请求被服务端确定性驳回(4xx)后, 待确认请求被清除, 用户的修改才作为新意图以新 Key 发出` | 4xx 之后不再重放，修改作为新意图 |

（完整测试名里"CASE-02 … "之后的部分是上表省略号处的原文；精确列表已导出为 JSON，位于本机 scratchpad `lpbfl/wire-ids.json`，Codex 也可用 `flutter test --no-pub --reporter json <文件>` 的 `testStart.test.name` 取得。）

### 11.2 为什么这样补（缺口是实测的，不是推测）

在样本项目的**副本**里（原仓库源码不动）对控制器的重放分支做 5 种破坏，分别运行已有的两个文件与新文件：

| 破坏 | 已有 `savings_closed_loop_test` | 已有 `savings_controller_test` | 新文件 |
|---|---|---|---|
| M1 重放用了新 Key | 抓到 | 抓到 | 抓到 |
| M2 重放发了修改后的**分类** | 抓到 | **漏过** | 抓到 |
| M3 重放发了修改后的**金额** | **漏过** | **漏过** | 抓到 |
| M4 重放丢了**备注** | **漏过** | 抓到 | 抓到 |
| M5 重放发了修改后的**备注** | **漏过** | 抓到 | 抓到 |

所以已有两个文件合起来**无法发现"重放发了修改后的金额"**；widget 层（页面→仓储）看不出备注被改；且没有任何一个断言过真实 HTTP 字节（已有 widget 测试只记录 `last*` 字段与 Key 列表，且重放用例只改了分类）。新文件在未破坏时 6/6 通过，5 种破坏下分别 3/6、2/6、3/6、3/6、2/6 失败。这印证了 Codex 对"断言不足"的判断。

### 11.3 局限与注意（如实）

- 新测试验证的是**客户端实际发出的请求**（拦截 `http.Client`），不是真实服务端；服务端侧的幂等行为（同 Key 同载荷重放、载荷不一致返回 409）由样本的后端测试覆盖，不在这里证明。
- "STEP-01 打开弹窗可填写分类、金额和备注"现在有三项输入存在与可编辑并流入请求的断言；"STEP-02 保留唯一 Key 与原输入"由第 1、2、3 个测试共同支撑。是否足以正式映射由 Codex 判断。
- **新增文件会使样本项目此前所有 FlowTree 证据变为"待更新"**：工作区指纹覆盖整个仓库的已跟踪与未跟踪（非忽略）文件，新增一个测试文件就改变了指纹。这是设计行为，不是缺陷，但意味着 Codex 刚接入的映射（含那三个文件的 40 项与此前的 pytest 条目）需要**重新执行**才会重新有效。我的临时映射实测：`SAV-001.CASE-02` 同时被两个条目覆盖，较早的一条已 stale，因此该单元整体显示"未执行"。
- 该文件目前是 Life-Piggy-Bank 里**未提交的未跟踪文件**；我没有在样本仓库做任何提交、暂存或其他改动。是否保留/提交/移动位置由用户决定。

### 11.4 真实执行

用临时映射（scratchpad，不入库）经 FlowTree 在 pinned 上下文真实执行：run `run_20261110T120542_e7d1bc54`，`SAV-001/M-WIRE` completed、exit 0、**6 passed**、命令干净；`SAV-001.STEP-01`、`SAV-001.STEP-02` 在当前宿主与 `env -i` 加无关变量的另一宿主下重检均 `passed / current`。样本项目除新增的那个测试文件外，源文件哈希前后一致，HEAD `a4cc0a0…` 不变；`git status` 为 `?? .flowtree/` 与 `?? test/savings_submission_wire_test.dart`。副本与破坏实验都在 scratchpad，已不影响原仓库。
