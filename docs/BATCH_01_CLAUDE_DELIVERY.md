# 第一批交付记录（Claude）：B1a 故事契约与结果真实性 + F01–F05 修复 + B1b 真实 pytest 执行

日期：2026-11-10。范围：B1a（第 1–7 节）、Codex 第一轮审查 F01–F05 的修复（第 8 节）、B1b（第 9–11 节）。第 1–7 节描述 B1a 交付时的状态；其中与 B1b 冲突处以第 9 节为准（`Baseline` 增加两个字段，`--rootdir` 不再禁用，`flowtree verify` 已存在）。

## 1. 基线与环境

- 基线：HEAD `e299cc355ca299a79387261d5b1128b8f44d2a17`，工作区为 dirty（本批全部改动未提交）。未跟踪的 `docs/flowchart.mermaid`、`docs/BATCH_01_CODEX_CLAUDE_2026-11-10.md` 为用户/Codex 文件，未改动。
- 环境：项目内 `.venv`（`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`），未改全局 Python。Python 3.13.7；pydantic 2.14.3、PyYAML 6.0.3、pytest 9.2.0、fastapi 0.162.2、starlette 1.10.0、httpx 0.28.1。依赖唯一主清单为 `requirements.txt`，未建 pyproject。
- 未做：未运行 Life-Piggy-Bank 任何测试/部署，未接收费 API，未碰真实库，未改前端、静态页和演示 JSON。

