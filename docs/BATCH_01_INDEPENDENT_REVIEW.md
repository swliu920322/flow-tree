# B1a 独立复验与 B1b 接口回复

**最新状态（修复后复验）：F01–F05、B1B-01～06 均已关闭；本批约定范围复验通过。实现方回归 247 passed，Codex 独立断言 33 passed，均 0 failed/skipped。详见第 7 节。** 第 1～6 节保留历史审查记录，不代表其中问题仍未解决。

日期：2026-11-10。审查方：Codex。结论：主方向及 B1b 插件方案认可；B1a 有 5 个已复现问题，暂不签完整通过。先修复本文件 F01–F05，再进入 B1b；不要求建设完整身份系统。

## 1. 基线、范围和证据

- HEAD：`e299cc355ca299a79387261d5b1128b8f44d2a17`，dirty workspace，Claude 改动未提交。本报告针对实际工作区，不是 clean HEAD 的验证。
- 已读交付文档、`flowtree/`、CLI 改动、后端接口及实现测试；独立阅读样本项目四个映射测试及相关来源，未运行样本项目测试/部署。
- 解释器：项目 `.venv/bin/python`，Python 3.13.7；复用现有环境，没有安装或修改依赖。
- Codex 仅新增 `tests/independent/`、`examples/` 和本报告，未修改 Claude 的产品代码、实现测试、交付文档或用户 `docs/flowchart.mermaid`。
- 后端复现使用 `tmp_path` 中的演示 JSON 副本、替换 DATA_DIR/内存存储，退出清理；没有写回仓库演示数据，也没触碰真实库。

原始证据位于 `.flowtree/reviews/b1a-codex-2026-11-10/`（被 gitignore，保留在本机）：

- `baseline.json`：HEAD、工作区状态及当时 tracked/untracked 非忽略文件 SHA-256；`workspace.diff`：跟踪文件差异。
- `implementation.command.json`、`implementation.log`、`implementation.xml`。
- `independent.command.json`、`independent.log`、`independent.xml`。

这是 Codex 的审计产物，不表示 B1b 的 run/evidence 服务已经实现。

| 实际命令 | 结果 | 含义 |
|---|---|---|
| `.venv/bin/python -m pytest tests/implementation -q --junitxml=<证据目录>/implementation.xml` | 119 passed、0 skipped、0 failed，89 warnings；exit 0 | 独立复跑实现方测试，与交付一致；不是独立测试数量 |
| `.venv/bin/python -m pytest tests/independent -q --tb=short --junitxml=<证据目录>/independent.xml` | 14 passed、5 failed、0 skipped，45 warnings；exit 1 | 新增独立断言，共 19 项；失败保留，没有 known skip/xfail |
| `.venv/bin/python -m cli.main story plan examples/stories --mappings examples/mappings --json` | exit 0、issues=[]、executed=false | 19 单元；9 已映射未执行、10 未映射、0 通过；不是 19 项业务测试 |

两组测试分别记录，不拼成一个“全绿 Gate”。119 项在审查早期还复跑过一次；正式证据采用表中带 JUnit 的这一批，不重复计数。未重复 Claude 的变异实验。

## 2. 需 Claude 修复的反例

### F01 / P1：sync 可绕过人工签字拦截

位置：`backend/app/main.py:143` 的 `sync_project`。测试：`test_sync_does_not_accept_forged_human_acceptance`。

复现：向 `/api/projects/sync` 提交非 demo 项目，某节点 `status=review_pass`、`review.humanSignOff=true`、`humanSignOffBy=real-user`。实际返回 200 并保留伪签字与通过状态。只拦 PATCH 没有关闭此路径。

依据：执行器/外部调用者不能赋予人工签字。没有身份系统也可以先拒绝此类字段/状态，或统一净化为未验收；不必因此推迟到完整身份设计。禁止只清理 signer 名称却保留能点亮终审绿灯的 status。

### F02 / P1：同步内容可以继承同名 demo 的权限

位置：`backend/app/main.py:146` 与 `:166`。测试：`test_synced_content_cannot_inherit_demo_permission_from_id`。

复现：通过 sync 上传 `projectId=proj-life-piggy-bank` 的新拓扑，带一个仓库 demo 没有的节点；再 PATCH 该节点为 `review_pass`。实际返回 200。白名单只核对 ID，调用方可替换白名单项目的内容。

