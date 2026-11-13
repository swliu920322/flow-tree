# 第一批协作安排：故事契约与真实执行证据

日期：2026-11-10。状态：已完成源码核对与分工安排，产品实现尚未开始。本文供用户转交另开的 Claude 会话；不表示 Codex 已与 Claude 直接通信或 Claude 已接单。

## 1. 基线与依据

- 核对基线：`e299cc355ca299a79387261d5b1128b8f44d2a17`，最新提交为交接文档；交接导出所记 `7472380` 是上一提交。
- 开始时工作区：仅 `?? docs/flowchart.mermaid`，属于用户已有文件，不覆盖、不顺手提交。
- 仓库及已检查的祖先目录没有发现 `AGENTS.md`。
- 产品边界以 `SESSION_HANDOFF_2026-11-10.md` 中已确认规则为准；故事与证据语义沿用 `STORY_ACCEPTANCE_SPEC.md`。本文细化第一批安排，不把其中全部建议升级为已实现或已批准的能力。
- 旧 PRD、提案、数据契约用于理解现状；与新故事规范冲突的横向默认视图、Agent 自报即通过等描述，不作为本批目标。

## 2. 当前实现核对

| 项目 | 当前事实 | 本批处置 |
|---|---|---|
| 文档扫描 | `cli/scanner.py` 只查候选路径和技术栈；没有读取正文提取故事 | CLI 如实说明；故事由外部 Agent 整理，不造内置模型抽取能力 |
| 模板生成 | `cli/generator.py` 根据项目名是否含 piggy 选择固定模板，两类脚本都固定 `passed = True` | 正常产品路径取消模板通过；旧模板只能作为明确隔离的 demo |
| 人工验收 | 模板预填 `humanSignOff`；`backend/app/main.py` 的 PATCH 收到 `review_pass` 即写 `human_reviewer`，没有真实身份依据 | 新路径不得写人工签字；旧 HTTP 自报入口须阻止借状态伪造人工签字，暂不建设完整身份系统 |
| 执行 | `cli/runner.py` 动态导入脚本，信任 `verify_all_nodes()` 的布尔值，没有真实命令与报告链 | 新增受控 subprocess + pytest/JUnit 路径，旧布尔接口不能提供新证据 |
| 空结果 | `cli/storage.py` 只要 blocked 数为 0 就写 ALL_PASS | 零测试、缺入口、全跳过和执行错误均不得通过 |
| 历史有效性 | 缺测试时保留旧节点绿灯；SQLite 有 git 列但 record_run 没填 | 保存实际基线；旧无证据记录保留为 legacy/unverified，不能沿用为当前通过 |
| 状态 | CLI 写节点 `blocked`，后端 NodeStatus 没有该枚举；自动失败与人工驳回混合 | 新领域状态独立于旧电路状态；旧展示做保守兼容投影，不把 blocked 硬塞进后端枚举 |
| MCP | `cli/mcp_server.py` 只有工具函数与就绪提示/--test，无协议收发循环 | 只保证现有工具包装不再走伪成功；完整 MCP 协议后置 |
| Web | React 画布按层级增加 x 坐标，仍是左右布局；没有故事分支与折叠风险摘要 | 下一批做纵向主线和 + 分支，本批不改整套画布 |
| 已有资产 | Pydantic 模型、DAG/透镜、API、React 画布和本地存储已存在 | 保留资产，新增故事/执行服务，不全面重写 |

### 本次实际验证

解释器：当前 `python3` 为 Python 3.13.7；可导入 pydantic、fastapi，找不到 pytest。本批未安装依赖、未接收费 API、未运行样本项目测试/部署。

1. 临时目录运行 `CircuitGenerator(...).generate_all('baseline-generic')` 与 `CircuitRunner.run()`：自动生成的人签节点为 `ROOT-PROJECT`、`N3-02`；模板返回 6 个通过、0 个 blocked，没有业务断言。
2. 删除临时目录中的生成测试脚本，再运行 runner：SQLite 本次记录为 `(total_nodes=0, passed_nodes=0, blocked_nodes=0, status='ALL_PASS')`；旧 logicVerified 仍保留。临时目录随上下文退出清理。
3. `python3 backend/test_projection.py`：exit 0；`python3 backend/test_life_piggy_bank.py`：exit 0。两者只打印演示投影，没有 assert，属于运行冒烟，不算业务断言通过数。
4. `python3 -m pytest backend --collect-only -q`：exit 1，`No module named pytest`。属于执行环境阻塞，没有测试通过计数。

以上复现说明验证器本身有缺陷，不重新打开 Life-Piggy-Bank 已关闭的问题。

## 3. 第一批范围与完成定义

批次目标：外部 Agent 提供结构化故事与显式测试映射，CLI 确实启动一次项目测试，保存可追溯证据，并诚实呈现未映射、未执行、失败、错误及人工待验。

