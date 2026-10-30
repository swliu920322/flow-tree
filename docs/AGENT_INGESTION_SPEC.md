# FlowTree 面向 AI Agent 的数据自报协议与指令模板规范 (Agent Ingestion Spec)

> **定位**：FlowTree 不是复杂的企业 ERP 或工单系统，而是一个**「Agent-Native 状态电路交付引擎」**。
> 研发执行完全由 AI Agent（如 Claude Code, Devin, Cursor, Gemini, 自动化 CI 脚本）自主推进；Agent 遵循本规范自动向 FlowTree 汇报数据，系统自动点亮电路，为企业与客户提供零认知负担的进度全景交付。

---

## 一、 Agent 与 FlowTree 的协作闭环

```
┌────────────────────────────────────────────────────────┐
│  1. 企业 / 客户 (Client / Stakeholder)                │
│     提出业务诉求 / 关键里程碑终审 / 查看实时通电大盘     │
└───────────────────────────┬────────────────────────────┘
                            │ 需求输入
                            ▼
┌────────────────────────────────────────────────────────┐
│  2. AI Agent 研发集群 (Coding & QA Agents)             │
│     • 阶段一：依据本规范，自动拆解出 0交叉瀑布流 JSON  │
│     • 阶段二：自主编码，客观运行单测与真机断言         │
│     • 阶段三：调用 PATCH 探针自动自报推进状态          │
└───────────────────────────┬────────────────────────────┘
                            │ 结构化数据自报 (REST / JSON)
                            ▼
┌────────────────────────────────────────────────────────┐
│  3. FlowTree 状态电路中枢 (FlowTree Engine)            │
│     • 严格因果导通计算（前面不通，后面失压）          │
│     • 模块根节点百分比自动变色                        │
│     • 自动提取卡点责任链与个人工位                     │
└───────────────────────────┬────────────────────────────┘
                            │ 实时只读交付投屏
                            ▼
┌────────────────────────────────────────────────────────┐
│  4. 企业高管 / 客户交付大盘 (Enterprise View)          │
│     • 一眼看清：哪个模块已全通 (绿)，哪个在施工 (黄)    │
│     • 清晰无争议，0 汇报扯皮，全自动化呈现真实进展     │
└────────────────────────────────────────────────────────┘
```

---

## 二、 面向 Agent 的极简自报数据契约 (Minimal Agent JSON Schema)

Agent 拆解项目时，**必须且仅需**输出以下标准化 JSON 结构：

```json
{
  "projectId": "proj-your-client-slug",
  "projectName": "项目商业名称",
  "description": "一句话讲清项目业务目标与交付边界",
  "version": "1.0.0",
  "stage": "dev_probing", 
  "perspectives": [
    {
      "viewId": "view-all",
      "name": "🎬 全局业务全景 (自顶向下瀑布)",
      "includeTags": []
    }
  ],
  "nodes": [
    {
      "nodeId": "ROOT-PROJECT",
      "parentId": null,
      "nodeType": "root",
      "name": "⚡ 项目一级总电源中枢",
      "description": "项目核心能量母线",
      "tags": ["project_root"],
      "assignee": "架构总线",
      "status": "review_pass",
      "deps": []
    },
    {
      "nodeId": "MOD-1",
      "parentId": "MODULE-AUTH",
      "nodeType": "module",
      "name": "📦 模块一：用户鉴权与账号中枢",
      "description": "【模块变电站】随内部完成度自动计算颜色",
      "tags": ["module_root", "module_auth"],
      "assignee": "Agent-Backend",
      "status": "review_pass",
      "deps": ["ROOT-PROJECT"]
    },
    {
      "nodeId": "TASK-101",
      "parentId": "MODULE-AUTH",
      "nodeType": "feature",
      "name": "01. 用户一秒免密登录与令牌发放",
      "description": "【用户视点】手机端输入账号，极速进入工作台",
      "tags": ["module_auth", "step_1"],
      "assignRole": "全栈实现",
      "assignee": "Agent-Fullstack",
      "status": "review_pass",
      "deps": ["MOD-1"],
      "acceptanceCriteria": [
        "冷启动 1.5 秒内完成，JWT Token 签名合规",
        "自动化单元测试 100% 通过"
      ],
      "estimateHours": 6.0,
      "actualHours": 4.5,
      "review": {
        "logicVerified": true,
        "humanSignOff": true,
        "comments": ["【CI 跑通】Token 签发测试用例全部通过"]
      }
    }
  ]
}
```

