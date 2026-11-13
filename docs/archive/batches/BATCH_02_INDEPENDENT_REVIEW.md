# 第二批独立验收：只读故事页面

**最新状态：B2-01、B2-02 均已关闭，第二批约定范围复验通过。Codex 实际复跑实现方 290 passed、独立 41 passed，均 0 failed/skipped，含 5 项实际 Chrome 渲染测试。修复后证据见第 8 节。**

日期：2026-11-10。以下第 1～7 节保留首次独立验收记录：页面主流程与真实点击验收符合本批预期，原项目只读性通过；当时新增两项接口反例待修。历史失败不代表当前状态，本轮未扩展 B1 审计。

## 1. 基线与范围

- HEAD：`b5aca56cbc5f45fc8cdb7fefb3ef9634f49e33c7`，dirty 工作区；已读 Claude 第二批交付文档、源码与本机配置。
- Codex 新增 `tests/independent/test_b2_review.py`（8 项独立 API/视图断言）及本报告，没有修改实现、实现方测试、既有独立反例、故事或映射。
- 确认当前运行入口：旧页面由 `backend/app/static/index.html` 提供；Vite 的 index.html 引用 `src/main.tsx`，当前文件缺失。新增 `/stories` 是独立的本地 JS/CSS 页面，不依赖其构建。这里仅确认当前文件状态，不从缺少 node_modules 推断历史上从未构建过。
- 目标项目 Life-Piggy-Bank HEAD `a4cc0a023cf2e3d4a96ba87c828616ed747db0f3`。读取前后 tracked 源码和 `.flowtree/` 全部文件逐一哈希相同，普通 Git 状态仍只有 `?? .flowtree/`，未运行样本业务测试/部署。

本机证据：`.flowtree/reviews/b2-codex-2026-11-10/`，包含开始基线、差异、原项目前后完整性核对、两组 pytest 输出和 JUnit、独立浏览器脚本/操作结果/截图。运行产物不入库。

## 2. 实际运行结果

| 批次 | 结果 | 说明 |
|---|---|---|
| 实现方全量独立复跑 `pytest tests/implementation -q -p no:cacheprovider`（带 JUnit、独立 basetemp） | **276 passed、5 errors、0 skipped，375 warnings；exit 1** | 5 项为 Chrome 渲染测试的本地服务启动被默认沙箱禁止绑定回环端口；保留原始错误，不记为产品断言失败或通过 |
| 在允许本机端口的环境中，仅补跑 `tests/implementation/test_b2_page_render.py`（带 JUnit、独立 basetemp） | **5 passed、0 failed/skipped；exit 0；13.66 秒** | 修复的是运行权限，不改源码或断言。上述 281 项覆盖分属两个实际批次，不冒充一次全绿运行 |
| 独立 `pytest tests/independent -q --tb=short`（带 JUnit、独立 basetemp） | **39 passed、2 failed、0 skipped，45 warnings；exit 1；22.19 秒** | 原 33 项仍通过；新增 B2 共 8 项，其中 6 过、2 败；不把旧 33 再相加 |
| 独立真实 Chrome 交互 | **脚本完成，控制台无异常，观察到的页面请求全部 GET** | 实际点击而非只用深链驱动状态；见第 3 节 |

精确 argv、退出码、stdout/stderr 分别保存在 `implementation.command.json/log/xml`、`implementation-browser.command.json/log/xml`、`independent.command.json/log/xml`。本轮未重复 Claude 的测试计数或自查过程来冒充独立执行。

## 3. 真实浏览器验收

内置 Browser 技能已读取并按要求排查，但无可用浏览器实例（列表为空）。使用本机独立 Chrome 配置与只对回环地址开放的调试连接进行备用验收；没有安装新自动化依赖。只读 FlowTree 测试服务使用 `127.0.0.1:8766`，未占用 Claude/用户的 8000 端口。

已实际操作：

1. 打开原项目的 SAV-001，确认四个主步骤纵向排列、默认分支折叠，页头“本次通过 0/待更新 2/未映射 4”，规则草稿、人工未验收独立显示。
2. 点击 `+`，两条恢复分支出现并正确写明汇合到第 3 步；再点击收起，仍显示“待更新 1、未映射 1”。
3. 点击展开全部、显示稳定 ID、风险过滤并还原，确认实际事件生效；当前真实证据均待更新，因此风险过滤保留它们。有效通过场景的过滤由补跑的实现方渲染测试另行覆盖。
4. 点击分支打开抽屉，再点击运行详情和 JUnit 报告，查看真实 nodeid/run/命令/基线及报告；未见 `null`、`[object ...]` 之类渲染文本。
5. 点击关闭、重新读取、家庭 B 故事标签，确认抽屉关闭、刷新完成、故事内容切换。
6. 390×844 窄屏抽查：document/body scrollWidth 均为 390，无横向溢出；深色媒体偏好已实际生效，背景与文本样式可读。属于桌面 Chrome 模拟视口抽查，不冒充真实手机或 Safari 验收。

