# 第三批交付记录（Claude）：统一工作区执行上下文

日期：2026-11-10。任务书：`docs/BATCH_03_CLAUDE_TASK_2026-11-10.md`。基线 HEAD `b279f1d`，本批改动**未提交**。不修改 `examples/`（含 Codex 新增的两项映射）、`tests/independent/`、`docs/flowchart.mermaid`。

## 1. 解决的问题

此前 CLI `verify`/`story status` 靠手工参数和宿主环境，Web 用 `Workspace.execution_env` 叠加覆盖项，二者拼装环境的逻辑不同；且两边都复制整个 `os.environ`，所以即使覆盖项相同，继承的宿主变量不同，环境摘要就不同、证据只能显示"待更新"。本批做到：**同一份工作区配置、同一个解析函数，决定实际传给子进程/运行时探测/git 的环境**；并提供显式选择的固定模式，**先约束实际环境，再对实际环境取完整摘要**。

## 2. 命令与配置

新增（旧命令 `verify`、`story status`、`story validate/plan` 原样保留，行为不变）：

```
flowtree workspace list                     [--config 路径] [--json]
flowtree workspace context <id>             解析后的上下文: 名称/策略/问题, 不含任何值; 有问题时退出 1
flowtree workspace status  <id>             只读重检 (不执行, 不写被测项目)
flowtree workspace verify  <id> [--mapped-only] [--entry STORY/ENTRY ...]   真实执行并保存证据
```
`workspace` 可简写 `ws`。故事、映射、项目根、解释器、环境、git 排除规则全部来自工作区配置（`--config`，缺省 `FLOWTREE_WORKSPACES` 或 `.flowtree/workspaces.yaml`）。`verify` 的退出码规则与旧命令相同。

`execution_context` 字段（示例见 `config/workspaces.example.yaml`）：

| 字段 | 含义 |
|---|---|
| `mode` | `inherit`（默认，行为与此前逐项一致）或 `pinned` |
| `env` | 字面值，非机密。疑似密钥名（SECRET/TOKEN/PASSWORD/CREDENTIAL/PRIVATE/API_KEY/ACCESS_KEY）或值含 URL 内嵌凭据 → **配置校验直接拒绝**，提示改用 `env_from_host` |
| `env_from_host` | 变量名列表。值在运行/重检时从**启动进程的宿主环境**读取，不写入配置、manifest、API 响应、页面或日志；缺失则执行 `blocked`、重检 `unknown`，**不静默退回宿主环境**（inherit 下同样要求存在） |
| `pinned_path` | 仅 pinned：固定的 `PATH`，默认 `/usr/bin:/bin:/usr/sbin:/sbin` |
| `git_excludes_file` | 可选 git 排除规则 |

未知字段、`mode` 非法、`env`/`env_from_host` 重名、非 pinned 却设 `pinned_path` 均为配置错误。

## 3. 统一解析（`flowtree/context.py`）

`resolve(spec, host)` 是唯一一处拼装环境的函数；`execution.run_attempt`、`current_baseline`（执行前后基线）、运行时探测、git 指纹、`service.collect_state`（CLI 状态与 Web 只读重检）全部调用它。旧的 `child_env()` 保留为兼容包装。

- **inherit**：宿主环境 + `env` 覆盖项 + `git_excludes_file` 以 `GIT_CONFIG_*` 传入 + 清除 `PYTEST_ADDOPTS` + 注入插件路径 —— 与此前拼装逐项一致（测试 `test_inherit_resolution_matches_the_legacy_assembly_exactly`）。`context_digest` 恒为 `None`，所以**旧证据保持有效**。
- **pinned**：子进程环境**只有** `PATH`（固定值）+ `env` + `env_from_host` 取到的宿主变量 + `PYTHONPATH`（插件路径）；FlowTree 每次尝试再注入 `FLOWTREE_REPORT/RUN_ID/ATTEMPT_ID`（沿用既有规则，仍不进入摘要）。**未声明的宿主变量不会进入被测进程**，并由测试内断言证明。环境摘要对这份**实际环境**取 HMAC，不是对白名单字段取摘要而继续把其余变量传入。
- **git 隔离（仅 pinned）**：git 调用使用最小环境并设置 `GIT_CONFIG_NOSYSTEM=1`、`GIT_CONFIG_GLOBAL=/dev/null`，工作区指纹不再受宿主全局/系统 git 配置影响（排除规则只来自声明的 `git_excludes_file`）。
- 失败不外溢：任一必需宿主变量缺失 → `problems`；执行写入 `blocked` 且不启动任何子进程；重检把环境摘要置为 `None`（`unknown`），页面 `can_determine_validity=false` 并列出原因。

