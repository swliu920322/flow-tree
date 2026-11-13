# FlowTree 文档入口

更新：2026-11-14。目的：让当前工作能找到依据，保留历史而不误当现行规则。**第 1～10 批的 30 份过程文档已移入 [批次归档](archive/README.md)，修复路径与链接；不改写历史结论，不改变既有确认状态。**

## 先读这三处

1. [设计原则与负责人决定](DESIGN_PRINCIPLES.md)：已决定的产品方向与边界，也列明待决项。具体章节注明来源，不代表所有提案已批准。
2. [第一版交付卡](FIRST_RELEASE_CARD.md)：Codex 整理的最小交付范围建议，待负责人确认；用来判断是否可交付，不是已实现说明。
3. **下一步实施看 [P1-1 任务书](steps/P1_1_TASK.md)**：限定最小项目入口与离线 AI 调用验证，不包含草稿和真实收费请求。[AI 核心规划](AI_CORE_PLAN.md) 第 2 版与 [Codex 评审](AI_CORE_PLAN_REVIEW.md) 保留全局方向；后续阶段不因本批安排自动获准。

## 当前工作材料

| 主题 | 文档 | 如何使用 |
|---|---|---|
| 最小接入、调用与草稿 | [B1 提案](B1_PROJECT_INIT_AI_PROPOSAL.md)、[设计复核](B1_PROJECT_INIT_AI_REVIEW.md) | 技术提案及审查依据；不能把“待确认”当成负责人已批准 |
| 故事与验收最初规范 | [故事验收规范](STORY_ACCEPTANCE_SPEC.md) | 基础参考，正文自称讨论草案；与后来的明确决定冲突时按来源/日期核对，不整篇当成已落地 |
| 待决需求 | [待决问题](OPEN_QUESTIONS.md)、[规则确认记录](RULE_CONFIRMATION_US23_US24.md) | 前者并未汇总全部未决项；后者仅限明确确认范围，不能扩大为整份故事确认 |
| 样例材料入口 | [examples 说明](../examples/README.md) | 有故事、映射及历史增量说明；其中“当前”是各段写作时点，不当作实时证据状态 |

出现冲突时，先区分“负责人明确决定／评审建议／当时实现／当前运行事实”。不要因为文件写了“锁定”“定稿”或日期较新，就自动赋予负责人批准或覆盖全部旧契约的效力。代码也不能反过来证明业务需求正确。

## LPB 样本验收：事实与历史

| 要找什么 | 去哪里 |
|---|---|
| 人工结论与范围 | [US-23/US-24 验收清单](ACCEPTANCE_CHECKLIST_US23_US24.md) |
| 人工发现与处置建议 | [US-24 发现](MANUAL_FINDINGS_US24.md)：事实、建议、正式决定分别读 |
| 已确认的核心规则 | [规则确认](RULE_CONFIRMATION_US23_US24.md)，未决附加项仍未决 |
| 当前操作与启动材料 | [业务验收手册](ACCEPTANCE_GUIDE_BUSINESS.md)、[隔离环境启动说明](MANUAL_ACCEPTANCE_SETUP.md)、[启动复核](MANUAL_ACCEPTANCE_SETUP_REVIEW.md)；页面指引在 [guides](../examples/guides/) |
| 接入项目写过什么 | [侵入事实清单](INTRUSION_FACTS_LPB.md)：写作时点的事实，后续变动须另核对 |
| 指引功能复验 | [第一步](MANUAL_ACCEPTANCE_GUIDES_STEP1_REVIEW.md)、[第二步](MANUAL_ACCEPTANCE_GUIDES_STEP2_REVIEW.md)；看各文件末尾的修复后结论 |

文档中的运行编号是历史证据入口，不保证此刻仍适用当前项目。当前自动化状态用同一执行上下文的 CLI/API 只读重检；人工操作结论不由自动重检代签。本次索引没有重新核对实时状态。

## 归档与历史参考：追溯时再读

批次历史已搬入 archive，其余参考文件保持原位。以下是阅读分组，不宣布所有条款失效。

- **批次历史：** [archive/batches/](archive/batches/)，含第 1～10 批任务书、交付、独立反例、提交清单；[归档目录](archive/README.md)逐项列出。按批次找实现演变，不拿“未提交”“当前通过”等当实时状态。
- **接入与视觉历史：** [后端映射增量](BACKEND_MAPPING_INCREMENT_2026-11-10.md)、[真实项目接入](REAL_PROJECT_INTEGRATION_2026-11-10.md)、[页面视觉复核](STORIES_VISUAL_INDEPENDENT_REVIEW_2026-11-12.md)。
- **讨论与交接快照：** [2026-11-10 交接](SESSION_HANDOFF_2026-11-10.md)、[2026-11-12 负责人讨论](OWNER_DISCUSSION_FOR_CODEX_2026-11-12.md)。后续决定可能已改变当时的下一步。
- **已实施功能的过程提案：** [人工指引页面提案](MANUAL_ACCEPTANCE_PAGE_PROPOSAL.md)、[方案复核](MANUAL_ACCEPTANCE_PAGE_REVIEW.md)。结果看对应交付和复验，不只读最初提案。
- **早期电路/多角色设计参考：** [PRD](PRD.md)、[项目提案](PROJECT_PROPOSAL.md)、[数据契约](DATA_CONTRACT.md)、[Agent 自报规范](AGENT_INGESTION_SPEC.md)、[项目配置规范](PROJECT_CONFIG_SPEC.md)、[WBS](WBS_PLAN.md)。部分涉及旧视图或旧自报机制；仅作参考，不能替代现有真实证据契约，更不能据此信任自报通过。
- **用户自有文件：** [flowchart.mermaid](flowchart.mermaid)，本轮不整理、不修改、不代为提交。

## 后续怎样维护，避免再次变乱

- 新工作先更新交付卡/任务范围，再引用技术提案；不要每轮复制一份新的“总体设计”。
- 现行原则与提案可修订，保留状态及变更来源；历史交付保留原事实，用后续链接说明。
- 每个小批次收口时更新入口或步骤卡，记录实现、证据、限制及下一步；提案没有实施时明确写待评审。
- 已完成批次归档的原路径与新路径见 [归档目录](archive/README.md)。继续归档时先核对链接与正文引用，不夹带改写历史或删除材料。
