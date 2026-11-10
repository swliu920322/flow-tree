# 第二批交付记录（Claude）：只读故事验收页面

日期：2026-11-10。任务书：`docs/BATCH_02_CLAUDE_TASK_2026-11-10.md`。基线 HEAD `b5aca56`，本批全部改动**未提交**（dirty）。不改写 B1 历史记录。

## 1. 交付了什么

打开 `/stories`，用 Life-Piggy-Bank 三条真实故事的纵向主流程、可展开分支、四个独立维度和真实测试证据详情；页面只读，浏览/刷新/展开不执行测试、不写被测项目、不写验收记录。旧电路视图 `/` 原样保留。

### 1.1 入口决定（任务书要求先核对运行入口）

- `frontend/` 是 Vite 工程，但 `src/` 下没有入口文件（只有组件、CSS、类型），也没有 `node_modules`，**从未能构建**，不接入。
- 实际可运行的旧页面是 `backend/app/static/index.html`（CDN 加载 React + Babel，约 1300 行）。不修改它，也不在其上叠加，避免两份互相脱节。
- 新页面 `backend/app/static/stories.{html,css,js}`：原生 JS，**无 CDN、无构建步骤**，可离线运行；测试断言页面不含外部地址、`innerHTML`、`eval` 与任何写请求。

### 1.2 文件归属与清单

我修改/新增（Codex 的 `examples/`、`tests/independent/`、`docs/flowchart.mermaid`、旧 `index.html`、`frontend/` 均未动）：

| 文件 | 内容 |
|---|---|
| `flowtree/workspace.py`（新） | 工作区配置：项目根、解释器、故事/映射路径、执行上下文（环境变量覆盖 + git excludes）。不含任何项目业务规则 |
| `flowtree/view.py`（新） | 把故事/映射/证据/当前基线投影成页面结构；复用 `compute_units`，不另算状态；20 秒缓存，`refresh=true` 跳过 |
| `backend/app/stories_api.py`（新）、`backend/app/main.py` | 只读路由（仅 GET）与 `/stories` 页面路由 |
| `backend/app/static/stories.{html,css,js}`（新） | 页面 |
| `config/workspaces.example.yaml`（新） | 配置示例；本机真实配置在 `.flowtree/workspaces.yaml`（已被 gitignore，不入库） |
| `flowtree/service.py` | 抽出 `collect_state`（只读状态收集），`story status`/Web 共用；`_status_core` 改为只读 |
| `flowtree/evidence.py` | `EvidenceStore(readonly=True)`：不建目录/库/表，SQLite 只读打开；`latest_evidence` 可复用一次扫描结果；新增 `latest_record` |
| `flowtree/baseline.py`、`flowtree/execution.py` | `env_salt(create=False)`（只读不建盐文件，缺失则环境摘要为未知）；git 调用可带执行上下文环境；`current_baseline(extra_env, readonly)`；噪声清单加入 `FLOWTREE_WORKSPACES` |
| `flowtree/status.py` | `compare_aspects`：逐维度比较（一致/不同/无法确认） |
| `requirements.txt` | 增加 `uvicorn`（启动 Web 服务所需；此前清单缺它，启动命令跑不起来），已装入项目 `.venv` |
| `tests/implementation/test_b2_stories_api.py`、`test_b2_page_render.py`（新） | 本批测试 |

对 B1 契约的影响：默认行为不变（`readonly`/`extra_env` 为可选参数，默认保持原行为）；`VERIFIER` 版本**未**升级，因此 Codex 的真实证据不会因本批失效。唯一语义变化是噪声清单增加 `FLOWTREE_WORKSPACES`（Web 服务自己的配置指针；不能按 `FLOWTREE_` 前缀整体排除，因为被测代码可能读取同前缀变量，Codex 的反例就是如此）。

## 2. 启动与使用