## 4. 失效与可追溯

- `Baseline` 增加可选字段 `context_digest`（对 B1 契约的唯一扩展，默认行为不变）：仅 pinned 非空 = 对 `{模式, git 隔离版本, 字面变量名集合, 宿主变量名集合, git excludes 文件内容摘要}` 取哈希，**不含任何值**。`None` 是合法取值（inherit / 旧证据缺该字段），与非空不同即 `stale`，因此换模式、改策略、改排除规则内容都会使旧证据失效，反向同理。不修改旧 manifest（测试断言多次重检后 manifest 字节不变）。
- 比较维度新增 `context`（`compare_aspects`）；页面"证据有效性"里显示为"执行上下文策略"。
- manifest 新增 `context`（模式、变量名、布尔、问题，无值）；`env_vars` 仍是名称→HMAC。
- 宿主环境不同、但上下文是 pinned：不影响（测试：不同的 HOME/LANG/无关变量/PATH 顺序/缺少其他变量，CLI 与 Web 均 `current`）；声明的字面值变化、声明的宿主变量值变化 → `stale`，并点名变量名（值不出现）。
- 缓存身份：`cache_key` 使用 `ContextSpec.identity()`（模式、字面值、宿主变量名、pinned_path、git excludes），同一工作区 id 只改上下文策略不会命中旧缓存。Web 仍是只读：只读打开证据、缺盐不创建、从未验证的项目读取后不产生任何文件（pinned 下同样有测试）。

## 5. 实际验证（单批计数，不相加）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/implementation -q -p no:cacheprovider` | **315 passed**，0 skipped，0 failed（约 169 秒）。含此前 290 项（B1/B2 回归，未改动断言）+ 本批新增 25 项；其中 5 项真实 Chrome 渲染测试本机实际执行 |
| `.venv/bin/python -m pytest tests/independent -q -p no:cacheprovider`（Codex，未改动） | **41 passed**，0 skipped，0 failed |

新增 `tests/implementation/test_b3_context.py` 25 项（真实 git 仓库 + 真实 pytest 子进程，用不同宿主环境分别驱动 CLI 与 Web）：解析与旧拼装一致；pinned 只含声明变量、不泄露值；缺必需变量两种模式都有明确问题；疑似机密的字面值被拒；旧证据（缺 `context_digest`）在 inherit 下仍 current、在 pinned 下 stale；**真实子进程内断言未声明的宿主变量未泄入**；摘要覆盖的恰好是实际传入的变量集合；机密值不出现在任何 `.flowtree` 文件、CLI 输出或 API 响应；两个不同宿主的 CLI 重检与不同宿主的 Web 重检一致；未声明变量变化不影响；字面值/宿主变量值变化→stale 并点名；缺宿主变量→执行 blocked 且无子进程、重检 unknown、Web `can_determine_validity=false`；inherit 模式行为不变且宿主变量仍影响；旧命令证据可被新命令读取为 current；模式互换双向失效；pinned 的 git 隔离使指纹不随宿主 git 配置变化；git excludes 文件内容变化→stale；缓存身份含上下文策略；pinned 下 Web 重检不写任何文件；CLI 退出码与错误；配置校验。

变异核对：让 pinned 泄入宿主变量、去掉 git 隔离、让缺失变量静默放行后，11 项测试失败；还原后全部通过。

说明：本批对 B1/B2 已有测试仅更新了 `Baseline` 构造等与新增可选字段无关的内容（无）；旧断言全部保持原样并通过，说明 inherit 默认行为未变。若 Codex 的沙箱仍禁止回环端口，5 项 Chrome 渲染测试需在允许端口的环境补跑，不能记为通过。

## 6. 真实项目运行（Life-Piggy-Bank，复用 Codex 已接入的两个隔离后端测试）

本机配置新增工作区 `life-piggy-bank-pinned`（`mode: pinned`；字面变量 `ENVIRONMENT/DATABASE_URL(sqlite 内存)/PYTHONDONTWRITEBYTECODE`；`git_excludes_file` 复用 Codex 接入记录里的文件），故事/映射为 Codex 当前工作区里的 `examples/`（未改动）。