## 2. 实际验证

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/implementation -q` | 119 passed，0 skipped，0 failed（89 个第三方弃用警告，来自既有 `datetime.utcnow()` 与 starlette，未处理） |
| 变异核对：把 `backend/app/main.py`、`cli/generator.py`、`cli/storage.py` 暂时还原为 HEAD 版本后运行 `test_backend_signoff.py`、`test_cli_and_legacy.py` | 7 failed / 12 passed，说明去伪成功、签字拦截、空结果与迁移测试在旧代码上确实失败；还原后重跑 119 passed |
| `.venv/bin/python -m cli.main story plan tests/implementation/fixtures/sav-001.story.yaml --mappings tests/implementation/fixtures/sav-001.mapping.yaml` | exit 0；6 个单元：3 个未映射、3 个已映射未执行，输出"未执行任何测试" |

这些是单批计数，仅覆盖 B1a 的校验/聚合/CLI/旧路径/PATCH；不含任何真实业务测试的执行结果。

## 3. B1a 冻结的接口

### 3.1 模块与入口

```
flowtree/canon.py    严格 YAML 读取（拒绝重复键，时间戳保持字符串）+ 内容摘要
flowtree/story.py    故事模型、校验、StorySet
flowtree/mapping.py  测试映射模型与校验
flowtree/status.py   四维状态、有效性、聚合、汇总
flowtree/service.py  validate() / plan()，CLI 与 MCP 共用
```

```
flowtree story validate <文件|目录>... [--mappings <文件|目录>...] [--json]
flowtree story plan     <文件|目录>... [--mappings <文件|目录>...] [--json]
```

MCP 工具类：`tool_story_validate(stories, mappings)`、`tool_story_plan(stories, mappings)`（只有工具函数，协议收发循环仍未实现）。

退出码：`validate` 格式与引用有效→0（待确认问题只报告），有 error→1；`plan` 成功生成→0（未映射只列出），输入有 error→1；`status` 成功展示→0；`run`/`watch`（旧入口）→1；用法错误→2。`verify` 的退出码规则在 B1b 按"必需范围未通过或未完整执行→非零"实现。

`--json` 的 issue 结构：`{severity: error|warning, code, where, message}`，`code` 为稳定机器码（如 `story.duplicate_id`、`mapping.match_unsupported`）。

### 3.2 故事（schema_version "0.1"，兼容原规范格式）

字段沿用规范；未知字段报错。可验证单元 = 主流程步骤（STEP）+ 分支场景（CASE），限定 ID 如 `SAV-001.CASE-02`。

- ID：`^[A-Za-z][A-Za-z0-9_-]*$`（不含 `.`）；step 与 branch 共用一个命名空间，故事内唯一；故事 ID 在整个读取集合内唯一。
- 分支：`at` 必须是存在的步骤；`end` 不得带 target；`rejoin` 必须有 target，且必须是 `at` **之后**的主流程步骤（回到更早/同一步骤是 retry）；`retry` 明确拒绝（`story.retry_unsupported`），不会当作 `end`。
- `open_questions`：结构化 `[{id, text, blocks: [STEP-xx|CASE-xx|"*"]}]`，`blocks` 必须引用存在的单元。旧字符串条目仍可读，转为 `OQ-LEGACY-nn`，`blocks=["*"]`（保守阻塞整个故事）并给出 warning。
- `inputs`：原格式 `amount: "0.25"` 照常读取，**未声明类型的输入不做类型校验，输出里列入 `untyped_inputs`**。可选类型声明：`{type: decimal, value: "0.25", max_scale: 2}`（`decimal` 必须是普通十进制字符串，不接受指数/浮点）、`integer`、`string`；含 `type` 键但类型未知时报错。裸浮点给 warning。
- `clock`（可选）：`{now: "2026-01-01T09:30:00", tz: "Asia/Shanghai"}`；`now` 必须是不带偏移的本地时间，`tz` 必须是有效 IANA 时区；夏令时重叠（歧义）和跳变（不存在）的本地时间均报错。
- `digest`（可选）：若文件里写了，必须等于计算值。

### 3.3 摘要算法（故事与映射共用）

对**解析后的数据**确定性序列化后取 SHA-256，格式 `sha256:<hex>`：排除顶层 `digest`；字典按键排序；**列表保持原顺序（顺序变化即内容变化）**；字符串 NFC 规范化；类型差异保留（`1` ≠ `"1"`）；JSON 紧凑分隔、`ensure_ascii=False`。注释、缩进、引号风格、键顺序不影响摘要。映射的每个条目另有 `entry_digest`（含所属故事 ID 与条目全部字段）。

### 3.4 映射（独立文件，schema_version "0.1"）

示例见 `tests/implementation/fixtures/sav-001.mapping.yaml`。

- 顶层：`story`、可选 `story_digest`（钉住所审阅的故事版本；与当前不一致→**error** `mapping.story_changed`；缺失→warning `mapping.unpinned`）、`entries`。
- 条目：`id`、`covers`（必须是**本映射所属故事**的限定 ID；跨故事暂不支持，需另写映射）、`level`（`code_review|backend|client|e2e`）、`runner`（目前只有 `pytest`）、`cwd`、`argv`、`tests`、`env.id`（必填）、`timeout_s`（默认 600）。
- `tests` 每项必须是 `{nodeid, match}`；裸字符串、缺 `match` 均报错。`match: exact` 为精确 pytest nodeid（可含具体参数实例，如 `test_a[1]`）；**`match: parametrized` 在 B1a 明确拒绝**（`mapping.match_unsupported`），nodeid 不得含通配符、绝对路径或越出 rootdir。
- `argv` 必须是 pytest 调用；含 `-k/-m/-x/-p/--deselect/--lf/--maxfail/--junitxml/--collect-only` 等改变收集范围或与注入报告冲突的选项一律拒绝。该黑名单不穷尽（如合并短选项 `-vx`），B1b 以"实际收集/执行证据"为最终依据，不依赖它。
- `cwd` 的解析基准在 B1b 定为 `--project-dir`（缺省为映射文件所在目录）；绝对路径给 warning。

### 3.5 状态与聚合

四个维度分开：`rule`（B1a 只有 `draft`/`pending`，**没有确认记录机制，因此不会出现 confirmed**）、`implementation`（恒 `unchecked`）、`automation`、`human`（`none|pass|reject|na`，执行器没有任何写 `human` 的代码路径）。

`automation` 取值：`unmapped | not_run | running | passed | failed | blocked | error`。**证据有效性（`current|stale|unknown`）是另一个维度**，先判有效性、再聚合有效结果：

1. 有效性：证据绑定的 `story_digest`、`entry_digest`、`env_id`、`worktree_fingerprint` 任一不同→`stale`；其余相同但任一方指纹无法确认→`unknown`；`git_sha` 与 `mapping_digest` 仅溯源，不参与（内容相同的不同提交仍有效；映射中其他条目的改动不使本条目失效）。`worktree_fingerprint` 由 B1b 计算：已跟踪与未跟踪（非忽略）文件内容的哈希，因此能识别影响测试的未跟踪源码。
2. 非 `current` 的证据：`result` 保留为历史，但对本次贡献 `not_run`（`contributes_current=None`）；历史通过/失败都不冒充当前结果。
3. 测试结果→状态：`passed→passed`；`failed→failed`；`error→error`；`skipped→not_run`；`xfailed→failed`（登记的已知缺陷，预期行为未交付）；`xpassed→error`（已登记缺陷意外通过，需复核，不据此判通过）；报告中不存在该 nodeid→`error`（未知标识/未收集）。
4. 尝试状态：`running→running`；`blocked→blocked`；`error|aborted→error`；仅 `completed` 才看逐测试结果，且映射声明的**每个** nodeid 都须 passed 才得 `passed`（只见到一个通过的实例不推断其余）。空 `tests` 不得通过。
5. 合并优先级（只对有效结果）：`failed > error > blocked > running > not_run`，全 passed 才 `passed`；一个单元被多个条目覆盖时同样合并，无条目→`unmapped`。
6. 汇总只给分母和分类计数，不给百分比；`complete` 须同时满足全部单元本次通过、规则无 pending 且已确认、人工 pass/na——B1a 因无规则确认记录，`complete` 恒为 `false` 并列出原因。

## 4. 产品路径上去伪成功（实际改动）

- `cli/generator.py`：删除两套含 `passed = True` 的脚本生成；模板节点统一 `status=pending_dev`、`review={}`、`actualHours=0`，`circuit.json` 标 `origin: template_unverified`。未向旧 `NodeStatus` 写 `not_run`。模板拓扑本身仍是按项目名选择的固定骨架（非从文档抽取），后续批次再决定去留。
- `cli/runner.py`：不再导入/执行 `.flowtree/tests` 下任何脚本，不改写节点，不写运行记录；`run()` 抛 `VerificationNotConfigured`。`flowtree run` 返回 1，`watch` 暂不可用返回 1。
- `cli/storage.py`：零节点→`NO_EVIDENCE`，非全部通过→`INCOMPLETE`；旧库迁移新增 `evidence_kind`，旧记录一律 `legacy_unverified`。
- `cli/main.py`、`cli/mcp_server.py`：不再声称"内置 Agent 抽取"；`status` 显示旧电路状态分布并标注"非验收证据，不代表通过率"；去掉按项目名硬编码的模块名表。
- `backend/app/main.py`：PATCH `review_pass` 对非演示项目返回 403，演示项目（仓库内置两个）的签字记为 `demo-unauthenticated`；`logicVerifiedBy` 记为 `self-reported:<source>`；`simulate-agent` 限演示项目并返回 `demo: true`。
- `.gitignore` 增加 `.flowtree/`。

## 5. 请 Codex 重点核对的决策

1. **nodeid 可靠性（B1b 方案，需 Codex 同意后冻结）**：JUnit 的 `classname`/`name` 不能无损还原 pytest nodeid，故映射的 `runner` 命名为 `pytest` 而非 `pytest-junit`。B1b 计划由 FlowTree 的单文件、仅标准库的 pytest 插件（`-p` 注入，随 PYTHONPATH 提供）写出 JSON 报告：每个 item 的真实 `nodeid`、各阶段结果，以及本次收集集合与 deselected 列表；JUnit XML 同时生成，作为原始证据和计数交叉校验（两者矛盾→`error`）。这套"本次收集集合"也是日后开放 `parametrized` 的依据。
2. `xfailed→failed`、`xpassed→error`、`skipped→not_run` 的映射（见 3.5）。
3. 有效性比较不含 `git_sha` 与 `mapping_digest`（见 3.5）。
4. 映射的 `story_digest` 钉住不一致为 error（强制重审映射），缺失仅 warning。
5. 映射 `covers` 暂不支持跨故事。

## 6. 遗留与未做

- （B1b 已在第 9 节完成；`/api/projects/sync` 的签字问题已在第 8 节 F01/F02 处理。）
- 前端静态页的"人工终审"按钮仍调用 PATCH，演示项目上保持可用并标注为 unauthenticated。
- 规则确认记录、实现检查来源、人工验收记录尚无存储与入口。
- 旧 `design.md`/PRD 等已加优先级说明（见各文件首部），未改正文。

## 7. 文档优先级

故事、验收证据、最小代码修复，以及"Agent 自报 `logic_verified`/`review_pass` 即点亮"这类冲突条款，以 `STORY_ACCEPTANCE_SPEC.md` 与 `SESSION_HANDOFF_2026-11-10.md` 为准；`design.md`、`PRD.md`、`PROJECT_PROPOSAL.md`、`DATA_CONTRACT.md`、`AGENT_INGESTION_SPEC.md` 的其余内容继续作为现有设计参考。

## 8. Codex 第一轮审查 F01–F05 修复

| 编号 | 修复 | 实现方回归（`tests/implementation/test_review_fixes.py`） |
|---|---|---|
| F01 | `/api/projects/sync` 拒绝（422，列出节点）任何携带 `status=review_pass` 或 `humanSignOff/By/At` 的数据；不是"清理 signer 名称却留着绿灯"。 | 4 种携带方式逐一；干净同步仍 200，同步后 PATCH `review_pass` 仍 403 |
| F02 | 两个内置演示 ID 为保留 ID，sync 返回 409，不能用同名 ID 替换演示内容；PATCH/simulate 共用同一 `DEMO_PROJECT_IDS`。 | 两个保留 ID 同步被拒且演示文件字节不变 |
| F03 | 显式给出的故事/映射目录没有 YAML 文件→稳定 error `story.no_files` / `mapping.no_files`；一个故事都没载入→`story.none_loaded`。"未提供映射"与"提供了却没发现文件"可区分。 | service 与 CLI（exit 1）；空映射目录 |
| F04 | NFC 归一化后键冲突→`YamlLoadError`，不再静默覆盖。 | 嵌套结构、真实 YAML 文件、无冲突正常 |
| F05 | `combine` 对 `UNMAPPED` 有明确位次（低于 `NOT_RUN`），只有全部显式 `PASSED` 才返回 `PASSED`，未知值抛错。 | `passed+unmapped→unmapped` 等 4 种组合 |

同源问题一并修复（审查未列出，我自查发现）：
- `get_project_path` 对未知项目 ID 曾回退到 `life_piggy_bank.json`，导致对任意 ID 的 PATCH（如 `logic_verified`）会把改动**写回演示文件**。现在未知项目 404；项目 ID 必须匹配 `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`（sync 对 `../x` 之类返回 422，避免写出 DATA_DIR）。
- 回归测试 `test_unknown_project_never_falls_back_to_demo_data`、`test_sync_rejects_unsafe_project_ids`。

## 9. B1b：真实 pytest 执行与证据

### 9.1 入口

```
flowtree verify <故事...> --mappings <映射...> --project-root <被测项目根> [--python <解释器>]
                [--mapped-only] [--entry <ID>]... [--json]