```sh
.venv/bin/pip install -r requirements.txt          # 含 uvicorn
cp config/workspaces.example.yaml .flowtree/workspaces.yaml   # 按本机路径修改 (已为本机写好 life-piggy-bank)
.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000
# 打开 http://127.0.0.1:8000/stories
```

页面选项：显示稳定 ID（默认弱化）、展开全部分支、仅看未通过/未覆盖、重新读取（只读；重新比较基线，不执行测试）。深链参数：`/stories?all=1&ids=1&risk=1&open=<STEP-/CASE- ID>&run=1#/<工作区>/<故事>`。

## 3. 接口（全部 GET；POST/PUT/PATCH/DELETE 均 405）

```
GET /api/workspaces
GET /api/workspaces/{ws}/stories
GET /api/workspaces/{ws}/stories/{story}?refresh=
GET /api/workspaces/{ws}/attempts/{run}/{story}/{entry}
GET /api/workspaces/{ws}/attempts/{run}/{story}/{entry}/artifacts/{plugin_report|junit|stdout|stderr}
GET /stories
```

故事详情（节选，真实数据；`ws=life-piggy-bank`，`story=SAV-001`）：

```jsonc
{
  "story": {"id": "SAV-001", "title": "克制记录响应丢失后确认原请求", "actor": "已登录用户", "digest": "sha256:9729…", "open_questions": []},
  "summary": {"units_total": 6, "complete": false, "incomplete_reasons": ["…"]},
  "totals": {"total": 6, "automation": {"passed": 0, "not_run": 2, "unmapped": 4, …},
             "outdated": 2, "never_run": 0, "rule_pending": 0, "human_unverified": 6, "attention": 6, "bad": 0},
  "flow": [
    {"id": "STEP-02", "action": "填写并提交一笔克制记录", "unit": {"rule": "draft", "implementation": "unchecked", "automation": "unmapped", "human": "none", …},
     "branches": [
       {"id": "CASE-01", "kind": "recovery", "condition": "服务器处理成功但客户端未收到响应",
        "continuation": {"type": "rejoin", "target": "STEP-03", "target_action": "查看记录结果"},
        "unit": {"automation": "not_run",
                 "entries": [{"entry": "M-SAV-REPLAY", "run_id": "run_20261110T085059_44b57ed7",
                              "last_result": "passed", "validity": "stale", "counts_for_current": null,
                              "aspects": {"story": "same", "mapping_entry": "same", "worktree": "same", "runtime": "same",
                                          "verifier": "same", "env_id": "same", "environment": "changed"},
                              "changed_env_names": ["PATH", "…"], "changed_env_count": 40,
                              "tests": [{"nodeid": "tests/test_savings_flow.py::…", "outcome": "passed"}],
                              "exit_code": 0, "command_clean": true,
                              "ref": {"run": "run_…", "story": "SAV-001", "entry": "M-SAV-REPLAY"}}]}}],
     "branch_summary": {"total": 2, "outdated": 1, "never_run": 0, "bad": 0, "rule_pending": 0, "attention": 2, "automation": {…}}}],
  "context": {"checked_at": "…", "python": "…/backend/venv/bin/python",
              "execution_context": {"env_names": ["DATABASE_URL", "ENVIRONMENT", "PYTHONDONTWRITEBYTECODE"], "git_excludes_configured": true},
              "validity_overview": {"current": 0, "stale": 4, "unknown": 0},
              "recheck": {"can_determine_validity": true, "undetermined_aspects": [], "workspace_problems": [], "note": "…"}},
  "evidence_problems": [], "command_failures": []
}
```

## 4. 页面语义（任务书 A/B 的落实）