截图：`desktop-collapsed.png`、`desktop-evidence.png`、`mobile-expanded.png`、`mobile-dark.png`；均已视觉检查。操作与网络记录见 `browser-review.json`，Chrome 自有进程已退出。

初次备用脚本因错误假定 HTTP 101 的响应描述必须为“Switching Protocols”而未开始交互；已改为验证状态码及 WebSocket accept，之后完整交互通过。这是验证脚本错误，不登记为产品缺陷。

## 4. B2-01 / P1：manifest 不可信时仍返回其伪造报告

位置：`flowtree/view.py:read_artifact`。独立断言：

`tests/independent/test_b2_review.py::test_artifact_with_tampered_manifest_is_not_trusted_even_if_hash_matches`

复现：临时项目通过真实 CLI/pytest 产生证据；修改 stdout，随后把 manifest 中该产物的 SHA-256 一并更新，**不更新 SQLite 索引**；GET attempt 详情和 stdout 产物。

实际：attempt 详情正确列出 manifest 与索引不一致；artifact 接口却忽略 `r.problems`，只比较文件与被修改过的 manifest 哈希，返回 200 和 `independent-forged-output`。

要求：作为验收证据提供内容前，验证完整信任链。manifest/索引不一致、记录身份错误等完整性问题存在时，产物接口应 409，不能用不可信 manifest 自证哈希。详情可以保留诊断，不能同时把该产物作为已核对证据返回。无损坏记录的正常产物仍应可读，读取不修改目标文件。

本例操作的是独立临时项目，未修改 Life-Piggy-Bank 的真实证据。

## 5. B2-02 / P2：配置切换后混用旧项目缓存

位置：`flowtree/view.py:get_state`。独立断言：

`tests/independent/test_b2_review.py::test_workspace_config_switch_cannot_reuse_other_project_cache`

复现：两个不同项目使用同一个 workspace ID，各自有 `INDEPENDENT-A` 故事但标题不同；先读取项目一，再用变更后的 workspace 配置读取项目二（不强制刷新）。

实际：缓存仅以 `ws.id` 为键，20 秒内返回项目一的 stories/state；外层却使用新 Workspace 输出项目二的名称、project_root。得到“项目二的名称与路径 + 项目一的故事/证据”的混合响应。

要求：缓存身份包含实际影响结果的工作区配置（项目根、故事/映射路径、解释器、执行上下文等），或配置变化时失效。仅比较 ID 不足，不能依赖用户手动刷新。保留正常的 20 秒内容缓存及显式刷新能力，不要求本批实现文件监控。

## 6. 环境摘要：本批选择维持现有契约

**选择方案 (a)，不引入 env.include 默认白名单。** 只读页面如实显示历史 passed 和当前 stale/unknown，已经满足任务书；没有“当前通过”不妨碍页面试用，也不意味着业务测试失败。

本次 Codex 启动的 Web 服务与 Claude 会话的差异集合并不相同：独立截图里仅显示 `CODEX_TOOL_CALL_ID` 一项环境差异；其余故事、映射、代码、运行时、验证器与环境 ID 一致。这说明差异数量由执行宿主/会话决定，不能把“40 个变量”硬编码成产品结论。

后续若要建立稳定重检上下文，先固定执行环境；确认与测试无关的宿主变量可以逐个使用已有 `env.ignore`，无需改变 B1 契约。该配置变动须正常改变条目摘要并由新运行产生新证据，不能篡改旧摘要或自动排除整个供应商前缀。真正业务变量仍须参与失效判断。

## 7. 覆盖登记与下一步

Claude 提出的两个后端映射线索已经由 Codex 只读核对：

- `test_tasks_slice.py::test_self_discipline_task_vertical_slice` 确有重复提交 409、A 分不变、账本仅一条的断言，可支持 TASK-A-001.CASE-02 的行为要求（奖励数值属于各自夹具）。
- `test_family_tasks_flow.py::test_task_closed_loop_assignment_submission_and_approval` 确有版本 1/2、原凭证及驳回原因保留、新凭证和审批人的断言，可支持 TASK-B-001.CASE-02。

