# 两项已有后端测试的增量接入

2026-11-10，Codex。FlowTree 基线 `b279f1d`；两个第二批提交已核对，源码与290/41复验时一致。本次仅修改映射与说明，未重跑全量。

- TASK-A-001.CASE-02：新增 M-A-REPEAT，关联 `tests/test_tasks_slice.py::test_self_discipline_task_vertical_slice`，验证重复提交拒绝、余额不变、账本不重复。
- TASK-B-001.CASE-02：扩展 M-B-REVIEW 的 covers，复用 `tests/test_family_tasks_flow.py::test_task_closed_loop_assignment_submission_and_approval`，验证重提版本和旧凭证保留。

原项目实际执行 **2 passed、0 failed/skipped**，两个命令 exit 0，changed_during_run=false，无证据问题；产物哈希已核对。这两个场景在本轮执行上下文中均 passed。映射校验通过。

运行：`run_20261110T102425_51f63838`。
证据：原项目 `.flowtree/runs/run_20261110T102425_51f63838/<story>/<entry>/`。
命令、结果和源码前后哈希：FlowTree 本机 `.flowtree/integrations/lpb-mapping-2026-11-10/`。

三条故事仍为19个单元，**已映射11、未映射8**；11是映射数量，不是本轮全部有效通过的数量。没有更改旧条目来消除环境差异，Web服务需按自身上下文如实判断有效性。故事仍为草稿，人工未验收。

Life-Piggy-Bank HEAD仍为 `a4cc0a023cf2e3d4a96ba87c828616ed747db0f3`，源文件前后哈希一致，Git状态仍只有原有 `.flowtree/`。只使用既有SQLite内存夹具，未触碰真实库或部署。未提交、未push。

下一步：先补稳定执行上下文，再决定Flutter适配；复杂设计和实现交给Claude。无需再次审计已关闭问题。