- **默认纵向主流程**：每步一张卡片，自上而下；稳定 ID 默认隐藏（详情和"显示稳定 ID"可见）。
- **`+` 分支**：每步旁显示 `+ N 个分支` 与风险概况；展开后逐个分支显示类型、条件、预期，`end` 显示"本次操作到此结束"，`rejoin` 显示"处理后汇合到第 N 步「动作」"。**折叠不改变统计**：失败/错误/阻塞、待更新、未执行、未映射、规则待确认的数量始终在折叠行上。
- **四个维度分开**：规则（草稿/待确认）、实现（未检查）、自动验证、人工；无单一完成百分比，页头给出分母（已定义 N · 本次通过 · 待更新 · 未映射 · 规则仍为草稿 · 人工未验收）和"整体未完成"的原因。
- **三件事分开**：
  1. **最近一次执行的结果**（`last_result`、run、时间、命令、nodeid、退出码）；
  2. **证据对当前上下文是否仍适用**（`validity` + 七个维度逐项"一致/不同/无法确认" + 检查时间与上下文）；
  3. **当前能否判定**（`recheck.can_determine_validity`，配置/解释器/盐缺失时为否）。
  非 `current` 的证据在页面上显示为"待更新"，并写明"存在历史结果(通过)，但不适用于当前上下文，不计为本次通过"——不与"从未执行"混淆，也不当作通过。
- **未映射**：明确写"尚未接入 FlowTree 映射。这不表示项目缺少测试，也不是业务缺陷"。
- **详情抽屉**：场景→映射条目→真实 nodeid 与逐测试结果→run→命令/工作目录/rootdir/运行时/基线/验证器→四个原始产物（读取时复核 sha256，被改动则拒绝显示，409）。整条命令的失败（含未被映射的失败测试）单独列出。
- **只读性**：只有 GET；证据库以只读方式打开；缺环境盐时不创建；对从未验证过的项目读取不会创建 `.flowtree`。环境配置只暴露变量**名称**，值（包括执行上下文里的值）不出现在任何响应里。

## 5. 真实数据结果（Life-Piggy-Bank 原仓库证据，run `run_20261110T085059_44b57ed7`）

页面（及 `/api/…/stories/*`）读取该批 4 条真实证据，在**本机 Web 服务的环境**下的结果：

| 故事 | 已定义 | 本次通过 | 待更新 | 未映射 | 条目有效性 | 整体 |
|---|---:|---:|---:|---:|---|---|
| SAV-001 | 6 | 0 | 2 | 4 | 4 条均 stale | 未完成 |
| TASK-A-001 | 6 | 0 | 3 | 3 | 同上（共 4 条证据） | 未完成 |
| TASK-B-001 | 7 | 0 | 4 | 3 | 同上 | 未完成 |

- 9 个已映射单元显示为"待更新"，**不是失败**；`last_result` 均为 passed，exit 0，无 evidence_problems、无 command_failures。
- 原因：七个维度里只有"环境变量配置"不同——故事、映射条目、环境标识、**工作区代码**、**运行时与依赖**、验证器版本都"一致"（工作区代码一致说明执行上下文里的 git excludes 配置已正确复现）。不同的是 Web 服务进程的整个环境变量集合与 Codex 执行时的 shell 不同（40 个变量，页面只显示名称）。这是预期的诚实结果：我没有改环境摘要或忽略该差异来换取绿灯。
- 因此**目前页面上没有任何一个"本次通过"**。要确认 current，须在与执行时相同的环境里重检（`flowtree story status …` 或重新 `verify`）。这是一个需要决定的设计问题，见第 8 节。
- 只读核对：读取前后目标项目的全部源码（tracked + 非忽略 untracked 逐文件哈希）、`.flowtree/` 内全部文件、HEAD、普通 `git status` 完全一致（只有原有的 `?? .flowtree/`）。

## 6. 实际验证（单批计数，不相加）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/implementation -q` | **281 passed**，0 skipped，0 failed（约 134 秒）。含 B1 的 247 项回归（未改动）+ 本批新增 34 项 |
| `.venv/bin/python -m pytest tests/independent -q`（Codex，未改动） | **33 passed**，0 skipped，0 failed |

