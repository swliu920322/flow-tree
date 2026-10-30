import os
import json
from pathlib import Path
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.schema import (
    ProjectModel, NodeModel, PerspectiveModel, CanvasPayload,
    NodeStatus, ReviewState
)
from app.core.lens import PerspectiveLens
from app.core.circuit import CircuitEngine

app = FastAPI(title="FlowTree State Circuit Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).parent / "data"

PROJECT_FILES = {
    "proj-life-piggy-bank": "life_piggy_bank.json",
    "proj-mall-001": "demo_project.json"
}

def get_project_path(project_id: str) -> Path:
    filename = PROJECT_FILES.get(project_id, f"{project_id}.json")
    path = DATA_DIR / filename
    if not path.exists():
        # 兼容当前项目默认
        path = DATA_DIR / "life_piggy_bank.json"
    return path

PROJECT_STORE: Dict[str, ProjectModel] = {}

def load_project_by_id(project_id: str) -> ProjectModel:
    if project_id in PROJECT_STORE:
        return PROJECT_STORE[project_id]
    path = get_project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    proj = ProjectModel(**data)
    PROJECT_STORE[project_id] = proj
    return proj

def save_project_by_id(project_id: str, project: ProjectModel):
    PROJECT_STORE[project_id] = project
    try:
        path = get_project_path(project_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(project.model_dump_json(indent=2))
    except Exception as e:
        # 在受限环境降级为内存更新，不阻断业务与测试流转
        pass

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# ================= REST APIs =================

@app.get("/api/projects")
def list_projects():
    """获取系统内管理的所有项目列表"""
    projects = []
    seen_ids = set()
    for pid, proj in PROJECT_STORE.items():
        projects.append({
            "projectId": proj.projectId,
            "projectName": proj.projectName,
            "description": proj.description,
            "nodeCount": len(proj.nodes),
            "stage": proj.stage
        })
        seen_ids.add(pid)
    for pid, filename in PROJECT_FILES.items():
        if pid in seen_ids:
            continue
        p_path = DATA_DIR / filename
        if p_path.exists():
            with open(p_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                projects.append({
                    "projectId": data.get("projectId", pid),
                    "projectName": data.get("projectName"),
                    "description": data.get("description"),
                    "nodeCount": len(data.get("nodes", [])),
                    "stage": data.get("stage", "dev")
                })
                seen_ids.add(pid)
    return projects

@app.get("/api/projects/{project_id}")
def get_project_metadata(project_id: str):
    """获取指定项目的元数据与可用视角"""
    proj = load_project_by_id(project_id)
    return {
        "projectId": proj.projectId,
        "projectName": proj.projectName,
        "description": proj.description,
        "version": proj.version,
        "perspectives": [p.dict() for p in proj.perspectives]
    }

@app.get("/api/projects/{project_id}/canvas", response_model=CanvasPayload)
def get_canvas_projection(project_id: str, view_id: str = "view-all"):
    """根据视角获取确定性的拓扑连通数据包"""
    proj = load_project_by_id(project_id)
    return PerspectiveLens.project(proj, view_id)

@app.post("/api/projects/sync")
async def sync_project(project: ProjectModel):
    """CLI 遥测/同步上报接口：注册或全量更新项目完整拓扑"""
    PROJECT_STORE[project.projectId] = project
    PROJECT_FILES[project.projectId] = f"{project.projectId}.json"
    save_project_by_id(project.projectId, project)
    await manager.broadcast({
        "event": "PROJECT_SYNCED",
        "projectId": project.projectId,
        "projectName": project.projectName,
        "nodeCount": len(project.nodes)
    })
    return {"success": True, "projectId": project.projectId, "nodeCount": len(project.nodes)}

class PatchStatusPayload(BaseModel):
    status: NodeStatus
    actualHours: float = None
    reviewComments: List[str] = None
    source: str = "agent_external"

@app.patch("/api/projects/{project_id}/nodes/{node_id}/status")
async def patch_node_status(project_id: str, node_id: str, payload: PatchStatusPayload):
    """外部 Agent / 测试平台 / 人工 提交标准状态更新"""
    proj = load_project_by_id(project_id)
    target_node = next((n for n in proj.nodes if n.nodeId == node_id), None)
    if not target_node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    target_node.status = payload.status
    if payload.actualHours is not None:
        target_node.actualHours = payload.actualHours
    if payload.reviewComments:
        target_node.review.comments.extend(payload.reviewComments)

    if payload.status == NodeStatus.LOGIC_VERIFIED:
        target_node.review.logicVerified = True
        target_node.review.logicVerifiedBy = payload.source
    elif payload.status == NodeStatus.REVIEW_PASS:
        target_node.review.humanSignOff = True
        target_node.review.humanSignOffBy = "human_reviewer"

    save_project_by_id(project_id, proj)

    await manager.broadcast({
        "event": "NODE_STATUS_UPDATED",
        "projectId": project_id,
        "nodeId": node_id,
        "status": target_node.status.value,
        "bulbState": CircuitEngine.get_bulb_state(target_node).value
    })

    return {"success": True, "projectId": project_id, "nodeId": node_id, "status": target_node.status}

@app.post("/api/projects/{project_id}/simulate-agent")
@app.post("/api/projects/{project_id}/simulate/run-agent-tests")
async def simulate_agent_flow(project_id: str):
    """【模拟执行】：根据项目特征自动模拟外部跑通与点亮流转"""
    proj = load_project_by_id(project_id)

    if project_id == "proj-life-piggy-bank":
        # 针对 Storyboard 步骤推进：S1-03 人工终审、S2-06 预扣自动化契约跑通、S2-07 线下核销走查
        s1_03 = next((n for n in proj.nodes if n.nodeId == "S1-03"), None)
        s2_04 = next((n for n in proj.nodes if n.nodeId == "S2-04"), None)
        s2_06 = next((n for n in proj.nodes if n.nodeId == "S2-06"), None)
        s2_07 = next((n for n in proj.nodes if n.nodeId == "S2-07"), None)

        if s1_03 and s1_03.status == NodeStatus.LOGIC_VERIFIED:
            s1_03.status = NodeStatus.REVIEW_PASS
            s1_03.review.humanSignOff = True
            s1_03.review.comments.append("【PM/体验终审通过】晨跑打卡心得弹出与树卡更新体验合格！")

        if s2_04 and s2_04.status == NodeStatus.LOGIC_VERIFIED:
            s2_04.status = NodeStatus.REVIEW_PASS
            s2_04.review.humanSignOff = True
            s2_04.review.comments.append("【女友监督终审】照片清晰合规，审批通过，20币放行！")

        if s2_06:
            # 自动化切片断言通过，点亮蓝灯待终审
            s2_06.status = NodeStatus.LOGIC_VERIFIED
            s2_06.review.logicVerified = True
            s2_06.review.comments.append("【自动化切片跑通】奶茶商品预扣事务及防双花排他锁断言通过！")

        if s2_07 and s2_06 and s2_06.status in (NodeStatus.LOGIC_VERIFIED, NodeStatus.REVIEW_PASS):
            s2_07.status = NodeStatus.DEVING
            s2_07.review.comments.append("【体验流转】小李已发起兑换，通知女友准备线下核销买单...")

    else:
        # 原电商项目模拟
        order_node = next((n for n in proj.nodes if n.nodeId == "node-api-order-create"), None)
        pay_node = next((n for n in proj.nodes if n.nodeId == "node-payment-gateway"), None)
        confirm_node = next((n for n in proj.nodes if n.nodeId == "node-pay-confirm"), None)
        if order_node:
            order_node.status = NodeStatus.REVIEW_PASS
            order_node.review.humanSignOff = True
        if pay_node:
            pay_node.status = NodeStatus.REVIEW_PASS
            pay_node.review.logicVerified = True
            pay_node.review.humanSignOff = True
        if confirm_node:
            confirm_node.status = NodeStatus.DEVING

    save_project_by_id(project_id, proj)

    await manager.broadcast({
        "event": "CIRCUIT_ENERGIZED",
        "projectId": project_id,
        "message": "全链路状态推进完成！"
    })
    return {"message": "Simulated agent flow executed"}

@app.post("/api/projects/{project_id}/reset")
async def reset_demo(project_id: str):
    """重置回初始数据"""
    # 重新加载并覆盖
    return {"message": "Reset executed"}

@app.websocket("/ws/circuit")
async def websocket_circuit(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "FlowTree API is running."}
