# 第一批故事与部分测试映射

这些是 Codex 根据 Life-Piggy-Bank 既有规则整理的三条 **draft**，不是已确认记录，也不是已执行证据。来源路径默认相对于样本仓库；SAV-001 另引用 FlowTree 自己的故事规范。没有引用 US-44（它是成果使用，不是克制记录）。

校验与计划：

```sh
.venv/bin/python -m cli.main story validate examples/stories --mappings examples/mappings --json
.venv/bin/python -m cli.main story plan examples/stories --mappings examples/mappings --json
```

初版 plan 返回 exit 0、issues=[]、executed=false：19 个单元，9 个已映射未执行、10 个未映射、0 个通过、19 个人工未验收。三个故事均未完成。

## 来源及实际断言范围

| 故事 | 已阅读的真实测试入口 | 当前映射范围 |
|---|---|---|
| TASK-A-001 | `backend/tests/test_task13_onboarding_and_relationship.py::test_task13_zero_relationship_user_self_task_full_loop` | 创建后查询待办、完成后 A=15.00 与账本对账；没有证明客户端入口、离页重进或重复领奖 |
| TASK-A-001 | 同文件 `test_task13_zero_relationship_user_b_task_rejected` | 无关系向他人指派 B 任务被拒绝 |
| TASK-B-001 | `backend/tests/test_family_tasks_flow.py::test_task_closed_loop_assignment_submission_and_approval` | 提交待审、驳回原因、重提待审、审批成功及陌生人越权拒绝；没有据此声称已验证版本历史与不提前发分等全部不变量 |
| SAV-001 | `backend/tests/test_savings_flow.py::test_savings_idempotency_key_deposit_and_yield` | 同 Key 与 payload 重放、余额及仅一条记录；不是实际弱网端到端旅程，也未证明客户端保存原输入 |

已阅读 `test/savings_controller_test.dart` 中“5. TOCTOU idempotent replay”用例，存在原 Key/原输入恢复的客户端断言；B1b 不解析 Flutter，因此 SAV-001.CASE-02 继续未映射。家庭重提版本、客户端入口、重新进入等也继续显式未映射，不为提高覆盖数关联不充分的测试。

## 后续执行条件

映射 `cwd: backend` 相对于**明确指定的 Life-Piggy-Bank 项目根目录**，不是 FlowTree 根目录或映射目录。B1b 的最终调用参数由 Claude 冻结；没有显式项目根目录时不要直接运行这些样例。

`argv: [python, -m, pytest, ...]` 中 python 必须解析到样本项目已有的合适隔离环境，并记录实际解释器路径；不能用 FlowTree 的 `.venv` 冒充已具备样本依赖。所读样本 `backend/tests/conftest.py` 使用每测试独立 SQLite 内存库和 ASGI transport；这里只核对文件，没有启动该环境。

金额、次数和时钟属于示例夹具。映射关联的是可读到的断言范围；示例中的 clock 尚未注入样本测试，运行时不得声称测试已采用该时钟。涉及时间边界的验证需另有注入与证据。故事不变量也没有独立可验证 ID，当前部分映射不能证明所有不变量已被执行覆盖，这是后续契约完善项。

映射已钉住当前故事摘要，故事变化后须由映射所有者审阅更新，不能在执行时偷偷重算钉住值。

## 后端增量接入（2026-11-10）

已补 TASK-A-001.CASE-02 和 TASK-B-001.CASE-02，原项目最小真实执行 2 passed。该轮19个单元中已映射11、未映射8；映射数不等于当前有效通过数。见 [增量记录](../docs/BACKEND_MAPPING_INCREMENT_2026-11-10.md)。

## Flutter正式增量（2026-11-10）

接入SAV-001.STEP-02、TASK-A-001.STEP-01、TASK-B-001.STEP-01，三个真实文件40 passed。该轮已映射14/19；另外两个客户端候选待补断言。见[第四批独立报告](../docs/archive/batches/BATCH_04_INDEPENDENT_REVIEW.md)。须使用Flutter固定PATH及HOME声明的pinned工作区，不拼接后端上下文的通过数。

## 请求构造断言补强后（当前）

正式接入新增测试的6个精确名称，补齐SAV-001.STEP-01与CASE-02。同一pinned上下文运行全部9个映射入口：51 passed，16/19单元本次有效，剩余3项离页重进未映射。运行 `run_20261110T121733_36ce89d9`。规则确认、人工验收仍未完成，详见第四批独立报告末节。
