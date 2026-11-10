# 当前版本在 Life-Piggy-Bank 原仓库的接入验收

日期：2026-11-10。执行方：Codex。结论：当前 FlowTree 已在原仓库通过三条故事的四个现存 pytest 映射入口，证据落盘和后续状态读取有效；这是部分后端接入验收，不是重新完成样本全部测试或人工验收。

## 1. 基线与范围

- FlowTree：`b5aca56cbc5f45fc8cdb7fefb3ef9634f49e33c7`，实现提交 `1e9b21746748a88aa9a754029a68667b748e8deb`；开始时仅用户已有 `docs/flowchart.mermaid` 未跟踪。
- 目标原仓库：`/Users/liushengwei/taylors_project/Life-Piggy-Bank`，HEAD `a4cc0a023cf2e3d4a96ba87c828616ed747db0f3`。开始/结束普通 Git 状态均只有 `?? .flowtree/`，不是 clean workspace 的声明。
- 使用 FlowTree 已提交的 `examples/stories/`、`examples/mappings/`，没有修改故事或扩大测试映射来提高覆盖数。
- 被测解释器：样本现有 `backend/venv/bin/python`，Python 3.13.5、pytest 9.1.1；没有安装依赖或更改 venv。
- 本次在**原仓库**执行，不是之前 scratchpad 副本的那一批；不借用旧通过。

已读样本 `backend/tests/conftest.py`：每个测试独立 SQLite 内存 engine、dependency override、ASGI transport；本次指定精确 nodeid，没有运行 MySQL/E2E/部署入口。

## 2. 执行环境与命令

本轮显式设置 `ENVIRONMENT=test`、`DATABASE_URL=sqlite+aiosqlite:///:memory:`、`PYTHONDONTWRITEBYTECODE=1`。夹具继续使用其自建的每测试内存库；显式 DATABASE_URL 让默认应用 engine 也不指向真实数据库。没有启动服务或应用 lifespan。

样本 `.flowtree/` 未被 Git 忽略，证据增长会使工作区指纹自我变化。本轮通过仅对子进程生效的 `GIT_CONFIG_COUNT/GIT_CONFIG_KEY_n/GIT_CONFIG_VALUE_n`，把 `core.excludesFile` 指向 FlowTree 本机运行目录中的文件，内容为 `.flowtree/`。原项目 `.gitignore`、`.git/info/exclude` 及 Git 配置均未改。**以后重检需保持同一执行上下文**；不能删去该环境配置仍声称证据 current。

按顺序执行：

```sh
.venv/bin/python -m cli.main story validate examples/stories --mappings examples/mappings --json
.venv/bin/python -m cli.main story plan examples/stories --mappings examples/mappings --json
.venv/bin/python -m cli.main verify examples/stories --mappings examples/mappings \
  --project-root /Users/liushengwei/taylors_project/Life-Piggy-Bank \
  --python /Users/liushengwei/taylors_project/Life-Piggy-Bank/backend/venv/bin/python \
  --mapped-only --json
.venv/bin/python -m cli.main story status examples/stories --mappings examples/mappings \
  --project-root /Users/liushengwei/taylors_project/Life-Piggy-Bank \
  --python /Users/liushengwei/taylors_project/Life-Piggy-Bank/backend/venv/bin/python --json
```

以上四条均在同一受控环境中运行，exit 0、ok=true。plan 只列计划；verify 实际启动四次 pytest；status 独立读取已有证据，没有再跑测试。

## 3. 实际结果

运行 ID：`run_20261110T085059_44b57ed7`。

| 条目 | 真实 nodeid（相对 backend rootdir） | 本次结果 |
|---|---|---|
| SAV-001/M-SAV-REPLAY | `tests/test_savings_flow.py::test_savings_idempotency_key_deposit_and_yield` | 1 passed，exit 0 |
| TASK-A-001/M-A-COMPLETE | `tests/test_task13_onboarding_and_relationship.py::test_task13_zero_relationship_user_self_task_full_loop` | 1 passed，exit 0 |
| TASK-A-001/M-A-RELATION | 同文件 `test_task13_zero_relationship_user_b_task_rejected` | 1 passed，exit 0 |
| TASK-B-001/M-B-REVIEW | `tests/test_family_tasks_flow.py::test_task_closed_loop_assignment_submission_and_approval` | 1 passed，exit 0 |