本批新增 34 项：
- `test_b2_stories_api.py`（29）：列表与详情结构；`end`/`rejoin` 与 `target_action`；四维独立与分母；折叠摘要在从未执行时仍显示 2 个"未执行"；真实证据 → nodeid/run/产物追溯；产物被改动→409；改源码→"待更新"但历史保留；环境差异只暴露变量名且值不泄露、工作区声明一致的执行上下文后恢复 current；解释器不存在→有效性未知且 `can_determine_validity=false`；最新 manifest 损坏→error 不回退；未映射失败单独呈现；两个故事同名条目互不覆盖；**读取前后被测项目逐文件快照完全一致**；从未验证的项目读取后不创建任何文件；写方法全部 405；浏览不会运行被测代码（测试文件里放了会写文件的代码，读取后该文件不存在）；标识符校验与路径穿透；配置校验；页面不含外部依赖/写请求/`innerHTML`/`eval`。
- `test_b2_page_render.py`（5）：**真实 Chrome** 渲染最终 DOM，检查纵向顺序、折叠时分支数量与概况仍在、展开后 `end`/`rejoin` 文案、`show-ids` 开关、详情抽屉含 nodeid/run/有效性/产物哈希核对、"未映射不是缺陷"文案、过期证据显示"待更新"且"本次通过 0"、风险过滤。无 Chrome 时整组明确跳过（环境缺失，不是通过）。

另做了人工截图核对（无头 Chrome，截图在本机 scratchpad，不入库），发现并修复：抽屉里 `null`/`[object HTMLDivElement]` 渲染缺陷、英文原因与中文维度重复、整体未完成原因为英文。

**未能验证（如实）**：浏览器里真正点击 `+`/抽屉/复选框的交互没有自动化覆盖——上述渲染测试通过深链参数驱动状态，点击事件处理器仅经代码审查和 `node --check`；深色模式样式未能在浏览器中验证（无头 Chrome 未应用该参数）；仅在 Chrome 上看过，窄屏/Safari 未验证；`frontend/` 与旧页面未触碰。

## 7. 任务书 C：未映射场景的缺口登记

先读了样本项目的既有测试（只读，未运行）。**"尚未映射"本身不是缺陷。** 分类：A=已有测试待接入（后端，可直接映射 exact nodeid）；B=已有测试待接入（Flutter，需客户端适配器）；C=断言不足/待核对；D=真实未覆盖；E=需要设备/目标环境。本批**未发现 D 类**，也未改动任何映射或样本项目。

