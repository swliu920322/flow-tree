# FlowTree 智能项目状态电路引擎｜技术数据契约与接口规范 (Data Contract)

> **文档优先级提示（2026-11-10）**：涉及用户故事、验收证据、最小代码修复，以及"Agent 自报状态即点亮/通过"的条款，以 `docs/STORY_ACCEPTANCE_SPEC.md` 和 `docs/SESSION_HANDOFF_2026-11-10.md` 为准；本文其余内容仍作为现有设计参考。

| 文档版本 | 状态 | 编写角色 | 面向对象 | 最终定稿时间 |
| :--- | :--- | :--- | :--- | :--- |
| **v1.0.0** | 规范已锁定 (Baseline Locked) | 架构师 / Tech Lead | 后端研发、前端研发、外部 Agent / 测试平台对接方 | 2026-10-29 |

---

## 1. 核心设计契约准则

1. **结构不可侵犯性（Structural Immutability for External Systems）**：
   - 外部 Agent 或自动化系统只能修改**状态类字段**（`status`, `review.logicVerified`, `actualHours`, `reviewComments`）。
   - 严禁外部系统在 PATCH 请求中篡改树结构字段（`nodeId`, `parentId`, `deps`, `name`），违者由后端网关直接 `400 Bad Request` 拦截。
2. **两段式验收状态机（Two-Stage Verification State Machine）**：
   - 逻辑状态（客观断言）与终审状态（人类体验）解耦，形成受控单向跃迁闭环。
3. **确定性渲染输出（Deterministic Canvas Projection）**：
   - 后端对任意 `(Project, ViewId)` 计算出的输出，是具备确定性边电气状态（`energized`, `dormant`, `blocked`）的标准 Graph JSON。

---

## 2. Pydantic 数据模型定义

### 2.1 基础枚举定义
```python
from enum import Enum

class NodeType(str, Enum):
    ROOT = "root"
    MODULE = "module"
    PAGE = "page"
    FEATURE = "feature"
    API = "api"
    COMPONENT = "component"
    CASE = "case"
    DATA_PIPELINE = "data_pipeline"

class NodeStatus(str, Enum):
    PENDING_DEV = "pending_dev"        # 待开工 (灰色休眠)
    DEVING = "deving"                  # 开发中 (黄色呼吸)
    LOGIC_VERIFIED = "logic_verified"  # 逻辑已通过 (亮蓝待终审)
    REVIEW_PASS = "review_pass"        # 终审通过·导通 (翠绿常亮)
    REVIEW_REJECT = "review_reject"    # 驳回/阻塞 (警示红)
    ARCHIVED = "archived"              # 已归档

class CircuitState(str, Enum):
    DORMANT = "dormant"      # 断电休眠
    ENERGIZED = "energized"  # 通电导通 (绿色粒子动画)
    BLOCKED = "blocked"      # 短路熔断 (红色故障连线)
```

### 2.2 节点完整契约模型 (Node Schema)
```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class ExternalBinding(BaseModel):
    system: str = Field(..., description="外部系统标识，如 test_platform, jira, github")
    targetType: str = Field(..., description="目标类型，如 api_test, unit_test, pr")
    targetId: str = Field(..., description="外部目标唯一标识符")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict, description="透传参数，如请求路径/方法")

class ReviewState(BaseModel):
    logicVerified: bool = Field(default=False, description="客观逻辑是否已由机器/Agent验证")
    logicVerifiedBy: Optional[str] = Field(None, description="逻辑验证者标识")
    logicVerifiedAt: Optional[datetime] = None
    humanSignOff: bool = Field(default=False, description="人类是否终审签字")
    humanSignOffBy: Optional[str] = None
    humanSignOffAt: Optional[datetime] = None
    comments: List[str] = Field(default_factory=list, description="审查与驳回意见")

class NodeModel(BaseModel):
    nodeId: str = Field(..., description="节点全局唯一ID")
    parentId: Optional[str] = Field(None, description="树状父节点ID")
    nodeType: NodeType = Field(default=NodeType.FEATURE)
    name: str = Field(..., max_length=100)
    description: Optional[str] = ""
    tags: List[str] = Field(default_factory=list, description="业务与岗位透镜标签")
    assignRole: Optional[str] = None
    assignee: Optional[str] = None
    status: NodeStatus = Field(default=NodeStatus.PENDING_DEV)
    deps: List[str] = Field(default_factory=list, description="强前置依赖节点ID列表")
    acceptanceCriteria: List[str] = Field(default_factory=list, description="客观逻辑验收标准")
    externalBinding: Optional[ExternalBinding] = None
    estimateHours: float = Field(default=1.0, ge=0)
    actualHours: float = Field(default=0.0, ge=0)
    outputs: List[str] = Field(default_factory=list, description="代码文件、文档或PR地址")
    review: ReviewState = Field(default_factory=ReviewState)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
```