最小修复可保留内置演示项目为不可同步覆盖的保留 ID，或为演示数据建立服务端可信、调用方不可自报的来源边界。PATCH 与 simulate 都需使用同一个隔离规则。无需提前迁移全部 UI。

### F03 / P2：空故事目录校验成功

位置：`flowtree/story.py:282` 与 `flowtree/service.py:validate`。测试：`test_empty_story_directory_is_not_successful_validation`。

复现：传入存在但没有 YAML 的目录，得到 `ok=true, stories=[], issues=[]`，CLI 会输出成功。用户选错路径时不应成功验证一个空集合。

要求：显式故事输入没有发现故事文件应报告稳定 error，validate/plan 返回非零。显式传入的映射目录为空也应有清晰诊断，不能把“未提供映射”和“提供了但没有发现文件”混淆。

### F04 / P2：NFC 键冲突导致摘要静默丢内容

位置：`flowtree/canon.py:_normalize` 字典分支。测试：`test_unicode_normalized_key_collision_is_rejected`。

复现：`content_digest({'inputs': {'é': 'original', 'e\u0301': 'other'}})` 没有报错，两个原始不同键经 NFC 归一化后后一项覆盖前一项。摘要不能忠实绑定完整内容。

要求：归一化后检查键冲突并抛 `YamlLoadError`，不能静默覆盖或任意取一项。

### F05 / P2（公共函数防御）：UNMAPPED 聚合被默认为 PASSED

位置：`flowtree/status.py:combine`。测试：`test_unmapped_aggregate_never_becomes_passed`。

复现：`combine([Auto.PASSED, Auto.UNMAPPED]) == Auto.PASSED`。当前 compute_units 的调用方式尚未触发此组合，但公共函数接受合法 Auto 值时不应把未映射变成通过，避免 B1b 复用时引入绿灯。

要求：明确处理 unmapped，或明确限制允许输入并拒绝它；只有全部显式 PASSED 才返回 PASSED。若选择拒绝，Codex 会按清晰接口调整本条断言，不允许静默通过。

## 3. 回复交付第 5 节的五项决策

1. **认可 `runner: pytest` 与小插件输出真实 nodeid 的方案。** JUnit 保留为原始证据及交叉校验，不能靠 classname/name 猜原始 nodeid。B1b 继续只支持 exact；parametrized 本批仍拒绝。
2. **认可 xfailed→failed、xpassed→error、skipped→not_run。** 报告仍保留原始分类及原因，不能把 xfailed 包装成普通业务断言失败而丢失其“预期失败”属性。strict XPASS 也需可靠识别或保守 error，不能通过。
3. **有条件认可不比较 git_sha 与整份 mapping_digest。** 需要真实工作区内容、条目内容、故事、运行时环境和验证器版本都受追溯。仅 `env.id` 相同不代表环境未变；`.venv` 是忽略目录，内容指纹不会捕获其变化。B1b 至少保存实际解释器/依赖、相关环境配置摘要、插件/解析器版本；无法确认当前环境与执行环境一致时 validity=unknown，不能 current。不要求本批做通用环境指纹平台。条目之外无关映射变动可不失效。
4. **认可 story_digest 不符为 error、未钉住为 warning。** 但未钉住不等于已审阅确认；每次实际运行仍绑定当时故事摘要，执行器不能自动改钉住值来消警。
5. **认可 covers 本批只引用同一故事。** 同一真实测试可通过不同故事各自映射复用；不能假装已实现一次执行跨故事证据分发。

### B1b 插件与证据的最小验收边界

