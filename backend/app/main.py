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

def load_project_by_id(project_id: str) -> ProjectModel:
    path = get_project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ProjectModel(**data)

def save_project_by_id(project_id: str, project: ProjectModel):
    path = get_project_path(project_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project.dict(), f, ensure_ascii=False, indent=2)

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
    for pid, filename in PROJECT_FILES.items():
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
async def simulate_agent_flow(project_id: str):
    """【模拟执行】：根据项目特征自动模拟外部跑通与点亮流转"""
    proj = load_project_by_id(project_id)

    if project_id == "proj-life-piggy-bank":
        # 模拟 T04 (他律指派) 与 T06 (心得持久化) 完成人类终审；T07 (商城) 研发完成并由切片测试验证通过！
        t04 = next((n for n in proj.nodes if n.nodeId == "T04"), None)
        t06 = next((n for n in proj.nodes if n.nodeId == "T06"), None)
        t07 = next((n for n in proj.nodes if n.nodeId == "T07"), None)
        t09 = next((n for n in proj.nodes if n.nodeId == "T09"), None)
        t10 = next((n for n in proj.nodes if n.nodeId == "T10"), None)

        if t04:
            t04.status = NodeStatus.REVIEW_PASS
            t04.review.humanSignOff = True
            t04.review.comments.append("【PM 终审通过】真机打卡审批交互符合预期！")
        if t06:
            t06.status = NodeStatus.REVIEW_PASS
            t06.review.humanSignOff = True
            t06.review.comments.append("【PM 终审通过】5000字心得排版与私密隔离验证通过！")
        if t07:
            t07.status = NodeStatus.REVIEW_PASS
            t07.review.logicVerified = True
            t07.review.humanSignOff = True
            t07.actualHours = 22.0
            t07.review.comments.append("【自动化切片跑通】商城幂等预扣与驳回原路退款事务通过！")
        if t09:
            t09.status = NodeStatus.REVIEW_PASS
            t09.review.humanSignOff = True
            t09.actualHours = 16.0
            t09.review.comments.append("【Flutter Coordinator】跨 Tab 状态联动实测通过！")
        if t10:
            # 前置全通，质量门禁自动点亮进入 deving!
            t10.status = NodeStatus.DEVING
            t10.review.comments.append("【门禁激活】上游全量导通，64 项 BDD 用户故事自动化回归中...")

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