### 节点类型与状态硬约束（Agent 必须严格遵守）
1. **`nodeType` 枚举**：
   * `root`：全系统仅 1 个总电源节点，`deps` 必须为空 `[]`。
   * `module`：每个模块的变电站根节点，`deps` 必须指向 `["ROOT-PROJECT"]`。
   * `feature`：具体业务交互步骤，`deps` 指向前置模块或步骤，形成自顶向下的瀑布流。
2. **`status` 状态枚举**：
   * `pending_dev`：尚未开始开发（冷灰熄灭）。
   * `deving`：Agent 正在编码或攻坚中（金黄色呼吸）。
   * `logic_verified`：**Agent 已完成代码并跑通自动化测试/单测断言**，点亮科技天蓝，等待人类或企业终审放行。
   * `review_pass`：终审通过，强劲绿光电流导通，向下游注入电能！
   * `review_reject`：测试断言失败或人工驳回，警示红闪烁，下游全线失压断电。

---

## 三、 面向 AI Agent 的标准系统提示词模板 (Agent Prompt Template)

你可以将下面这段提示词，直接喂给任何 Coding Agent（如 Claude Code, Devin, Cursor, AutoGPT 等）：

```markdown
# FlowTree 研发与自报 Agent 任务指令

你是一个高级全栈工程 Agent。在执行当前项目的研发任务时，你需要严格按照 FlowTree 状态电路规范组织任务并汇报进展。

## 你的三大核心职责：

### 职责一：项目初始化与瀑布流拆解 (DAG Generation)
当开始一个新项目或新需求时，请按照真实用户使用的先后顺序，将项目拆解为自顶向下的“零交叉瀑布流 (Zero-Crossing Planar Waterfall)”：
1. 创建唯一的 `ROOT-PROJECT` 项目电源根节点；
2. 为每个核心业务领域创建 `MOD-X` 模块变电站节点（`deps: ["ROOT-PROJECT"]`）；
3. 在每个模块内部，按照用户真实操作顺序串联步骤，每个步骤明确写清：
   - `name`: 动作直观（如 "01. 打开App免密登录"）
   - `description`: 描述用户视角体验
   - `acceptanceCriteria`: 客观验收标准 DoD（至少包含 1 条自动化断言和 1 条体验断言）
   - `assignee`: 负责执行该步骤的 Agent 或角色标识

### 职责二：代码实现与客观断言 (Implementation & Logic Verification)
当你正在编写某个步骤的代码时：
1. 将该节点状态更新为 `deving`（黄色呼吸），表示正在编码攻坚；
2. 代码完成后，必须编写并运行单元测试或自动化脚本；
3. **关键准则**：只要你的自动化测试跑通了，将该节点状态更新为 `logic_verified`（亮蓝灯），并在 `review.comments` 中附带客观测试输出结果（如 "12/12 单元测试通过，耗时 0.4s"）；
4. 严禁自己伪造人类终审签字。对于关键交互，保留给企业或架构师终审。

### 职责三：轻量 API 状态自报 (State Reporting Protocol)
在任务推进过程中，你可以通过简单的 HTTP PATCH 请求向 FlowTree 报告当前节点的状态：

```bash
PATCH /api/projects/{projectId}/nodes/{nodeId}/status
Content-Type: application/json

{
  "status": "logic_verified",
  "reviewComments": ["【Agent-CI】自动化切片测试已跑通，API 返回 200 OK"],
  "source": "coding_agent"
}
```

FlowTree 会自动基于你的自报数据，推导全链路通电状态、计算模块完成百分比，并在企业大盘中实时渲染出翠绿色流动电流！
```

---

## 四、 呈现给企业的精简交付视角（企业无需配置任何东西）

通过本模式，企业客户不需要学习任何软件，不需要录入任何工单，企业看到的只有一个**只读交付屏幕（Executive Dashboard）**：

1. **宏观进度一眼清**：
   * 模块一（个人自律）：`83%` 冲刺天蓝
   * 模块二（情侣互勉）：`50%` 施工金黄
   * 模块三（克制存钱）：`100%` 翡翠绿满电
2. **零阻力真实透明**：
   * 哪个步骤跑通了，绿灯亮起，电流向下流动；
   * 哪个步骤卡住了，水流截断，红灯报警并标明“卡点原因与受影响下游”；
   * 客户完全没有“进度黑盒焦虑”，项目天然具备工业级可信度。