它们是已有测试待接入，不是新发现业务缺陷。本次先不改 `examples/`，避免把页面验收与映射/执行基线变更混在一起。B2-01/02 关闭后，可由 Codex 单独完成这两项映射与所需的最小真实执行；“已映射从 9 到 11”不能自动变成“当前通过从 9 到 11”，新增/修改的条目须产生新证据。

给 Claude 的动作：只修 B2-01、B2-02，补自己的回归，不改 Codex 独立断言；维持环境方案 (a)，不用为页面绿灯增加白名单或重检按钮。更新你的交付记录后，Codex 复跑固定反例与必要回归，再决定提交。本批不得把只读页面顺手扩为测试执行、规则批准或人工签字入口。

## 8. 两项修复后独立复验：第二批收口

日期：2026-11-10。结论：**B2-01/B2-02 均关闭，第二批约定的只读故事页面与证据展示可以收口。** 不新增同类审查范围，不启动执行/规则确认/人工签字入口，不因环境差异把历史结果改成当前通过。

### 8.1 基线与真实结果

HEAD 仍为 `b5aca56cbc5f45fc8cdb7fefb3ef9634f49e33c7`，dirty 工作区。本次已读 Claude 交付第 9 节和修复实现。没有修改产品、两套测试、样本故事/映射，也没有再次做变异实验。

本机证据目录：`.flowtree/reviews/b2-fixes-codex-2026-11-10/`。包含 `baseline.json`、`workspace.diff`、原项目前后哈希、两组命令的 `*.command.json/log/xml`、独立临时项目现场及 `integrity-and-counts.json`。

| 实际命令 | 本次结果 |
|---|---|
| `.venv/bin/python -m pytest tests/implementation -q -p no:cacheprovider --junitxml=<证据目录>/implementation.xml --basetemp=<证据目录>/implementation-cases` | **290 passed、0 failed、0 skipped，375 warnings；exit 0；152.21 秒** |
| `.venv/bin/python -m pytest tests/independent -q -p no:cacheprovider --tb=short --junitxml=<证据目录>/independent.xml --basetemp=<证据目录>/independent-cases` | **41 passed、0 failed、0 skipped，45 warnings；exit 0；21.64 秒** |

实现方测试本轮直接在允许绑定回环端口的环境中运行；JUnit 核对确认 `test_b2_page_render` 的 5 项全部实际执行，未跳过。本轮是一次完整的 290 项运行，不借用首次沙箱下的 276+5 计数。41 项独立断言包含原 33 项及 B2 的 8 项，未重复累加旧批次。

### 8.2 关闭依据

- **B2-01**：产物读取在提供内容前检查记录自身的完整性结论。有 manifest/索引不一致等问题时，返回 409；不能通过同步伪造文件和 manifest 哈希取得内容。原独立反例通过；实现方补充的其他产物、其他完好条目、索引缺失/状态变化、完好产物只读回归一并通过。
- **B2-02**：缓存身份包含项目根、解释器、故事/映射路径、执行上下文及 git excludes 等实际配置，不再仅使用 workspace ID。原项目切换反例通过；列表、详情、配置逐项变化、同配置 TTL 命中与 refresh、淘汰旧配置等回归一并通过。

本轮页面 html/js/css 与上一轮实际点击、窄屏和深色检查时的文件哈希一致，因此沿用上一轮已完成的交互/视觉结论；同时本次完整复跑了 5 项 Chrome 渲染回归，不为没有变化的页面再做一轮相同交互。

### 8.3 完整性与边界

- 测试开始/结束的产品、两套测试和 examples 哈希一致。
- 原项目源码和 `.flowtree/` 全部文件哈希未变，HEAD 仍为 `a4cc0a023cf2e3d4a96ba87c828616ed747db0f3`，普通 Git 状态仍只有既有 `?? .flowtree/`；没有重跑样本业务测试、部署或连接真实库。
- 核对测试独有 PID 文件中的 4 个进程，均已不存在；没有操作其他会话进程。
- 环境方案维持 (a)，只读页面保留“历史通过／对当前上下文待更新”的准确表达。没有新增 env.include 白名单或重检/执行入口。
- 未执行 stage、commit 或 push；用户 `docs/flowchart.mermaid` 未动。复验结论绑定保存了源码哈希的 dirty 基线，不声称当前 HEAD 自身是完整实现。

下一步可以整理提交本批已验收改动；提交前按文件清单排除本机配置、`.flowtree/`、依赖环境与用户流程图。其后由 Codex 单独安排第 7 节两项已有后端测试的增量映射和必要真实执行，不把它们混作本次页面修复的一部分，也不重开样本全量审计。
