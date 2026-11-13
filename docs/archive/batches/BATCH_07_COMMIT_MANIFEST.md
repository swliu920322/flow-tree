# 第六、七批提交清单（只列清单，未暂存、未提交、未 push）

日期：2026-11-11。FlowTree HEAD `d75e594`，LPB HEAD `199b285`。两个仓库此刻都没有已暂存内容。
提交说明末尾沿用你此前确认的署名：`Co-Authored-By: Claude <noreply@anthropic.com>`（不写具体模型版本）。

## A. 样本仓库 Life-Piggy-Bank（1 个提交）

| # | 建议信息 | 文件 |
|---|---|---|
| L1 | `test(integration): real client-backend integration (isolated SQLite) and two-check-in story` | `test_integration/support/real_backend.dart`、`test_integration/support/kit.dart`、`test_integration/real_backend_a_task_test.dart`、`test_integration/real_backend_two_checkins_test.dart` |

- 全部是新增测试文件，不含业务源码、既有测试或夹具改动；`git diff` 为空。
- **不要加入**：`.flowtree/`（运行产物，已被 FlowTree 工作区排除）。
- 提交不会使证据失效：工作区指纹按文件内容（含未跟踪文件）计算，与是否提交无关；`git_sha` 仅作溯源。但提交后 HEAD 变化，正式证据里记录的 `git_sha` 会与新 HEAD 不同（只是溯源差异）。

## B. FlowTree（建议 3 个提交，按依赖顺序）

| # | 建议信息 | 文件 |
|---|---|---|
| F1 | `feat(companions): bind backend interpreter and dependencies into runtime evidence validity` | 实现：`flowtree/companions.py`（新）、`flowtree/context.py`、`flowtree/workspace.py`、`flowtree/mapping.py`、`flowtree/execution.py`、`flowtree/baseline.py`（pytest 探测加 `-B`）、`config/workspaces.example.yaml`；测试：`tests/implementation/test_companions.py`、`tests/independent/test_b7_companions_review.py`；文档：`docs/BATCH_07_RUNTIME_BINDING_PROPOSAL.md`、`docs/BATCH_07_COMPANIONS_INDEPENDENT_REVIEW.md` |
| F2 | `feat(stories): TASK-A-002 two-check-in story and integration mapping` | `examples/stories/task-a-002.story.yaml`、`examples/mappings/task-a-002.mapping.yaml` |
| F3 | `docs: batch 06/07 delivery, story sources, US-23 walkthrough and acceptance records` | `docs/BATCH_06_CLAUDE_DELIVERY.md`、`docs/BATCH_07_STORY_SOURCES_AND_QUESTIONS.md`、`docs/BATCH_07_US23_WALKTHROUGH.md`、`docs/BATCH_07_CODEX_STORY_REVIEW.md`、`docs/BATCH_07_US23_INDEPENDENT_ACCEPTANCE.md`、`docs/BATCH_07_COMMIT_MANIFEST.md` |

- F1 先于 F2：映射里的 `companions` 字段需要 F1 的 schema 才能加载。
- `flowtree/baseline.py` 的 `-B` 改动来自 Codex 的复验（B7 复验已通过），归 F1。
- 验证状态：全量 499 项通过（`tests/implementation` + `tests/independent`，含 B7-01/02 修复后）；B7-03 修复在 LPB 侧，独立复验已通过。

## C. 已核对的排除与文档处理

| 项 | 建议 |
|---|---|
| `docs/flowchart.mermaid` | 排除（此前一直未跟踪，非本批产物） |
| `docs/drafts/task-a-002.mapping.yaml` | 内容与正式映射一致，已删除重复草案，不提交；正文引用已转向正式替代文件 |
| `.flowtree/`（两个仓库） | 排除 |
| 过时的状态表述 | 保留历史过程描述；已在上述三份过程文档首部增加最新状态指引，指向 `BATCH_07_US23_INDEPENDENT_ACCEPTANCE.md`。没有改写历史测试结果 |
| 机器路径 | 已核对：可移植文件（实现、测试、映射、示例配置）中没有本机绝对路径；本机路径只在 `.flowtree/` 忽略配置与带日期的验收记录里 |

## D. 未解决 / 不由本清单代签

规则确认（Q-04～Q-10 等）、人工验收、Q-SAV-NAV-001 仍保留；FlowTree 超时下仅"进程/端口/临时目录"已验证，SIGKILL 下进程内清理不可能，是明确的已知限制。需要你授权后我才会暂存和提交。
