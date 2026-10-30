from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

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
    LOGIC_VERIFIED = "logic_verified"  # 客观逻辑已通过 (亮蓝待人工终审)
    REVIEW_PASS = "review_pass"        # 终审通过·导通 (翠绿常亮，向下游供电)
    REVIEW_REJECT = "review_reject"    # 驳回/阻塞 (警示红)
    ARCHIVED = "archived"              # 已归档

class CircuitState(str, Enum):
    DORMANT = "dormant"      # 断电休眠 (灰色)
    ENERGIZED = "energized"  # 通电导通 (绿色发光 + 动态电流粒子)
    BLOCKED = "blocked"      # 短路熔断 (红色故障连线)

class BulbState(str, Enum):
    OFF = "off"                    # 灰色断电
    BREATHING_YELLOW = "breathing" # 黄色呼吸灯
    GLOWING_BLUE = "blue_waiting"  # 亮蓝待终审
    ILLUMINATED_GREEN = "green_on" # 翡翠绿完全通电
    ALERT_RED = "red_alert"        # 警示红闪烁

class ExternalBinding(BaseModel):
    system: str = Field(..., description="外部系统标识 (test_platform, jira, github, agent)")
    targetType: str = Field(..., description="目标类型 (api_test, unit_test, pr)")
    targetId: str = Field(..., description="外部唯一标识")
    meta: Dict[str, Any] = Field(default_factory=dict, description="额外参数，如请求路径/方法")

class ReviewState(BaseModel):
    logicVerified: bool = Field(default=False, description="客观逻辑是否已由机器/Agent验证")
    logicVerifiedBy: Optional[str] = Field(None, description="逻辑验证来源")
    logicVerifiedAt: Optional[str] = None
    humanSignOff: bool = Field(default=False, description="人类是否终审签字")
    humanSignOffBy: Optional[str] = None
    humanSignOffAt: Optional[str] = None
    comments: List[str] = Field(default_factory=list, description="审查与反馈意见")

class NodeModel(BaseModel):
    nodeId: str = Field(..., description="节点唯一ID")
    parentId: Optional[str] = Field(None, description="父节点ID")
    nodeType: NodeType = Field(default=NodeType.FEATURE)
    name: str = Field(..., max_length=100)
    description: Optional[str] = ""
    tags: List[str] = Field(default_factory=list, description="视角过滤与业务标签")
    assignRole: Optional[str] = None
    assignee: Optional[str] = None
    status: NodeStatus = Field(default=NodeStatus.PENDING_DEV)
    deps: List[str] = Field(default_factory=list, description="前置依赖节点ID列表")
    acceptanceCriteria: List[str] = Field(default_factory=list, description="验收标准")
    externalBinding: Optional[ExternalBinding] = None
    estimateHours: float = Field(default=1.0, ge=0)
    actualHours: float = Field(default=0.0, ge=0)
    outputs: List[str] = Field(default_factory=list, description="产出物路径")
    review: ReviewState = Field(default_factory=ReviewState)
    updatedAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class PerspectiveModel(BaseModel):
    viewId: str = Field(..., description="视角唯一标识")
    name: str = Field(..., description="显示名称")
    description: Optional[str] = ""
    icon: Optional[str] = "Eye"
    includeTags: List[str] = Field(default_factory=list, description="命中标签集")
    includeNodeTypes: List[NodeType] = Field(default_factory=list, description="命中类型集")
    bypassUnmatched: bool = Field(default=True, description="是否穿透非匹配中间节点保持链路连通")

class ProjectModel(BaseModel):
    projectId: str
    projectName: str
    description: Optional[str] = ""
    version: str = "1.0.0"
    stage: Optional[str] = "staging_review"
    perspectives: List[PerspectiveModel] = Field(default_factory=list)
    nodes: List[NodeModel] = Field(default_factory=list)
    createdAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

# ================= 渲染层输出协议 (Core Canvas Payload) =================

class CanvasNodeOverlay(BaseModel):
    assignee: Optional[str] = None
    hours: str
    hasExternalBinding: bool
    isLogicVerified: bool
    isHumanApproved: bool
    isPowered: bool = True
    powerPathBroken: bool = False
    moduleProgressPct: Optional[float] = None
    moduleColorHex: Optional[str] = None

class CanvasNode(BaseModel):
    id: str
    label: str
    nodeType: NodeType
    status: NodeStatus
    bulbState: BulbState
    dataOverlay: CanvasNodeOverlay
    raw: NodeModel

class CanvasEdge(BaseModel):
    id: str
    source: str
    target: str
    circuitState: CircuitState
    flowAnimation: bool
    strokeColor: str
    isBypass: bool = False  # 是否为视角穿透虚拟线

class BottleneckImpact(BaseModel):
    blockerNodeId: str
    blockerNodeLabel: str
    blockerAssignee: Optional[str] = "未分配"
    blockerRole: Optional[str] = "-"
    status: NodeStatus
    blockedDownstreamCount: int
    blockedAssignees: List[str] = Field(default_factory=list)
    blockedNodeIds: List[str] = Field(default_factory=list)
    severity: str = "medium"  # high, medium, low
    reason: str = ""

class ModuleSummary(BaseModel):
    moduleId: str
    moduleName: str
    assignees: List[str] = Field(default_factory=list)
    assignRoles: List[str] = Field(default_factory=list)
    totalNodes: int
    energizedNodes: int
    progressRate: float
    isHealthy: bool = True
    bottlenecksCount: int = 0

class PersonalSupplyChain(BaseModel):
    assignee: str
    upstreamFeeders: List[Dict[str, Any]] = Field(default_factory=list)   # 上游谁在供电/我等谁
    myNodes: List[str] = Field(default_factory=list)                     # 我的在手卡片
    downstreamWaiters: List[Dict[str, Any]] = Field(default_factory=list)# 下游谁在等我放电

class CanvasStats(BaseModel):
    totalNodes: int
    energizedNodes: int
    blockedNodes: int
    logicVerifiedNodes: int
    progressRate: float
    bottlenecks: List[BottleneckImpact] = Field(default_factory=list)
    modules: List[ModuleSummary] = Field(default_factory=list)

class CanvasPayload(BaseModel):
    projectId: str
    projectName: str
    activeViewId: str
    activeViewName: str
    stats: CanvasStats
    nodes: List[CanvasNode]
    edges: List[CanvasEdge]
    personalSupplyChains: Dict[str, PersonalSupplyChain] = Field(default_factory=dict)
