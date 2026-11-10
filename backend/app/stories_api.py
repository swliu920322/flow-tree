"""故事验收只读接口。全部 GET: 不启动测试, 不修改被测项目, 不写验收记录/签字。

状态与有效性全部来自 flowtree/ 的领域服务 (flowtree.view -> compute_units); 这里不做任何状态计算。
"""
import re
import sys
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flowtree import view  # noqa: E402
from flowtree.workspace import Workspace, WorkspaceConfigError, load_workspaces  # noqa: E402

router = APIRouter(prefix="/api/workspaces", tags=["stories (read-only)"])
SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ARTIFACTS = ("plugin_report", "junit", "stdout", "stderr")


def _workspaces() -> Dict[str, Workspace]:
    try:
        return load_workspaces()
    except WorkspaceConfigError as e:
        raise HTTPException(status_code=500, detail=f"workspace config error: {e}")


def _ws(ws_id: str) -> Workspace:
    ws = _workspaces().get(ws_id)
    if ws is None:
        raise HTTPException(status_code=404, detail=f"workspace {ws_id!r} not found")
    return ws


def _safe(*parts: str) -> None:
    for p in parts:
        if not SAFE.match(p) or ".." in p:
            raise HTTPException(status_code=400, detail="invalid identifier")


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except view.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except view.Conflict as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("")
def list_workspaces(refresh: bool = Query(False, description="跳过缓存重新读取证据与基线 (仍然只读)")):
    return {"workspaces": [view.workspace_card(w, refresh) for w in _workspaces().values()]}


@router.get("/{ws_id}/stories")
def list_stories(ws_id: str, refresh: bool = False):
    return _guard(view.story_list, _ws(ws_id), refresh)


@router.get("/{ws_id}/stories/{story_id}")
def get_story(ws_id: str, story_id: str, refresh: bool = False):
    _safe(story_id)
    return _guard(view.story_detail, _ws(ws_id), story_id, refresh)


@router.get("/{ws_id}/attempts/{run}/{story}/{entry}")
def get_attempt(ws_id: str, run: str, story: str, entry: str):
    _safe(run, story, entry)
    return _guard(view.attempt_detail, _ws(ws_id), run, story, entry)


@router.get("/{ws_id}/attempts/{run}/{story}/{entry}/artifacts/{name}")
def get_artifact(ws_id: str, run: str, story: str, entry: str, name: str):
    _safe(run, story, entry)
    if name not in ARTIFACTS:
        raise HTTPException(status_code=404, detail="unknown artifact")
    return _guard(view.read_artifact, _ws(ws_id), run, story, entry, name)