分成两个顺序交付点，避免双方在接口未定时同时改公共文件：

**B1a：故事契约与结果真实性。** Claude 给出可运行的领域模型/校验器、字段示例及 CLI 入口，移除正常路径上的模板绿灯、伪人工签字与空结果通过。Codex 用独立反例核对契约，不等待可视化。

**B1b：一个 pytest 真实执行闭环。** Claude 实现单次执行和证据落盘；Codex 验证真实子进程、结果映射与旧证据失效。先以临时项目的真实断言做执行器验收，再在样本既有隔离环境可用时映射并运行一个现存 pytest 入口。两者分别记录；临时项目通过不代表样本业务通过。环境缺失时如实阻塞，不用历史样本计数补齐本批。

本批不做模型供应商接入、自主修复循环、Flutter 结果解析、完整 MCP 协议、纵向 UI 或业务数据库框架。这些已有方向保留到后续批次；第一批验收不宣称完整产品闭环已完成。

## 4. 文件归属

| 所有者 | 文件/目录 | 职责 |
|---|---|---|
| Claude：公共契约与主实现 | 新建 `flowtree/`（建议 `story.py`、`validation.py`、`execution.py`、`evidence.py`，最终模块拆分可简化） | 故事 Schema/引用校验、真实执行、解析、证据与领域状态；不依赖 Web 服务启动 |
| Claude | `cli/generator.py`、`cli/runner.py`、`cli/storage.py`、`cli/main.py`、`cli/mcp_server.py` | 正常路径去伪成功；CLI/现有工具类委托同一服务；明确旧记录兼容策略 |
| Claude | `backend/app/main.py`，必要时 `backend/app/core/schema.py` | 仅处理本批签字伪造与兼容边界；不实施整个 Web 迁移 |
| Claude | `tests/implementation/`、必要的依赖清单、`docs/BATCH_01_CLAUDE_DELIVERY.md` | 自测、最小可复现环境与交付记录；不改 Codex 的独立断言 |
| Codex | `docs/BATCH_01_CODEX_CLAUDE_2026-11-10.md`、后续 `docs/BATCH_01_INDEPENDENT_REVIEW.md` | 规则核对、差距和独立复验结论 |
| Codex | `examples/stories/`、`examples/mappings/`、`tests/independent/` | 三条真实故事草稿、显式测试映射、独立负例与执行器复验 |
| 暂不分配修改 | `frontend/**`、`backend/app/static/index.html`、旧业务数据 JSON、样本项目源码 | 后续批次再安排；不将演示数据迁移成真实证据 |

共用文件出现新需求时先在交付记录中交接归属，不能两边同时修改。Claude 可读所有反例，不能修改/跳过 Codex 的反例来获取绿灯；确认修好后由 Codex 更新缺陷标记。

## 5. B1a 需要冻结的最小接口

以下为本批实现约束，具体 Python 类名和命令名由 Claude 在 B1a 回报，Codex 据此编写调用，不各自维护第二套 Schema。

- 故事继续采用 `schema_version: "0.1"` 与既有字段：id/title/actor/goal/sources/preconditions/inputs/main_flow/branches/invariants/open_questions。接受 YAML；有独立故事版本或内容摘要，不能用 schema_version 替代内容版本。
- 校验项目内故事 ID 唯一、故事内 step/scenario ID 唯一、at/target 有效；end/rejoin 必须支持。retry 若暂不支持应明确拒绝，不能静默当 end；若支持必须有目标与有限重试策略。用户流程回路不得混入任务依赖 DAG。
- 未决问题能关联具体场景/步骤；只阻塞受影响范围。若旧格式只有文本而无关联，不得猜测其不影响任何场景，应保守显示待确认。
- 金额输入遵循十进制字符串；不得把任意文本字段猜成金额。涉及时间边界的样本提供固定时钟和时区；具体结构需在 B1a 示例中确定。
- 独立技术映射至少标识故事/步骤或分支、验证层级、cwd、argv、报告类型及实际测试标识。一个命令成功不能自动把没有执行到的映射项标通过。跨故事引用使用限定 ID。
- 四个维度分开保存：规则定义、实现检查、自动验证、人工验收。自动验证至少区分 unmapped/not_run/running/passed/failed/blocked/error/stale；命名可以调整但含义不能合并。blocked 用于已知环境前置缺失，error 用于执行/收集/解析故障；失败仅用于真实测试断言失败。
- 旧 NodeStatus 仅是兼容投影，不是新领域模型的事实来源。新路径遇到旧证据不显示当前通过；人工状态从未验收开始，执行器无权自动签字。
- 原始 PATCH 的状态自报不是人工操作证明，也不作为新执行证据。未完成身份机制前，不得仅靠 source 字符串赋予人签权限；旧模拟接口需明确 demo 隔离。

## 6. B1b 最小执行与证据约束

