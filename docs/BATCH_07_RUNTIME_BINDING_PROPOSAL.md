# 最小方案：把"伴随运行时"（后端解释器与依赖）绑定进证据有效性（仅设计，未改框架）

> 本文保留写作时点的过程状态；最新执行与清理复验以 [US-23 独立验收记录](BATCH_07_US23_INDEPENDENT_ACCEPTANCE.md) 为准。原映射草案已由 `examples/mappings/task-a-002.mapping.yaml` 取代。

日期：2026-11-11。针对 Codex 指出的正式点亮前缺口：TASK-A-002 的联调测试由 Flutter runner 执行，但真正被测的后端跑在另一个 Python 解释器/依赖里；现有 Flutter runtime digest 只覆盖 SDK、`pubspec.lock`、`package_config`，**后端 venv 的解释器或依赖变化不会使旧证据失效**。日志里记版本不算绑定。

## 1. 现状与可复用的位置（已核对代码）
- `Runner.runtime(...) -> RuntimeProbe(digest, info, error)` 是唯一的运行时探测入口；digest 进入基线的 `runtime_digest`。
- 同一个探测在三处被调用：`execution.current_baseline`（执行前；`service`/`status` 的只读重检也经由它）、`execution` 里执行前的 `runner.runtime`（blocked 判定）、`classify` 的 `runtime_now()`（执行后）。执行前后不一致 → 本次作废（"runtime" 变化）；重检不一致 → `stale`；探测报错 → 执行 `blocked` / 重检 `unknown`。
- 所以**只需让"组合后的运行时 digest"替换这三处的 `runner.runtime` 结果**，不用新增失效机制。

## 2. 方案（最小）
**配置分两层，机器路径不进可移植文件：**
- 映射 entry（可移植）新增可选字段 `companions: [<名字>]`，如 `[backend-python]`。
- 工作区配置（本机、已忽略）新增 `companions: {backend-python: {kind: python, interpreter: <绝对路径>}}`。

**一个公共函数**（建议放 `flowtree/runners/__init__.py` 旁，不进具体 runner）：
```
runtime_with_companions(runner, entry, exe, python, env, cwd, project_root, companions) -> RuntimeProbe
  = 主探测 runner.runtime(...)
  + 对每个声明的伴随项调用其 kind 的只读探测
  digest = H(主 digest, [(名字, 伴随 digest)…])  # 未声明 companions 时返回原 digest, 不变
```
三处调用点改为调用它；runner 本身与 `classify` 不变（`runtime_now` 自动带上伴随项）。

**伴随项 kind 用小注册表**（与 runner 注册方式一致）。第一个 kind `python` 的只读探测：用声明的解释器、`-I`、清洗环境、有超时、不联网、不安装，输出
`realpath(sys.executable)`、`sys.version`、已安装发行包的 `名称==版本`（按名称排序）。核心只处理不透明 digest 与 error，**没有 Python 特例散落在核心里**。

**语义（与现有一致）：**
| 情形 | 结果 |
|---|---|
| 执行前探测失败/解释器不存在 | 执行 `blocked`，不产生证据 |
| 执行前后伴随 digest 不同 | 本次运行作废（同 runtime 变化） |
| 重检时 digest 与证据不同（升级/重装/换 venv） | `stale` |
| 重检探测失败 | `unknown`（不静默放过） |
| 未声明 companions 的 entry | digest 与现在逐字节相同（旧证据不受影响，需黄金用例固定） |
| 页面/API | 只读：不启动测试；只暴露伴随项**名称与"变了/未变/未知"**，不暴露路径值 |

## 3. 诚实的限制
- 覆盖"解释器路径、版本、已装包名称+版本"。同版本包被原地改文件不会被发现；不覆盖操作系统库、数据库服务端（SQLite 随 Python 标准库，由解释器版本覆盖）。
- 不替代"源码指纹"：后端源码已在 worktree 指纹里（被 git 跟踪）。
- 仍不是 MySQL；是否另需 MySQL 证据是单独的产品/验收问题。

## 4. 需要的测试（实现时，不是现在）
1. 在**临时 venv 副本**里升级/安装一个包 → 旧证据 `stale`；还原 → 恢复 `current`。
2. 重检时解释器路径不存在 → `unknown`；执行前缺失 → `blocked`。
3. 执行期间改变伴随项（受控夹具）→ 运行作废。
4. 未声明 companions 的既有映射 digest 不变（黄金值）。
5. 配置层：伴随项路径只在工作区配置；映射里出现字面路径被校验拒绝；API 响应不含路径值。
6. 探测不联网/不写项目目录（沿用 `-I`、清洗环境、超时）。

## 5. 在实现之前的使用约束
TASK-A-002 的映射草案（`examples/mappings/task-a-002.mapping.yaml`（正式替代文件，以下描述保留原写作时点））在该方案落地前**不应点亮**；若要提前试跑，只作为"手工试跑记录"，页面上不得显示为通过证据。方案需要改动映射 schema（`companions` 字段）与工作区配置，故先提交设计，等 Codex 评审后再实现。

## 6. 实现状态（2026-11-11，按 Codex 的五条约束）
已实现：`flowtree/companions.py`（新）、`context.py`/`workspace.py`（声明）、`mapping.py`（`companions` 字段）、`execution.py`（三处调用点）。未提交。

| 约束 | 实现 |
|---|---|
| 1 绑定实际解释器 | 工作区声明必须带 `bind_env`；声明的解释器按**绝对路径字符串**与子进程环境里该变量比较（不解析符号链接：两个 venv 可指向同一基础解释器）。不一致/未设置 → 执行 blocked、重检 unknown；报错不回显路径值 |
| 2 缓存键与执行后重探 | 缓存键含伴随项配置与实际绑定值；执行后对伴随项**全新探测**并与 runner 报告的实际运行时组合，执行后基线也改用新缓存，不复用执行前摘要 |
| 3 兼容与 blocked | 未声明时运行时摘要与条目摘要逐字节不变（黄金用例）；缺配置/未知名称/探测失败 → blocked/unknown；blocked 尝试照常落盘，并取代较早的通过 |
| 4 SQLite | 探测加入 `sqlite3.sqlite_version`；同版本包被原地修改仍是已声明限制 |
| 5 不承诺逐项展示 | 只保存组合摘要；清单里的 `runtime.companions` 仅有版本/计数，不含路径，也不用于逐项比较 |

测试（`tests/implementation/test_companions.py`，15 项，全部离线：`venv --without-pip` + 伪造 `.dist-info`）：实际解释器不匹配被阻塞并落盘；依赖变化 → stale（页面/CLI 一致），旧通过不再点亮；执行期间改变伴随依赖 → 本次作废（基线指纹置空）；旧映射摘要不变；解释器消失 → unknown/blocked；Web 重检与 CLI 一致且不暴露解释器路径。
回归：原 479 项仍全部通过（`tests/implementation` + `tests/independent`）。
变异核对：忽略伴随项 / 去掉绑定检查 / 执行后复用执行前摘要 / 条目摘要总含 companions 键，各自被至少一项测试抓住（6/2/1/1 项失败）。
映射草案已补 `companions: [backend-python]`（`examples/mappings/task-a-002.mapping.yaml`（正式替代文件，以下描述保留原写作时点），可加载）。工作区配置示例见 `config/workspaces.example.yaml`。