flowtree story status <故事...> --mappings <映射...> --project-root <根> [--python <解释器>] [--json]
```

- **project root / 解释器已显式冻结**：映射 `cwd` 相对 `--project-root` 解析（越出根目录→error）；证据写入 `<project-root>/.flowtree/`。映射 `argv[0]` 为 `python*` 时使用 `--python`，未给则按子进程 PATH 解析，找不到→blocked。**永不静默改用 FlowTree 自己的解释器。** `argv[0]` 为 `pytest` 脚本形式时，没有 `--python` 就无法探测运行时，有效性为 unknown。
- `verify` 退出码：必需范围内**每个单元**本次自动验证均 `passed` 且无证据问题→0，否则→1。默认必需范围=所给故事的全部单元（未映射单元使其非零）；`--mapped-only` 只含已映射单元。输入有 error 时不执行（退出 1）。`story status` 成功读取即 0。
- 每个映射条目各一次 attempt，无自动重试、无修复循环。

### 9.2 执行与插件

- `argv` 直接启动子进程（不经 shell），`start_new_session` 独立进程组；超时先 SIGTERM 进程组、5 秒后 SIGKILL，只终止本次拥有的进程组；Ctrl-C 同样终止并留 `aborted` 记录后再抛出。
- 注入 `-p flowtree_pytest_plugin -p no:cacheprovider --junitxml=<本次唯一路径>`；**清除 `PYTEST_ADDOPTS`** 并在 manifest 记录被清除的值。
- 插件 `flowtree/plugin/flowtree_pytest_plugin.py`（仅标准库 + pytest hook，经 PYTHONPATH 加载）写 JSON 报告：run_id/attempt_id、实际 rootdir 与 ini、最终收集集合（含 pytest 自身的 junit classname/name 键）、`deselected`、逐项 setup/call/teardown、收集错误、**生效的范围改变选项**（`-k/-m/--deselect/--lf/-x/--maxfail/--ignore` 等，来自 argv、环境和配置文件 `addopts` 的合并结果）、会话退出码与终态、被测运行时（解释器、全部已安装依赖、pytest 与插件版本）。先写 `terminal=false` 的开始记录，每个阶段增量落盘，会话结束覆盖为终态。
- 因此范围不依赖 argv 黑名单：`pytest.ini` 里的 `addopts = -k zero` 会被插件如实上报，尝试判 error。

### 9.3 分类规则（`flowtree/pytest_report.py`，纯函数）

attempt 状态：
- `blocked`：已知环境前置缺失——cwd 不存在、解释器找不到、解释器探测失败（例如未装 pytest）。
- `error`：插件报告缺失/不可读/schema 不符、run_id 或 attempt_id 不符（旧文件/串用）、无终态、进程退出码与报告 `exitstatus` 矛盾、**pytest rootdir ≠ 映射 cwd**（映射 nodeid 相对 rootdir，基准不一致无法可靠匹配）、范围改变选项生效、收集错误、pytest 退出码非 0/1（含 5 无测试、2 中断）、收集集合为空或有重复 nodeid、会话不完整（缺 setup/call/teardown）、JUnit 缺失/损坏、超时、执行器异常。
- `aborted`：被中断，或 `running` 超过 `timeout_s + 120s` 仍无终态。
- `completed`：以上都通过后才到逐测试结果（测试失败仍是 `completed`，失败记在逐项结果里）。

逐测试（setup/call/teardown 三阶段）→ 结果：setup 失败→`error`；setup 跳过→`skipped`（带 xfail→`xfailed`）；call：passed→`passed`（带 wasxfail→`xpassed`），skipped→`skipped`/`xfailed`，failed→`failed`，若有 xfail 标记且 longrepr 以 `[XPASS(strict)]` 开头→`xpassed`（无标记不能冒充）；**call 通过但 teardown 失败→`error`**；call 失败且 teardown 也失败→仍 `failed`（保留断言失败信息）；缺阶段→`missing`→整次会话 error。聚合沿用 3.5：`xfailed→failed`、`xpassed→error`、`skipped→not_run`、映射声明但不在收集集合（含被剔除）→`error`；原始分类保存在 manifest 的 `outcomes[nodeid].outcome/reason/phases`，不丢失"预期失败"属性。

**JUnit 交叉校验**：逐项而非比总数。以插件记录的 junit 键（classname+name）对应每个收集项，要求：JUnit 没有插件未知的用例、插件的每个用例在 JUnit 里都有记录、状态相容（passed↔passed；failed/error↔failure/error；skipped/xfailed↔skipped；xpassed↔passed 或 failure）。teardown 错误在 JUnit 中与 call 记在同一 testcase 的形状已用真实 pytest 验证。任何无法解释的矛盾→error。

### 9.4 证据存储（`flowtree/evidence.py`）

`<root>/.flowtree/runs/<run_id>/<story_id>/<entry_id>/{manifest.json, plugin-report.json, junit.xml, stdout.txt, stderr.txt}` 为事实记录，`data.db` 的 `flowtree_attempts` 为索引（与旧 `flowtree_runs` 分开，旧记录保持 `legacy_unverified`）。先写 `state=running` 的 manifest 与索引行再执行；终态时在 manifest 中写各产物 sha256 并重写 manifest 与索引。读取时复核：manifest 缺失/损坏、索引行缺失或 manifest 哈希/状态与索引不符、产物缺失或被改→该尝试按 `error` 呈现并在 `evidence_problems` 中报告，**绝不推导为通过**。同一 (故事, 条目) 以**最新一次尝试**为准，之前的通过不会越过一次未完成/失败的新尝试。manifest 记录：命令、解析后的可执行文件、cwd、前后基线、`changed_during_run`、必需 nodeid、逐项结果、分类计数、JUnit 计数、退出码、耗时、实际运行时。

### 9.5 基线与有效性

`Baseline` 在 B1a 的 4 个核心字段上增加 `runtime_digest`、`verifier`（默认 None，Codex 的位置参数断言不受影响）。当前有效性比较 `story_digest`、`entry_digest`、`env_id`、`worktree_fingerprint`、`runtime_digest`、`verifier`：任一明确不同→`stale`；无不同但任一方有未知项→`unknown`；仅全部已知且一致才 `current`。`git_sha`、`mapping_digest` 仅溯源。

- `worktree_fingerprint`：`git ls-files --cached --others --exclude-standard` 的全部文件（含**未跟踪**源码）的 (路径, 内容 sha256) 合并哈希，与提交 SHA 无关；**排除本次使用的故事/映射文件**（它们由 story_digest/entry_digest 单独绑定，否则改一个映射条目会使全部条目过期——测试 `test_changed_mapping_entry_invalidates_only_that_entry` 抓到过这个双重计数）。非 git 目录→None→unknown。`.gitignore` 忽略的内容（如 `.venv`）不在其中。
- `runtime_digest`：被测解释器的实际解释器路径、Python 版本、平台、**全部已安装依赖及版本**、pytest 与插件版本。执行前用同一函数在 `python -I` 下探测，执行后以报告里的实际运行时为准并与探测比对。`.venv` 内容变化因此能被识别，即使它不在工作区指纹里。
- `verifier = "flowtree-b1b/1;plugin/1;report/1"`：验证器/插件/报告版本变化使旧证据 stale。
- **运行期间变化**：执行前后各算一次基线，并从磁盘重新读取故事与映射；工作区指纹、故事/条目摘要或运行时有变化（或无法重算）→结果保留，但 manifest 基线的指纹置空，有效性 `unknown`，不贡献当前通过，`changed_during_run` 列出原因。
- 对 `blocked/error/aborted` 的尝试，若运行时指纹在证据与当前两侧都拿不到（它描述的正是"无法运行"），视为一致，避免把真实的环境阻塞显示成 `not_run`；`completed` 的结果仍必须有可确认的运行时（测试 `test_completed_attempt_with_unavailable_runtime_is_still_unknown`）。

### 9.6 已知限制（如实）

1. **测试自身会弄脏工作区**时（运行中产生未被忽略的未跟踪文件），该次结果有效性为 `unknown`、不计当前通过；这是有意的保守选择，项目需要把测试产物加入 `.gitignore`。
2. 参数化：`parametrized` 仍拒绝；插件已提供"本次收集集合"，开放它需要另行设计完整性判定。
3. 映射黑名单对合并短选项（如 `-vx`）不穷尽，但范围改变选项由插件按生效值上报，最终以插件为准。
4. 仅 pytest；不解析 Flutter，不实现 MCP 协议收发，没有规则确认记录、实现检查来源、人工验收录入与身份机制（`human` 恒为 `none`）。
5. `flowtree status`（旧入口）仍只显示旧电路视图；新状态用 `flowtree story status`。
6. 证据读取每次扫描全部尝试目录，数量很大时需要优化。
7. `verify` 在执行前不会清理上次运行遗留的子进程以外的资源；清理与隔离仍由项目的测试夹具负责。

## 10. 实际验证（单批计数，不相加成一个"全绿"）

环境同第 1 节（项目 `.venv`；Python 3.13.7；pytest 9.2.0）。

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/implementation -q` | **218 passed**，0 skipped，0 failed（约 90 秒；含 35 项真实子进程/真实 git 仓库执行测试） |
| `.venv/bin/python -m pytest tests/independent -q`（Codex 独立断言，未改动） | **19 passed**，0 skipped，0 failed（第一轮审查时为 14 passed / 5 failed） |