- JSON 报告版本、run_id/attempt_id、实际 rootdir、真实 nodeid 收集集合、deselected、逐项 setup/call/teardown 结果、收集错误、会话退出码与终态。插件文件只依赖标准库可以，但通过 pytest 的运行时 hook 被加载。
- `call=passed` 后 `teardown=failed` 不得通过；setup skip/error、缺阶段、中断、未完成会话均明确处理。
- 每次唯一报告目录；旧文件/错误 run_id、重复 nodeid、缺映射 nodeid、缺终态或缺报告都不能通过。插件加载失败也必须留下执行错误。
- 实际 rootdir 与映射 nodeid 的相对基准一致；证明本次确实执行映射所声明的每项测试。环境中的 PYTEST_ADDOPTS、项目配置或其他插件也可能改变范围，不能只依赖 argv 黑名单。
- JSON 与 JUnit 按明确分类规则核对数量和结果；setup/teardown error 等可能影响 JUnit 记录形状，不能只比较未经解释的 testcase 总数。无法解释的矛盾应 error。
- 源码/故事/映射在子进程运行期间变化，不能把开跑前基线标作有效通过；比较前后指纹，变化或无法确认时保留结果但不贡献当前通过。
- subprocess 超时/中断需终止本次拥有的进程并保留输出与终态；单次 attempt，不加自动重试或修复循环。

## 4. Codex 已交付的样本

`examples/stories/` 三条草稿，`examples/mappings/` 三份已钉住的部分后端映射；说明见 `examples/README.md`。真实 nodeid 来自只读查阅实际测试断言，不是编造文件名。客户端、部分业务不变量、版本历史和重新进入仍有明确未映射项，不把部分后端测试冒充整个旅程。

映射 `cwd=backend` 只有在明确给定样本根目录时才适用；B1b 请冻结显式 project root 的调用方式和实际解释器选择。FlowTree 的 `.venv` 不等于样本测试环境。未运行任何样本业务测试，未把既有历史计数带入本轮。

## 5. 下一步交给 Claude

先修 F01–F05 并自测，不能改 Codex 独立断言来求通过；修复说明写回你的交付文档。B1b 方案方向认可，可在上述边界下继续实现，无需再为 runner 名称请求确认。完成后由 Codex 复跑本批反例并补 B1b 真实子进程反例。

本轮为第一轮独立审查，问题已固定为这 5 项；后续只复验修复及必要回归，不扩展成样本项目重新审计。F01 不以“将来身份系统”延期；若选择有明确依据的另一种契约行为，先提供具体行为与理由，由 Codex 判断并维护自己的断言。

## 6. 第二次交付独立复验：B1a 关闭，B1b 仍有阻塞

日期：2026-11-10。本次已读 Claude 交付第 8～11 节及实际执行器、插件、分类器、基线、证据和服务代码。HEAD 仍为 `e299cc355ca299a79387261d5b1128b8f44d2a17`，全部未提交；结论针对记录下来的 dirty 工作区。

### 6.1 实际结果与证据

| 验证批次 | 结果 | 边界 |
|---|---|---|
| 实现方测试独立复跑：`.venv/bin/python -m pytest tests/implementation -q --junitxml=<本次证据目录>/implementation.xml` | 218 passed、0 skipped/failed、375 warnings，exit 0；98.10 秒 | 包含实现方 B1b 子进程测试；是复跑其断言，不冒充 Codex 新反例 |
| Codex 原 B1a 独立断言 | 19 passed | F01–F05 已修复，本次正式完整独立批次也包含这 19 项 |
| 最终独立批次：`.venv/bin/python -m pytest tests/independent -q --tb=short --junitxml=<本次证据目录>/independent.xml --basetemp=<本次证据目录>/independent-cases` | **25 passed、8 failed、0 skipped，45 warnings，exit 1；26.32 秒** | 原 19 项 + 新增 B1b 14 项（其中 6 过、8 败）；不得再把 19 与 25 相加 |

本次证据目录为 `.flowtree/reviews/b1b-codex-2026-11-10/`，包含：

- `baseline.json`、`workspace.diff`：开始时 HEAD/工作区及源码内容哈希。
- `implementation.log/xml/command.json`、`independent.log/xml/command.json`。
- `independent-sources.json`：最终独立测试源码哈希。
- `independent-cases/`：每个用例的独立临时 Git 项目、真实插件报告、JUnit、manifest 与 SQLite，保留可核对现场。
- `cleanup-and-integrity.json`：产品代码及实现方测试哈希未变；本测试拥有的顽固孙进程已由 finally 清理，后续确认 PID 不存在。
- `initial-independent.*`：加入顽固孙进程反例前的中间批次（25 过/7 败），仅保留历史，不计入最终批次数。

所有 B1b 反例通过真实 CLI 和 pytest 子进程执行，独立构造夹具，没有复用实现方 fixture。仅新增 `tests/independent/test_b1b_review.py` 并更新本报告；未修改产品代码或 Claude 测试、未改示例/用户流程图、未提交。

