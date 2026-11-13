# 第八批提交清单（只列清单，未暂存、未提交、未 push）

日期：2026-11-11。FlowTree HEAD `9fb737c`，LPB HEAD `6391ce2`。两个仓库此刻都没有已暂存内容。
提交说明末尾署名沿用你此前确认的：`Co-Authored-By: Claude <noreply@anthropic.com>`（不写具体模型版本）。

## A. 样本仓库 Life-Piggy-Bank（1 个提交）

| # | 建议信息 | 文件 |
|---|---|---|
| L2 | `test(integration): two-account B-task review flow (reject, resubmit, approve) on isolated SQLite` | `test_integration/real_backend_b_review_test.dart`（新）、`test_integration/support/kit.dart`（修改，仅在 `BackendApi` 末尾追加 51 行 helper，既有 helper 未改） |

- 不含业务源码、既有测试或夹具改动（`git diff` 只有 `kit.dart` 的 51 行追加）。
- 不要加入：`.flowtree/`（运行产物）。
- 提交不会使证据失效：指纹按文件内容计算；只是证据里记录的 `git_sha` 将与新 HEAD 不同（溯源差异）。

## B. FlowTree（2 个提交，按顺序）

| # | 建议信息 | 文件 |
|---|---|---|
| F4 | `feat(stories): TASK-B-001 pre-approval invariant and real two-account integration entry` | `examples/stories/task-b-001.story.yaml`（Codex 增补不变量：待审、驳回和重提不增加有效进度、B 余额或 B 奖励流水）、`examples/mappings/task-b-001.mapping.yaml`（同步 `story_digest`，新增 `M-B-REAL-REVIEW` 条目，保留旧三个条目） |
| F5 | `docs: batch 08 US-24 plan, independent review and acceptance records` | `docs/BATCH_08_US24_PLAN.md`、`docs/BATCH_08_US24_CODEX_REVIEW.md`、`docs/BATCH_08_US24_INDEPENDENT_ACCEPTANCE.md`、`docs/BATCH_08_COMMIT_MANIFEST.md` |

- F4 的故事与映射必须同一个提交：映射的 `story_digest` 要与故事文本一致，拆开会让中间状态加载失败。
- 本批没有改 `flowtree/` 框架代码，也没有改测试（`tests/`）。
- 提交顺序建议 LPB 的 L2 先于 F4（映射引用 `test_integration/real_backend_b_review_test.dart`），两个仓库互相独立，不影响 FlowTree 自身测试。

## C. 排除与提交前整理

| 项 | 建议 |
|---|---|
| `docs/BATCH_08_US24_MAPPING_DRAFT.yaml` | 已核对与正式条目解析后相等；重复草案已删除、不提交，方案引用已更新到正式条目，并增加最新验收记录指引 |
| `docs/flowchart.mermaid` | 排除（一直是未跟踪的非本批产物） |
| `.flowtree/`（两个仓库） | 排除 |
| `scratchpad/lpb_copy` 等变异副本与日志 | 在会话临时目录，不在两个仓库内，不涉及提交 |
| 机器路径 | 已核对：本批新增/修改的故事、映射、测试、kit 与文档中没有本机绝对路径 |

## D. 已在文档里更正的说法

- "后端变异做不了" 已改为 "尚未做（可把后端目录指向临时副本，无需改原仓库）"。
- 上一批四个提交已完成并核对（LPB 6391ce2；FlowTree 4d97278、384c9f2、9fb737c），方案文档里不再有"仍等确认"的说法。

## E. 不由本清单代签

规则确认（Q-10 等）、人工验收仍保留。证据边界不变：SQLite 非 MySQL；非冷启动、非真机；发行人界面没有被驱动，"发行人审批由测试模拟"的客户端证据保留为较低层级；后端侧"待审就发奖"类变异检查尚未做，阶段性断言对后端缺陷的有效性目前只有间接支撑。本清单记录提交前范围；用户已要求按小任务及时进行本地提交，不 push。