`tests/implementation` 分文件：`test_b1b_execution` 35、`test_pytest_report` 42、`test_status` 37、`test_mapping` 34、`test_story` 25、`test_review_fixes` 18、`test_cli_and_legacy` 15、`test_canon` 8、`test_backend_signoff` 4。

B1b 真实执行测试（`test_b1b_execution.py`）覆盖：通过且证据落盘；默认范围含未映射单元→非零；断言失败=`failed`（非 error）；全部 skip=`not_run`；映射 nodeid 不在收集集合（exit 0 也是 error）；xfail=`failed`、strict/non-strict xpass=`error`；teardown/setup 失败；收集错误；参数化实例精确 nodeid 存在/不存在；`PYTEST_ADDOPTS` 被清除；ini `addopts -k` 被插件发现；rootdir≠cwd；解释器/ cwd 缺失与解释器缺 pytest=blocked；cwd 越出根目录；**超时终止孙进程**；改已跟踪文件/新增未跟踪文件/改故事/改条目/改 env.id 使证据 stale 且历史保留；忽略文件不影响；**运行中产生文件、运行中改故事→unknown 且不计通过**；产物被改、manifest 被改、索引行被删/状态不符；未完成尝试 running→aborted 且不回退到更早的通过；最新尝试优先。

### 真实执行证据：样本项目现存 pytest 入口（Codex 的映射）