- 复用项目的测试命令与夹具，用 argv 启动子进程并指定 cwd/超时；不以 shell 拼接用户文本，不在执行器里偷偷建生产环境或迁移业务数据。
- 首个适配器解析本次 pytest 生成的 JUnit XML；报告路径每次运行唯一，旧报告不能被复用。保留原始输出、报告和退出码。报告/退出码矛盾、收集错误、格式损坏应有明确错误，不能只看 exit 0。
- passed 要求映射测试实际执行且断言通过；零测试、全部 skip、xfail、未知测试标识、缺命令、超时、缺报告均不能通过。混合结果逐场景呈现，不将未跑的分支涂绿。参数化、重复映射和多测试映射的聚合规则需在 B1a 明示。
- 最小 run/attempt/event/evidence 可先用文件和现有 SQLite 组合，不要求四套大表。至少保存运行 ID、故事摘要、源码 SHA、工作区状态与差异/快照标识、环境标识、真实命令/cwd、起止时间、退出码、分类计数、原始报告位置及场景映射。
- 首版单次 attempt，无自动重试；记录开始与终态，异常也留记录。代码/故事/映射变更、环境不符或基线无法识别时，历史记录保留但不能作为当前通过；不追求完整内容寻址系统。
- 汇总包含分母与分类数；命令失败给非零退出码，待验不能输出“全通”。旧人工记录不得被自动执行改写；旧模板签字不得继承为真实签字。

## 7. Codex 的三条样本与独立验收

样本从真实项目只读提取规则与测试入口，作为 draft 导入，不把原 Markdown 的 AUTO 标签转成新运行通过：

1. 零关系 A 任务完成：来源 `USER_STORY_MAP.md` US-09、US-17、US-23；覆盖本人操作、进度与仅一次奖励，具体任务目标由夹具明确。
2. 家庭 B 任务驳回重提：来源 US-24；覆盖提交不加分、驳回原因、重提新版本和审批后的有效进度，分支有后续出口。
3. 克制记录响应丢失后确认原请求：沿用故事规范 SAV-001 的恢复分支，并核对样本 E09 的实际记录测试。US-44 是“成果使用”，不能冒充“克制记录”来源；没找到足够规则时保留 open_questions。

独立用例至少验证：重复 ID/悬空引用；合法 rejoin；未决规则局部阻塞；模板无业务断言不能通过；缺脚本/零测试/全部跳过；断言失败与环境/解析错误分离；未知映射；混合场景结果；旧报告重放；基线变化；人工签字不被自动写入；CLI 返回码。独立测试须真正执行子进程并检查证据文件，不能只 mock 返回一个 passed。

## 8. 交接顺序与停止条件

1. 用户把本文转交 Claude。Claude 先读取两份原交接文档与本文，核对 HEAD/工作区，回报 B1a 公共接口、命令样例与最终文件清单，再实现其负责范围。
2. Codex 收到 B1a 接口后写三条样本和独立用例；可提前查来源，但不凭猜测创建另一套公共契约。
3. Claude 完成 B1b 及自测后，提交交付记录；Codex 在明确代码基线和隔离目录运行独立复验。
4. 每轮只回传可复现问题：规则依据、入口/命令、实际结果、预期结果、证据位置。修复后针对问题与必要回归复验，不重开已关闭的样本项目审计。
5. 本批最多安排两轮“独立复验 → 修复”；仍有未解决项就列明阻塞与下一步，不扩大范围、不用 skip 伪装完成。新发现的 UI/模型/部署事项单列后续任务。

每份交付必须包含：基线 SHA 与 dirty 状态、修改文件、接口/规则依据、实际命令、逐批计数及跳过/失败原因、环境和清理、原始报告位置、遗留问题。不同批次或不同环境的计数不相加冒充一次完整验收。

### 给 Claude 的可复制启动语

> 请先读 docs/SESSION_HANDOFF_2026-11-10.md、docs/STORY_ACCEPTANCE_SPEC.md 和 docs/BATCH_01_CODEX_CLAUDE_2026-11-10.md，核对当前 HEAD 与工作区。你负责本文第一批公共领域模型、校验和真实 pytest 执行/证据链及产品路径去伪成功；Codex 负责 examples/stories、examples/mappings、tests/independent 与独立复验，请勿修改这些文件。先回报 B1a 的字段与调用样例、状态/映射聚合规则、命令入口和最终文件范围，再按 B1a/B1b 顺序实现。保留用户 docs/flowchart.mermaid，不运行 Life-Piggy-Bank 部署或触碰真实库，不接收费模型、不先改画布或搭通用 Agent 平台。交付写到 docs/BATCH_01_CLAUDE_DELIVERY.md，附实际基线、命令、计数、原始证据和遗留项；不要把当前环境缺 pytest、未执行场景或旧模板绿灯写成通过。