| 单元 | 分类 | 已有测试线索 | 说明 |
|---|---|---|---|
| SAV-001.CASE-02 修改输入后重提须重放原 Key 与原 payload | **B**（强） | `test/savings_controller_test.dart` “5. TOCTOU idempotent replay: …修改输入，必须使用原 Key 与原 payload 重放”；`test/savings_closed_loop_test.dart` 的 3 条同主题 widget 用例 | 服务端侧另有 `backend/tests/test_savings_flow.py::test_savings_idempotency_payload_mismatch_returns_409`，但不覆盖"客户端先确认原请求"，不能单独映射该场景 |
| SAV-001.STEP-02 保留唯一 Key 与原输入 | **B** | `savings_closed_loop_test.dart` “存入操作生成 Idempotency-Key 并在网络失败重试时严格复用该 Key” | 同上，需 Flutter 适配器 |
| SAV-001.STEP-01 打开弹窗可填分类/金额/备注 | **B**（强度待核对） | `savings_closed_loop_test.dart` 打开弹窗的 widget 用例（约 467/1010 行） | 需读断言确认是否断言了三个输入项 |
| SAV-001.STEP-04 离页重进进度与记录一致 | **C** | 后端 `test_savings_flow` 有存入后查询；客户端未见专门的"离页重进"用例 | 后端持久化有线索，客户端重进需核对，之后才能归类 |
| TASK-A-001.CASE-02 完成后重复提交不重复发奖 | **A**（强） | `backend/tests/test_tasks_slice.py::test_self_discipline_task_vertical_slice`：断言重复提交 409、A 分仍为 10.00、账本仅 1 条；执行者为无关系新用户 | 可立即映射 exact nodeid（Codex 维护映射）。客户端 409 拦截另有 `task_vertical_slice_test.dart` “重复提交保护” |
| TASK-A-001.STEP-01 无关系用户可进入 A 任务创建 | **B** | `test/task13_onboarding_and_relationship_direction_test.dart` “零关系用户打开 CreateTemplateDialog 默认 A 类并支持成功创建” | 需 Flutter 适配器 |
| TASK-A-001.STEP-04 退出再进入完成状态/积分一致 | **C** | 同一后端测试在完成后查询 `/auth/me`、账本；未见客户端"退出再进入"用例 | 同 SAV STEP-04 |
| TASK-B-001.CASE-02 重提后查询提交版本，首次凭证保留 | **A（已映射的测试其实已覆盖）** | Codex 已映射的 `test_family_tasks_flow.py::test_task_closed_loop_assignment_submission_and_approval` 第 366–395 行断言：`submit_version` 1/2、v1 的凭证与驳回原因保留、v2 为新凭证、审批人与局外人 403 | **无需新测试**：只需 Codex 复核后把 `M-B-REVIEW` 的 `covers` 增加该场景（映射为 Codex 所有，我未改） |
| TASK-B-001.STEP-04 查看结果与提交历史；审批后才增加有效进度；B 奖励归原发行人 | **A + C** | 同一后端测试第 363 行断言发行人账下 B=25；`test_multiple_issuers_b_points_strict_isolation`；客户端历史有 `task_history_*` Flutter 测试 | "审批后才增加有效进度"在该测试里未找到明确同名断言，需核对 |
| TASK-B-001.STEP-01 执行人打开待办任务，显示凭证输入入口 | **B** | `test/family_tasks_closed_loop_test.dart` “执行者提交 B 任务输入凭证 -> 状态流转为 submitted” | 需 Flutter 适配器 |

对下一条业务验证闭环的建议（不自动扩范围）：**先做 A 类两项**（TASK-A-001.CASE-02 与 TASK-B-001.CASE-02），它们都只需要映射已有后端测试，且能把本次 9 个"已映射单元"提高到 11；之后再决定是否做 Flutter 适配器（B 类共 5 项）。均不是缺陷修复。

## 8. 需要决定 / 遗留

1. **环境摘要的范围（最重要）**：目前环境摘要覆盖整个环境变量集合（去掉少量噪声），任何不同终端/会话都会使真实证据显示"待更新"，页面上因此看不到"有效"。选项：(a) 维持现状，约定重检必须在同一环境（页面已如实说明）；(b) 映射增加显式的 `env.include` 白名单（只绑定声明过的变量），在稳定性与保守性之间折中。(b) 会改变 B1 的有效性契约与 Codex 的反例假设（环境变量变化使旧通过失效），**不由我单方面决定**，请你和 Codex 定。
2. 页面当前不提供重检/执行/规则确认/人工验收入口（按任务书，后续另排）。`human` 恒为"未验收"，`rule` 恒为"草稿"。
3. 页面以 20 秒缓存重算；样本项目很大时每次重算工作区指纹需读取全部文件（本样本约 26MB，约 1–2 秒）。
4. 旧 `index.html` 与 `frontend/` 保持原样；`frontend/` 缺入口文件的问题未处理，建议另行决定是否清理。
5. 本批改动、`.flowtree/workspaces.yaml`（本机配置）均未提交；`.flowtree/` 与运行产物不入库。

## 9. Codex 第二批独立验收：B2-01 / B2-02 修复