为避免改动用户的另一个仓库，把 Life-Piggy-Bank 工作区复制到 scratchpad（排除 `venv/.git/.flowtree/.pytest_cache`），副本内 `git init` 后作为 `--project-root`，只借用样本自带的 `backend/venv` 解释器（Python 3.13.5 上的 pytest 9.1.1）。**这是副本在当时的工作区内容上的执行，不是原仓库路径，也不是某个提交的 clean 验证。** 原仓库执行后仍只有原本就有的未跟踪 `.flowtree/`。

```
cd /Users/liushengwei/project/PythonProject/virtual-manage
.venv/bin/python -m cli.main verify examples/stories --mappings examples/mappings \
  --project-root <scratchpad>/lpb --python /Users/liushengwei/taylors_project/Life-Piggy-Bank/backend/venv/bin/python --mapped-only
```

结果：run `run_20261110T080541_a7baa23f`，4 个映射条目各一次 attempt，均 `completed`、exit 0，各收集并通过 1 项，共 4 项（`test_savings_idempotency_key_deposit_and_yield`、Codex 映射的 TASK-A 两项与 TASK-B 一项）；`changed_during_run=false`；插件报告确认 rootdir=`.../lpb/backend`（== cwd）、ini=`backend/pytest.ini`、收集集合只有映射声明的 nodeid、`deselected=[]`。`--mapped-only` 范围内全部本次 `passed`，exit 0。
单元汇总：SAV-001 6 单元 2 passed/4 unmapped；TASK-A-001 6 单元 3 passed/3 unmapped；TASK-B-001 7 单元 4 passed/3 unmapped；19 个单元中 9 个本次自动验证通过、10 个未映射；规则全部 draft，人工全部未验收，三个故事均未完成。
证据位置（本机，gitignore，不入库）：`<scratchpad>/lpb/.flowtree/runs/run_20261110T080541_a7baa23f/<entry>/`。