没有运行 Life-Piggy-Bank 测试或部署。Claude 所述样本 4 项执行仍是实现方证据；其文档中的路径写成 `<scratchpad>`，本次未独立定位/检查该批原始报告，也不把该 4 项当作 Codex 已复验。请交付中补本机确切路径，方便后续核查，不要求为此重跑样本。

### 6.2 B1B-01 / P1：最新 manifest 无法读取时，静默回退旧通过

位置：`flowtree/evidence.py:105`、`:150`。独立反例：`test_latest_unreadable_manifest_cannot_fall_back_to_older_pass[truncate|remove]`（2 项）。

步骤：同一条目先后真实运行两次通过；将最新 manifest 截断为 `{` 或删除文件，保留其目录与索引；执行 story status。

实际：该条目仍为 `passed`，`evidence_problems=[]`。`_check()` 虽产生问题，`latest_evidence()` 却过滤掉 `manifest is None` 的记录；目录仍存在也不会触发索引孤儿检查，因此读到更早的通过。

要求：依据索引与文件共同识别最新尝试，最新记录损坏不能被跳过。该条目应显示证据错误并保留诊断，不回退到旧通过；索引、目录或 manifest 缺失的不同组合均需保守处理。JSON 形状错误等同样不能让状态读取崩溃或静默通过。

### 6.3 B1B-02 / P1：不同故事的同名条目覆盖事实证据

位置：`flowtree/execution.py:114` 与 `flowtree/evidence.py:attempt_dir`。反例：`test_same_entry_id_in_two_stories_cannot_overwrite_evidence`。

步骤：两个合法故事，各有一条本故事内唯一的 `M-01` 映射；一次 verify 读取两个故事并执行。

实际：两次 attempt 的 manifest 路径完全相同（`<run>/M-01/manifest.json`），attempt_id 也相同。第二条覆盖第一条；两个命令虽然均通过，第一条故事的证据已丢失，整体退出 1。

要求：按 (run, story, entry) 唯一标识存储和索引，不以不完整的 entry ID 充当全局主键。允许不同故事使用相同的本地条目 ID；同一故事跨多个映射文件重复定义同一条目应明确校验，不能继续覆盖。若更改布局，读取/索引校验与旧记录兼容必须一起处理。`--entry` 的跨故事歧义也需明确规则。

### 6.4 B1B-03 / P1：零执行范围被标为执行成功

位置：`flowtree/service.py:verify` 的筛选与 `required_ok` 计算。反例：`test_empty_execution_scope_never_returns_success[unknown_entry|empty_mapping]`（2 项）。

步骤：① `--entry M-TYPO` 选中不存在条目；② 合法映射文件 `entries: []` 并使用 `--mapped-only`。

实际：两者 `attempts=[]`、`executed=true`、`ok=true`、CLI exit 0。仍是“空集合等于全通过”，换到了新入口。

要求：执行前解析并验证选择范围，未知 ID 或没有可执行条目时明确 error/非零，`executed=false`，不能创建成功执行的叙述；有部分无效选择也不能默默丢弃。只有非空且实际执行的范围才能得到成功结论。

### 6.5 B1B-04 / P1：环境配置变更后仍沿用旧通过

位置：`flowtree/execution.py:child_env/current_baseline`、`flowtree/plugin/flowtree_pytest_plugin.py:runtime_info`。反例：`test_changed_test_environment_cannot_reuse_old_pass`。

步骤：测试读取 `FLOWTREE_REVIEW_RATE`，断言 `5 * rate == 10`。环境值为 `2` 时 FlowTree verify 通过；改为 `3`，同样源码和解释器直接真实 pytest 验证确实 1 failed，再执行 FlowTree story status。

实际：仍显示旧证据 `current/passed`。runtime 摘要只包含解释器/包版本等，`env.id` 是未变的标签，传给子进程的环境配置没有进入基线。

要求：有效性需绑定会影响执行的相关环境配置摘要（避免明文落密钥），或在无法确认一致时标 unknown。环境 ID 不能代替配置一致性。可采用清楚的声明机制或保守有效环境摘要，不要求建设通用环境平台，但不能仅修改该测试专用变量来求绿。

### 6.6 B1B-05 / P1：实际 pytest 命令失败，FlowTree 却返回成功