依据 `docs/BATCH_02_INDEPENDENT_REVIEW.md`。本轮范围固定为这两项；环境摘要按 Codex/用户的选择采用**方案 (a)**，维持现有摘要契约，不加白名单，本批不加重检或执行入口。页面真实点击、窄屏、深色样式已由 Codex 在真实 Chrome 中核对（第 6 节"未能验证"的几项因此关闭，其中真实手机/Safari 仍未验证）。未提交。

| 编号 | 修复 | 位置 |
|---|---|---|
| B2-01 manifest 不可信时仍返回其伪造产物 | `read_artifact` 现在遵守记录自带的完整性结论：只要该尝试存在任何完整性问题（manifest 与索引哈希/状态不一致、索引行缺失、身份与位置不符等），该尝试的**所有**产物一律 409，`detail` 说明原因，不能用 manifest 自己记录的哈希来证明产物。详情接口仍返回诊断，不把它同时当作已核对证据。完好记录照常可读，读取不修改目标文件。 | `flowtree/view.py:read_artifact` |
| B2-02 配置切换后混用旧项目缓存 | 缓存键由 `ws.id` 改为 `cache_key(ws)`：工作区 id、项目根、解释器、故事/映射路径、执行上下文环境（名称+值，仅用于键，不存储、不输出）、git excludes。配置任一项变化即不命中，不依赖手动刷新；同一 id 的旧配置结果在写入新结果时被淘汰（缓存不无限增长）。20 秒内同配置缓存与 `refresh=true` 行为保持。 | `flowtree/view.py:cache_key/get_state` |

### 9.1 实现方回归（`test_b2_stories_api.py` 新增 10 项，与 Codex 反例构造不同）

- B2-01：伪造 stdout 并把 manifest 哈希改成与伪造文件一致（不更新索引）→409 且响应中不含伪造内容、同一尝试的其他产物也 409、详情有诊断、该场景显示 error、另一条目的完好记录仍 200；索引状态被改/索引行被删→409；完好产物 200 且读取不改变文件内容与 mtime。
- B2-02：同一 workspace id 先后指向两个不同项目（故事标题不同、只有一个有证据）→详情、列表、工作区列表都不混用；`python`/`env`/`git_excludes`/`mappings` 四种配置变化各自使缓存失效（执行上下文一致时是 current，变更后不再得到旧的 current）；同配置 20 秒内只构建一次、`refresh` 绕过缓存、同一 id 缓存条目数保持 1。

变异核对：临时撤销两处修复后，实现方新增的 7 项与 Codex 的 2 项反例共 9 项失败；还原后通过。

### 9.2 验证（单批计数，不相加）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/implementation -q -p no:cacheprovider` | **290 passed**，0 skipped，0 failed（约 149 秒）。含 B1 的 247 项、第二批 34 项与本轮新增 9 项（含 5 项真实 Chrome 渲染测试，本机允许回环端口，全部实际执行） |
| `.venv/bin/python -m pytest tests/independent -q -p no:cacheprovider`（Codex，未改动） | **41 passed**，0 skipped，0 failed（此前 39 passed / 2 failed；原 33 项 B1/B1b 断言 + 8 项 B2 断言） |

说明：Codex 报告中实现方测试在其沙箱里有 5 项 Chrome 渲染测试因禁止绑定回环端口而报错（环境限制，不是产品断言失败）；本轮在允许本机端口的环境中这 5 项实际通过。若 Codex 的验收环境仍禁止回环端口，这 5 项需在允许端口的环境补跑，不应被记为通过。

### 9.3 遗留（未变）

人工验收/规则确认入口、重检与执行入口、真实手机与 Safari、`frontend/` 缺入口文件的处理均不在本轮范围，见第 8 节。环境摘要维持现有契约（方案 a）；稳定重检上下文需先固定执行环境，确认无关的宿主变量再逐个使用已有 `env.ignore`（会正常改变条目摘要并产生新证据）。

