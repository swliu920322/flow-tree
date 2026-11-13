# 历史材料：解释沿革，不安排下一步

整理日期：2026-11-14。当前入口见 [文档导航](../README.md)，具体任务见 [P1-1](../delivery/steps/P1_1_TASK.md)。旧路径见 [路径映射](PATH_MAP.md)。历史文件保留原结论及写作时点状态，只调整 Markdown 链接。

## 早期设计参考

以下材料与旧电路、自报或早期多角色规划有关；不是本批实施依据。不能仅因标题写“锁定/定稿”就视为当前契约。未冲突的背景仍可参考。

- [PRD.md](early-design/PRD.md)
- [PROJECT_PROPOSAL.md](early-design/PROJECT_PROPOSAL.md)
- [PROJECT_CONFIG_SPEC.md](early-design/PROJECT_CONFIG_SPEC.md)
- [DATA_CONTRACT.md](early-design/DATA_CONTRACT.md)
- [AGENT_INGESTION_SPEC.md](early-design/AGENT_INGESTION_SPEC.md)
- [WBS_PLAN.md](early-design/WBS_PLAN.md)
- [MANUAL_ACCEPTANCE_PAGE_PROPOSAL.md](early-design/MANUAL_ACCEPTANCE_PAGE_PROPOSAL.md)

## 交接和讨论快照

- [2026-11-10 交接](discussions/SESSION_HANDOFF_2026-11-10.md)
- [2026-11-12 负责人讨论](discussions/OWNER_DISCUSSION_FOR_CODEX_2026-11-12.md)

后来的明确决定可能改变其中的建议或“下一步”。

## 第 1～10 批过程

任务书、交付、独立反例、提交清单一起保留。正文里的旧文件清单与路径保留原样，可用路径映射查找。

| 批次 | 文档 |
|---|---|
| 01 | [第一批交付记录（Claude）：B1a 故事契约与结果真实性 + F01–F05 修复 + B1b 真实 pytest 执行](batches/BATCH_01_CLAUDE_DELIVERY.md) |
| 01 | [第一批协作安排：故事契约与真实执行证据](batches/BATCH_01_CODEX_CLAUDE_2026-11-10.md) |
| 01 | [B1a 独立复验与 B1b 接口回复](batches/BATCH_01_INDEPENDENT_REVIEW.md) |
| 02 | [第二批交付记录（Claude）：只读故事验收页面](batches/BATCH_02_CLAUDE_DELIVERY.md) |
| 02 | [给 Claude 的第二批任务：真实项目试用与故事证据页面](batches/BATCH_02_CLAUDE_TASK_2026-11-10.md) |
| 02 | [第二批独立验收：只读故事页面](batches/BATCH_02_INDEPENDENT_REVIEW.md) |
| 03 | [第三批交付记录（Claude）：统一工作区执行上下文](batches/BATCH_03_CLAUDE_DELIVERY.md) |
| 03 | [第三批任务：统一工作区执行上下文](batches/BATCH_03_CLAUDE_TASK_2026-11-10.md) |
| 03 | [第三批独立设计检查与复验](batches/BATCH_03_INDEPENDENT_REVIEW.md) |
| 04 | [第四批交付记录（Claude）：Flutter 已有测试接入](batches/BATCH_04_CLAUDE_DELIVERY.md) |
| 04 | [第四批：Flutter 已有测试接入](batches/BATCH_04_CLAUDE_TASK_2026-11-10.md) |
| 04 | [**最新状态：B4-01及两项客户端断言缺口均已关闭。第四批约定范围通过；正式整批51 passed，16/19单元本次有效，剩余3项离页重进未映射，规则与人工验收未完成。下文保留历史记录，最新证据见末节。**](batches/BATCH_04_INDEPENDENT_REVIEW.md) |
| 05 | [第五批交付记录（Claude）：成功后的页面重进与审批结果/历史](batches/BATCH_05_CLAUDE_DELIVERY.md) |
| 05 | [第五批：成功后的页面重进与审批结果/历史](batches/BATCH_05_CLAUDE_TASK_2026-11-11.md) |
| 05 | [第五批独立核对与正式映射](batches/BATCH_05_INDEPENDENT_REVIEW.md) |
| 06 | [第六批交付记录（Claude）：客户端 ↔ 真实后端联调（隔离测试，尚未接正式映射）](batches/BATCH_06_CLAUDE_DELIVERY.md) |
| 07 | [US-23 故事与断言核对](batches/BATCH_07_CODEX_STORY_REVIEW.md) |
| 07 | [第六、七批提交清单（只列清单，未暂存、未提交、未 push）](batches/BATCH_07_COMMIT_MANIFEST.md) |
| 07 | [伴随运行时独立复验：暂缓正式映射](batches/BATCH_07_COMPANIONS_INDEPENDENT_REVIEW.md) |
| 07 | [最小方案：把"伴随运行时"（后端解释器与依赖）绑定进证据有效性（仅设计，未改框架）](batches/BATCH_07_RUNTIME_BINDING_PROPOSAL.md) |
| 07 | [第七批·第一步：故事来源与待确认清单（Claude）](batches/BATCH_07_STORY_SOURCES_AND_QUESTIONS.md) |
| 07 | [US-23 正式映射与独立执行核对](batches/BATCH_07_US23_INDEPENDENT_ACCEPTANCE.md) |
| 07 | [第七批·首个正式故事 US-23 完整示范（Claude）](batches/BATCH_07_US23_WALKTHROUGH.md) |
| 08 | [第八批提交清单（只列清单，未暂存、未提交、未 push）](batches/BATCH_08_COMMIT_MANIFEST.md) |
| 08 | [US-24 独立断言核对：先补客户端证据](batches/BATCH_08_US24_CODEX_REVIEW.md) |
| 08 | [第八批 US-24 独立核对与正式执行](batches/BATCH_08_US24_INDEPENDENT_ACCEPTANCE.md) |
| 08 | [第八批：US-24 故事与断言方案及实现记录（未提交）](batches/BATCH_08_US24_PLAN.md) |
| 09 | [第九批独立核对：验证层级与运行器展示](batches/BATCH_09_INDEPENDENT_REVIEW.md) |
| 10 | [第十批独立核对：发行人审批界面联调](batches/BATCH_10_ISSUER_UI_INDEPENDENT_ACCEPTANCE.md) |
| 10 | [第十批：发行人侧真实界面联调方案（仅方案；只读核对，未写测试、未改框架、未提交）](batches/BATCH_10_ISSUER_UI_PLAN.md) |