四次 attempt 均 completed、command_clean=true、changed_during_run=false；无 evidence_problems、command_failures 或未映射失败。各 manifest 所列原始产物哈希吻合，verifier=`flowtree-b1b/2;plugin/1;report/1`，均有 env_digest。随后 status 中所有关联条目 validity=current。

| 故事 | 已定义单元 | 本次自动通过 | 未映射 | 人工未验收 | 整体完成 |
|---|---:|---:|---:|---:|---|
| SAV-001 | 6 | 2 | 4 | 6 | 否 |
| TASK-A-001 | 6 | 3 | 3 | 6 | 否 |
| TASK-B-001 | 7 | 4 | 3 | 7 | 否 |
| 合计 | 19 | 9 | 10 | 19 | 否 |

**4 项真实测试**和**9 个被覆盖单元**不是两个可相加的测试计数。规则仍 draft；客户端入口、离页重进、版本历史等缺口继续未映射，不把后端通过扩写成完整用户旅程通过。样例时钟未注入项目夹具，也不声称测过其时间边界。

这里“未映射”表示尚未接入 FlowTree 的这批映射，并不意味着样本项目没有对应测试，更不推翻其既有验收结论。本轮验收对象是 FlowTree 的接入与证据链。

## 4. 原始证据与完整性

原项目证据根：

`/Users/liushengwei/taylors_project/Life-Piggy-Bank/.flowtree/runs/run_20261110T085059_44b57ed7/<story>/<entry>/`

FlowTree 本机接入记录：`.flowtree/integrations/lpb-current-2026-11-10/`，包含实际执行脚本、环境策略、四条命令的 argv/退出码/JSON/stderr、运行摘要、源码前后哈希及产物完整性核对。均为本机运行产物，不入库。

完整性检查结果：

- 目标项目 tracked 与非忽略 untracked 源文件逐文件哈希前后一致，HEAD 未变。
- 原 `.flowtree/` 下已有模板和脚本文件哈希未变；新增本次 runs、环境盐和 SQLite 证据索引。
- 原项目普通 Git 状态仍只有已有的 `?? .flowtree/`；运行产物未被提交。
- 没有修改业务源码、夹具、业务配置或依赖，没有触碰真实数据库、部署或宿主操作。

本次没有重跑 FlowTree 的 247/33 项回归，因为其实现未变；也没有重新运行 Life-Piggy-Bank 的整套历史审计。

## 5. 建议的下一批：真实故事与证据页面

本节为下一批实施建议，不表示页面已实现。现在已有来自原项目的当前版本真实证据，下一步优先让用户看得见：

1. 读取同一故事/映射/证据服务，展示三条故事的纵向正常主流程；技术 DAG 保留为独立视图。
2. 节点旁 `+` 展开边界和恢复分支，准确显示 end/rejoin；收起后保留失败、待定、未执行与未映射数量。
3. 分别展示规则、实现、自动验证、人工验收；默认弱化 ID，详情可看稳定 ID、真实命令、nodeid、run_id、原始报告与有效性。
4. 展示本次 19/9/10 的分母与缺口，不显示全故事已验收，也不生成一份模拟绿灯数据替代本轮证据。
5. 页面首先做只读查看，不把浏览操作变成执行测试/批准规则/人工签字。后续执行入口另外安排。

协作建议：Claude 负责最小只读后端适配与前端纵向流程实现；Codex 负责本项目样本映射、独立 API/状态断言、浏览器分支展开与折叠风险摘要验收。开始前明确公共响应字段及文件归属，避免两边同时改 Schema。

特别注意：Web 服务自身的环境不一定等于被测执行环境。UI 必须区分“最近一次执行的结果”“最近一次有效性检查及时间”“当前目标环境能否确认”；不能把服务进程的环境当作已确认的测试环境，也不能为保留绿灯忽略环境差异。不具备重检上下文时显示待更新/未知，不伪造 current。

这一批不必先接 BYOK、自主修复循环、完整 MCP、Flutter 解析或重开样本业务审计。客户端已有测试可先登记为待接入，之后再完善适配。