```
flowtree workspace verify life-piggy-bank-pinned --mapped-only --entry M-A-REPEAT --entry M-B-REVIEW --json
```
run `run_20261110T103510_7e706e1e`：`TASK-A-001/M-A-REPEAT` 与 `TASK-B-001/M-B-REVIEW` 均 completed、exit 0、各 1 passed、command_clean=true，`context_problems=[]`。仅使用既有 SQLite 内存夹具，未连接真实库、未部署、未改业务源码、依赖或夹具。

**不同宿主下的重检**（`workspace status life-piggy-bank-pinned`；两个条目均为 `validity=current`、`last_result=passed`，所有维度"一致"）：

| 宿主 | 结果 |
|---|---|
| CLI：当前 shell | current / current |
| CLI：`env -i`，另一个 HOME、`LANG=C`、额外变量 | current / current |
| CLI：PATH 重排并加入无关厂商变量 | current / current |
| Web：以 `env -i`、另一个 HOME 启动的真实 uvicorn，请求 `?refresh=true` | current / current，`can_determine_validity=true` |
| 对照：继承模式工作区 `life-piggy-bank` 读取同一份最新证据 | stale（`context`、`environment` 不同）—— 预期：证据由 pinned 上下文产生 |

页面因此第一次能显示"本次通过"（pinned 工作区下这两个条目覆盖的 **6 个单元**：TASK-A-001 1 个、TASK-B-001 5 个），而不是靠放宽摘要：三条故事共 19 个单元中已映射 11、未映射 8；本次 pinned 有效 6，其余已映射的 **5 个**单元的证据来自继承模式，仍为"待更新"，需要在 pinned 上下文里重新 `workspace verify` 才会变为有效（本批未重跑，避免无谓扩大对样本项目的执行）。

**目标项目完整性**：HEAD 仍为 `a4cc0a023cf2e3d4a96ba87c828616ed747db0f3`；448 个源文件（tracked + 非忽略 untracked，不含 `.flowtree/`）的 SHA-256 与 Codex 最近一次记录（`.flowtree/integrations/lpb-mapping-2026-11-10/source-after.json`）逐一相同；`git diff` 为空；普通 `git status` 仍只有原有的 `?? .flowtree/`（新增了本次 run 的证据目录，已核对产物哈希）。我自己的第一次哈希核对曾显示"CHANGED"，原因是命令把 LPB 里未被忽略的 `.flowtree/`（含新证据）也算入，已改用 Codex 的逐文件记录精确核对，非源码变化。

原始证据位置：目标项目 `.flowtree/runs/run_20261110T103510_7e706e1e/<story>/<entry>/`；命令输出与源码前后哈希在本机 scratchpad（不入库）。

## 7. 文件清单

新增：`flowtree/context.py`、`tests/implementation/test_b3_context.py`、本文档。修改：`flowtree/workspace.py`（`mode/env_from_host/pinned_path` 与 `context()`）、`flowtree/execution.py`、`flowtree/service.py`（`ctx` 参数、`context_problems`、`aspects`/变化变量名同样输出给 CLI）、`flowtree/status.py`、`flowtree/evidence.py`、`flowtree/view.py`、`cli/main.py`、`backend/app/static/stories.js`（新维度与上下文说明）、`config/workspaces.example.yaml`。

## 8. 遗留与需要你们知道的

1. **旧的 `verify`/`story status` 命令仍是 inherit**，所以它们的证据与 pinned 工作区互相失效（上下文不同，预期行为）。要让 CLI 与 Web 稳定复用，请统一使用 `workspace` 命令，并为需要稳定的工作区选 `pinned`。
2. pinned 只保证"进入测试的环境"确定；被测项目若依赖未声明的宿主变量（例如机密）会失败/阻塞，需要把变量名加入 `env_from_host`。这次的两个 Life-Piggy-Bank 测试只需要三个字面值。
3. 机密值的识别是**名称与 URL 凭据形态的启发式**，不能保证识别所有机密；配置里的字面值仍应由使用者自行把关。
4. 页面与 Web 仍无执行/重检/签字入口；`workspace verify` 仅 CLI。`human` 恒为未验收、`rule` 恒为草稿。
5. 其余 5 个已映射单元（共 11 个已映射、6 个 pinned 有效）尚无 pinned 上下文下的证据；规则仍为草稿、人工未验收，三条故事均未完成；Flutter 适配、规则确认/人工验收录入未开始。
6. 本批改动与本机 `.flowtree/workspaces.yaml` 均未提交。