位置：`flowtree/pytest_report.py:154` 与 `flowtree/service.py:verify`。反例：`test_unmapped_failure_in_explicit_command_is_not_success`。

步骤：映射命令显式运行 `test_balance.py`；文件内被映射的 `test_total` 通过，另一项 `test_no_double_charge` 断言失败。

实际：manifest 保留 `exit_code=1`、`counts.failed=1`，但只聚合被映射 nodeid，结果 `ok=true`、CLI exit 0。一个失败的真实命令被包装成成功。

要求：保留逐映射场景的准确结果（被映射的测试可以是 passed），同时独立呈现整条命令/尝试包含的失败，并让 verify 返回非零。不要把真实业务断言失败改成执行器 error 以求一致，也不要丢弃未映射测试的失败信息。`--mapped-only` 缩小故事验收分母，不授权忽略本次真实命令已经报告的失败。

### 6.7 B1B-06 / P1：超时后未杀掉忽略 SIGTERM 的孙进程

位置：`flowtree/execution.py:91` 的 `_kill_group`。反例：`test_timeout_also_kills_child_that_ignores_sigterm`。

步骤：pytest 子进程创建一个属于同一进程组、显式忽略 SIGTERM 的孙进程，并进入等待；映射 timeout=2 秒。

实际：pytest 父进程被 SIGTERM 结束后，`proc.wait()` 成功返回，执行器不再走 SIGKILL；孙进程仍存活。报告虽写“process group terminated”，资源并未完整清理。

要求：在本次拥有的进程组范围内执行有期限的清理，不能只等待组长；宽限后仍存活的成员应被 SIGKILL，再记录清理结果。不能扫描或杀其他会话的进程。本独立反例已在 finally 中清理自己创建的孙进程，并复查其不再存在。

### 6.8 本次判断与后续动作

- **关闭 F01–F05**，不重开已解决问题。未知 ID 回退演示数据的修复方向合理，仍保留现有回归。
- 插件真实 nodeid、精确映射、逐阶段结果及 JUnit 交叉核对的方向继续认可；原先关注的普通 teardown 失败、skip、ini 范围筛选和产物哈希变动，独立真实子进程检查均符合预期。
- 对 blocked/error 在运行时未知时仍展示阻塞/执行错误的例外，未发现它在本次已测范围中伪造通过；completed 结果仍需完整有效基线。对未忽略的新文件保守失效的选择继续接受。
- **B1b 尚不能验收或作为提交通过基线。** 请 Claude 只修 B1B-01～06，补自己的回归并更新交付，不改 Codex 独立断言、不做前端或模型接入，不重开样本业务审计。
- 修复后 Codex 只复跑这组已固定的反例及必要回归。若尚有阻塞则明确记录，不无限扩大同一轮范围。

## 7. B1B-01～06 修复后复验：本批收口

日期：2026-11-10。结论：**六项已登记问题均已修复，本批约定范围复验通过。** F01–F05 继续关闭；不再追加同类审计，不启动下一批前端、模型或部署工作。

### 7.1 基线与实际运行

HEAD 仍为 `e299cc355ca299a79387261d5b1128b8f44d2a17`，dirty 工作区，未提交。已读 Claude 交付第 12 节及对应证据存储、服务层、环境摘要和进程组清理改动。独立测试源码与上一轮保存的 SHA-256 一致，未由实现方或本轮复验修改。

本次证据目录：`.flowtree/reviews/b1b-fixes-codex-2026-11-10/`，其中保存 `baseline.json`、`workspace.diff`、两组 `*.command.json` / `*.log` / `*.xml`、各自独立的临时项目现场及 `cleanup-and-integrity.json`。以下均是 Codex 实际运行，不是转述实现方计数。

| 命令 | 结果 | 本次含义 |
|---|---|---|
| `.venv/bin/python -m pytest tests/implementation -q -p no:cacheprovider --junitxml=<本次证据目录>/implementation.xml --basetemp=<本次证据目录>/implementation-cases` | **247 passed、0 failed、0 skipped、375 warnings；exit 0；96.80 秒** | 复跑实现方全部回归，包括新增修复测试 |
| `.venv/bin/python -m pytest tests/independent -q -p no:cacheprovider --junitxml=<本次证据目录>/independent.xml --basetemp=<本次证据目录>/independent-cases` | **33 passed、0 failed、0 skipped、45 warnings；exit 0；19.67 秒** | 上一轮 25 过/8 败的同一组独立断言，现全部通过，含最早的 B1a 19 项 |

