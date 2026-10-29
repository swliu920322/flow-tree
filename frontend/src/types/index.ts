export type NodeType =
  | 'root'
  | 'module'
  | 'page'
  | 'feature'
  | 'api'
  | 'component'
  | 'case'
  | 'data_pipeline';

export type NodeStatus =
  | 'pending_dev'
  | 'deving'
  | 'logic_verified'
  | 'review_pass'
  | 'review_reject'
  | 'archived';

export type BulbState =
  | 'off'
  | 'breathing'
  | 'blue_waiting'
  | 'green_on'
  | 'red_alert';

export type CircuitState = 'dormant' | 'energized' | 'blocked';

export interface ExternalBinding {
  system: string;
  targetType: string;
  targetId: string;
  meta?: Record<string, any>;
}

export interface ReviewState {
  logicVerified: boolean;
  logicVerifiedBy?: string;
  logicVerifiedAt?: string;
  humanSignOff: boolean;
  humanSignOffBy?: string;
  humanSignOffAt?: string;
  comments: string[];
}

export interface NodeModel {
  nodeId: string;
  parentId?: string;
  nodeType: NodeType;
  name: string;
  description?: string;
  tags: string[];
  assignRole?: string;
  assignee?: string;
  status: NodeStatus;
  deps: string[];
  acceptanceCriteria: string[];
  externalBinding?: ExternalBinding;
  estimateHours: number;
  actualHours: number;
  outputs: string[];
  review: ReviewState;
  updatedAt: string;
}

export interface PerspectiveModel {
  viewId: string;
  name: string;
  description?: string;
  icon?: string;
  includeTags: string[];
  includeNodeTypes: NodeType[];
  bypassUnmatched: boolean;
}

export interface CanvasNodeOverlay {
  assignee?: string;
  hours: string;
  hasExternalBinding: boolean;
  isLogicVerified: boolean;
  isHumanApproved: boolean;
}

export interface CanvasNode {
  id: string;
  label: string;
  nodeType: NodeType;
  status: NodeStatus;
  bulbState: BulbState;
  dataOverlay: CanvasNodeOverlay;
  raw: NodeModel;
}

export interface CanvasEdge {
  id: string;
  source: string;
  target: string;
  circuitState: CircuitState;
  flowAnimation: boolean;
  strokeColor: string;
  isBypass: boolean;
}

export interface CanvasStats {
  totalNodes: int;
  energizedNodes: int;
  blockedNodes: int;
  logicVerifiedNodes: int;
  progressRate: number;
}

export interface CanvasPayload {
  projectId: string;
  projectName: string;
  activeViewId: string;
  activeViewName: string;
  stats: CanvasStats;
  nodes: CanvasNode[];
  edges: CanvasEdge[];
}