不能由此推出：客户端入口、离页重进、重复领奖、版本历史等未映射项已验证；MySQL/E2E 等未运行；这 4 项也不与样本项目历史计数相加。

## 11. 遗留与下一步（第一轮 B1b 交付时；第二轮见第 12 节）

- 请 Codex 复跑 F01–F05 反例并补 B1b 真实子进程反例（已知需要关注：第 9.3 JUnit 兼容表、第 9.5 的 `blocked/error` 运行时视为一致的例外、第 9.6 第 1 条）。
- 本批全部改动仍未提交（dirty 工作区）；未提交即不是任何提交的 clean 验证。
- 后续批次候选（未开始，需用户决定）：纵向主线与 `+` 分支的前端、规则确认/人工验收录入与身份、`parametrized` 开放、Flutter 适配、MCP 协议收发、旧模板骨架去留。

## 12. Codex 第二轮复验 B1B-01～06 的修复

日期：2026-11-10。HEAD 仍为 `e299cc3`，全部改动未提交（dirty）。本节与第 9 节冲突处以本节为准。F01–F05 已由 Codex 关闭，未重开。

| 编号 | 修复 | 关键点 |
|---|---|---|
| B1B-01 最新记录损坏回退旧通过 | `latest_evidence` 基于**目录与索引的并集**确定最新尝试，身份（故事/条目/时间）在 manifest 不可读时仍由路径与索引恢复；最新记录损坏、缺失、索引不符、JSON 形状错误（非对象、字段类型错、`baseline` 非对象、缺键）一律产生 `corrupt` 证据，单元显示 `error`，`evidence_problems` 给出诊断。时间未知的记录视为最新，不能越过它取更早的通过。状态读取不会因此崩溃。 | `EntryEvidence.corrupt`；更早的损坏尝试只报告问题，最新有效的仍生效 |
| B1B-02 同名条目覆盖证据 | 存储键改为 **(run, story, entry)**：目录 `runs/<run>/<story>/<entry>/`，`attempt_id=<run>.<story>.<entry>`；仍读取旧布局 `runs/<run>/<entry>/`（有回归）。同一故事跨多个映射文件重复定义同一条目→校验 error `mapping.duplicate_entry`。`--entry` 支持 `STORY/ENTRY`；裸 ID 在多个故事都存在→报错不执行；未知→报错不执行；部分无效则整体拒绝。 | 不同故事可使用相同本地条目 ID |
| B1B-03 空范围返回成功 | 执行前解析范围：输入有 error、选择未知/歧义、映射没有任何条目、必需范围没有单元，均 `executed=false`、`ok=false`、非零。`--entry` 选定时必需范围=这些条目覆盖的单元。 | 不创建"成功执行"的叙述 |
| B1B-04 环境配置变更沿用旧通过 | 基线新增 `env_digest`：传给被测进程的**全部环境变量**（去掉已知会话级噪声如 `PWD/OLDPWD/_/SHLVL/PYTEST_CURRENT_TEST` 与 FlowTree 自注入变量）的 HMAC（项目本地随机盐 `.flowtree/env.salt`，权限 0600），只存名称与 HMAC，**不落明文**。任一变量新增/删除/变值→`stale`，状态输出点名变化的变量名（不含值）。映射可用 `env.ignore: [NAME]` 声明确实无关的变量（计入条目摘要，改动会使旧证据失效）。`env_digest` 缺失→`unknown`。`VERIFIER` 升为 `flowtree-b1b/2`，旧证据因此 stale。`env.id` 仍只是标签。 | 默认保守：宁可多失效，不沿用旧通过；`mapping.env_ignore` 校验变量名 |
| B1B-05 真实命令失败却返回成功 | 逐场景结果保持准确（被映射的测试可为 passed），**另外**记录并呈现整条命令的结果：attempt 增加 `command_clean`（`completed` 且 pytest exit 0）与 `unmapped_nonpass`（未被映射但已失败/出错/XPASS 的测试）。`verify` 的 `ok` 还要求所有 attempt `command_clean`；`--mapped-only` 只缩小验收分母，不豁免命令失败。`story status` 增加独立的 `command_failures` 列表。未映射的 skip/xfail 不弄脏命令（pytest 本身 exit 0）。不把断言失败改写为执行器 error。 | 退出码 1 的 completed 尝试仍是 `completed` |
| B1B-06 孙进程忽略 SIGTERM | `terminate_group`：SIGTERM 整个进程组→回收组长→有期限等待**整组成员**退出（组长退出不代表组空）→仍存活则 SIGKILL 整组→确认组已清空，结果（`sigterm/sigkill/cleared`）写入 manifest `cleanup`。超时、Ctrl-C、执行器异常以及"命令正常结束后仍有同组遗留进程"（测试泄漏）四条路径都走它。只使用我们创建的进程组 ID，不扫描其他进程。清理失败会在原因中明示 `NOT FULLY CLEARED`。 | 超时原因不再无条件写"terminated" |