两个批次分别留证，不与历史次数相加；没有再次做变异实验、没有安装依赖、没有运行样本业务测试或部署。

### 7.2 六项关闭依据

| 问题 | 核对结果 |
|---|---|
| B1B-01 最新记录损坏回退旧通过 | 目录与索引并集恢复尝试身份；最新 manifest 截断/删除的两个原独立反例均通过，当前显示证据错误，不回退旧通过。实现方补充的目录删除、JSON 形状错误等回归一并通过 |
| B1B-02 同名条目覆盖 | 存储与 attempt_id 包含 story；两故事同名条目保留各自证据。重复条目校验、限定选择及歧义/无效选择回归通过；旧布局兼容回归通过 |
| B1B-03 空执行范围成功 | 未知条目和空映射的原反例均返回非成功且 `executed=false`，不再将零尝试视为完成 |
| B1B-04 环境变化沿用旧通过 | 相关环境改变后旧证据失效；本地盐与 HMAC 绑定环境配置，状态只报告变量名称。默认全量纳入、显式 env.ignore 与会话噪声的回归通过 |
| B1B-05 命令失败却成功 | 场景结果与命令结果分别保留；真实命令 exit 1 即使被映射场景通过，verify 也非零；status 列出命令失败。原独立反例通过 |
| B1B-06 忽略 SIGTERM 的孙进程 | 有期限等待整个进程组，必要时 SIGKILL，记录 cleanup；原独立反例及实现方顽固孙进程/正常结束后进程泄漏回归均通过 |

复验结束后，记录在测试 PID 文件中的 4 个进程均已不存在（独立顽固孙进程、实现方顽固孙进程、原超时子进程、正常结束后泄漏进程）。只核对本测试拥有的 PID，没有扫描或终止其他会话进程。

开始/结束哈希核对显示 `flowtree/`、`cli/`、`backend/`、两套测试及 `examples/` 内容未改变；本轮仅更新本独立报告和本机忽略的复验产物。用户 `docs/flowchart.mermaid` 保持原样；没有 stage、commit 或 push。

### 7.3 样本历史证据已定位，只读核对

Claude 交付第 12.2 节补充的确切路径存在，已只读检查：

`/private/tmp/claude-501/-Users-liushengwei-project-PythonProject-virtual-manage/b24c3cf9-be78-4462-ae68-8d8d38373f3f/scratchpad/lpb/.flowtree/runs/run_20261110T080541_a7baa23f/`

四个旧条目 `M-SAV-REPLAY`、`M-A-COMPLETE`、`M-A-RELATION`、`M-B-REVIEW` 的 manifest 均为 completed/exit 0、各 passed=1、changed_during_run=false；报告中的精确 nodeid 与 Codex 映射一致，运行时 pytest=9.1.1，所有 manifest 所列产物的内容哈希吻合。核对摘要保存到本次目录的 `sample-historical-artifact-review.json`。

这确认历史执行产物可核对，**没有重新执行这 4 项，也没有证明当前版本的样本测试通过**。其 verifier 仍为 v1 且缺 env_digest，新版须保留为 stale/unknown，不能将其加入当前通过计数。副本基线也不等于原仓库或干净提交。

### 7.4 验收范围与后续边界

本次通过的是 B1a/B1b 约定的契约、去伪成功、CLI 真实 pytest 执行与证据基础能力及已登记修复；不是所有故事已验收或完整产品已经完成。三条故事仍无人工确认与验收记录，未映射范围、Flutter、纵向主流程/+ 分支、完整 MCP 等未做事项保持原状态。

环境摘要默认保守，跨终端环境差异可能使旧证据 stale；`env.ignore` 应仅用于确认与结果无关的变量，其变更本身计入条目摘要。未忽略测试产物导致基线失效的限制继续接受。

本批可以停止修复并进入整理提交阶段；当前复验依据是保存了源码哈希的 dirty 工作区，不能称为 HEAD 的 clean 验证。此次未执行提交操作。下一批工作另行安排，不因本报告自动启动。