### 2.3 动态视角定义模型 (Perspective Schema)
```python
class PerspectiveModel(BaseModel):
    viewId: str = Field(..., description="视角唯一ID，如 view-analytics")
    name: str = Field(..., description="视角显示名称")
    description: Optional[str] = ""
    icon: Optional[str] = "Eye"
    includeTags: List[str] = Field(default_factory=list, description="命中的标签集(OR关系)")
    includeNodeTypes: List[NodeType] = Field(default_factory=list)
    bypassUnmatched: bool = Field(default=True, description="是否穿透非匹配中间节点保持链路")
```

---

## 3. 状态机流转与电路导通推导算法

### 3.1 状态机合法跃迁表

```
                    ┌────────────────────────────────────────┐
                    │                                        ▼
[pending_dev] ──> [deving] ──> [logic_verified] ──> [review_pass] ──> [archived]
       ▲                             │
       │                             ▼
       └─────────────────────── [review_reject]
```

| 当前状态 | 允许跃迁至 | 触发源 | 业务前置条件 |
| :--- | :--- | :--- | :--- |
| `pending_dev` | `deving` | 人工 / 自动 | **强约束**：所有 `deps` 节点状态必须为 `review_pass` |
| `deving` | `logic_verified` | 外部 Agent / 测试平台 | 客观测试断言 100% 通过 |
| `deving` | `review_reject` | 外部 Agent / 开发者 | 测试失败、构建失败或自测不通过 |
| `logic_verified` | `review_pass` | **仅限人类审查员** | 人工终审签字通过，主观体验合格 |
| `logic_verified` | `review_reject` | **仅限人类审查员** | 主观体验驳回，并强制填写 `comments` |
| `review_reject` | `deving` | 开发者 | 打回后重新启动开发修复 |
| `review_pass` | `archived` | PM | 项目发布归档 |

### 3.2 导线通电状态推导算法 (Edge Circuit Rule)
对于连接 `Source -> Target` 的依赖导线：
- **`CircuitState.ENERGIZED` (通电发光+粒子流)**：当且仅当 `Source.status == review_pass` 且 `Target.status != pending_dev`。
- **`CircuitState.BLOCKED` (短路熔断+红色警示)**：当 `Source.status == review_reject` 或前置链路存在未解决故障。
- **`CircuitState.DORMANT` (断电休眠)**：其余情况（前置未完成，下游未激活）。

---

## 4. 外部对接与 PATCH 接口规范

### 4.1 状态更新 PATCH 接口契约
- **URL**: `PATCH /api/projects/{projectId}/nodes/{nodeId}/status`
- **Headers**: `Content-Type: application/json`
- **Payload 示例**:
```json
{
  "status": "logic_verified",
  "actualHours": 2.5,
  "outputs": ["src/api/auth.py"],
  "review": {
    "logicVerified": true,
    "logicVerifiedBy": "agent_test_runner_v1",
    "comments": ["所有自动化用例通过 (4/4 passed), 响应时间 35ms"]
  }
}
```

### 4.2 严格安全与校验规则
1. **反结构篡改检查**：Payload 中若包含 `deps`, `parentId`, `name`, `nodeType`，接口立即返回 HTTP `422 Unprocessable Entity` 并拒绝更新。
2. **状态跃迁拦截**：若试图从 `pending_dev` 直接修改为 `review_pass`（跳过逻辑验证），抛出 `IllegalStateTransitionError`。
3. **数据广播**：更新成功后，系统持久化落盘，并自动向 WebSocket 广播 `{ event: "NODE_STATUS_CHANGED", data: { ... } }`。