### 12.1 实际验证（单批计数，不相加）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/implementation -q` | **247 passed**，0 skipped，0 failed（约 188 秒）；本轮新增 `test_b1b_fixes.py` 27 项真实子进程回归，另更新 `test_status.py`/`test_pytest_report.py` 里手工构造的 `Baseline`（补 `env_digest`） |
| `.venv/bin/python -m pytest tests/independent -q`（Codex，未改动） | **33 passed**，0 skipped，0 failed（上一轮为 25 passed / 8 failed，含原 19 项） |

变异核对：临时去掉 SIGKILL 阶段、让最新损坏记录被跳过后，`truncate`、`remove_dir`、`sigterm_ignoring_grandchild` 三项回归失败；文件已恢复并重跑全量。运行结束后确认没有遗留的 `time.sleep(60)` 子进程。

我自己的回归与 Codex 反例构造不同，额外覆盖：6 种损坏方式（含整目录删除、非对象 JSON、`baseline` 类型错、缺键）、索引行被删、旧布局记录可读、两个故事同名条目各自保留证据且一边失败不污染另一边、跨映射文件重复条目、`STORY/ENTRY` 与歧义选择、部分无效选择整体拒绝、空 `entries`、环境变量变更指出变量名、`env.ignore` 与噪声变量不使证据失效、环境值不在任何落盘文件中且盐文件权限为 0600、未映射失败使 `verify` 非零但被映射单元仍为 `passed`、`status` 单独列出 `command_failures`、未映射 skip/xfail 不弄脏命令、忽略 SIGTERM 的孙进程与"测试通过后泄漏的子进程"都被清空并记录。

### 12.2 本轮遗留与取舍（如实）

1. **环境默认全量纳入摘要**意味着不同终端会话的环境差异可能让旧证据显示 stale（安全方向）。已用噪声清单与 `env.ignore` 缓解；清单不穷尽，遇到误失效时按状态输出里点名的变量名补充 `env.ignore`。
2. 状态读取仍每次扫描全部尝试目录；数量很大时需优化。
3. 样本项目 4 项真实执行的本机原始证据（实现方证据，Codex 尚未独立定位）：`/private/tmp/claude-501/-Users-liushengwei-project-PythonProject-virtual-manage/b24c3cf9-be78-4462-ae68-8d8d38373f3f/scratchpad/lpb/.flowtree/runs/run_20261110T080541_a7baa23f/{M-SAV-REPLAY,M-A-COMPLETE,M-A-RELATION,M-B-REVIEW}/`。这批记录写于旧目录布局（`runs/<run>/<entry>/`），现在由旧布局兼容路径读取；其基线不含 `env_digest` 与 `flowtree-b1b/2`，在当前版本下会按 `unknown/stale` 处理，不作为当前通过。未为此重跑样本。
4. 其余未做事项同第 9.6 与第 11 节，范围未扩大。
