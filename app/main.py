"""FastAPI 入口：REST + SSE 流式 + 会话/审计/指标/巡检。"""
from __future__ import annotations

import asyncio
import json
import queue
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.monitor import diagnose_incident, monitor
from app.openclow_client import OpenClowClient
from app.orchestrator import answer
from app.session import session_store

_executor = ThreadPoolExecutor(max_workers=8)


def resolve_user(x_api_key: str, x_user_id: str, users: dict[str, str], single_key: str) -> str | None:
    """由凭证解析出真实的 user_id；返回 None 表示未认证。

    优先级：OPS_ASSISTANT_USERS(user->key) → 单 OPS_ASSISTANT_API_KEY → 无鉴权(仅开发)。
    配置了任一凭证后，身份由凭证决定，不再信任客户端自报的 X-User-Id。
    """
    if users:  # 多用户：key 必须匹配某个 user
        for uid, key in users.items():
            if key == x_api_key:
                return uid
        return None
    if single_key:  # 单 key -> 归属 default 用户
        return "default" if x_api_key == single_key else None
    return x_user_id or "default"  # 本地开发免鉴权


def authenticate(
    x_api_key: str = Header(default="", alias="X-API-Key"),
    x_user_id: str = Header(default="default", alias="X-User-Id"),
) -> str:
    """FastAPI 依赖：认证并返回真实 user_id（失败 401）。"""
    user = resolve_user(x_api_key, x_user_id, settings.users, settings.ops_api_key)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return user


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期：启动/关闭后台健康巡检线程。"""
    monitor.start()
    try:
        yield
    finally:
        monitor.stop()


app = FastAPI(title="ops-assistant", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str = Field(..., description="用户问题")
    session_id: str | None = Field(default=None, description="会话 ID，不传则创建新会话")
    user_id: str = Field(default="default", description="用户标识（多用户隔离）")


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    user_id: str = "default"
    rewritten: str = ""
    elapsed_ms: float = 0.0
    report: dict[str, Any] | None = None
    tool_trails: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, Any]:
    client = OpenClowClient()
    try:
        platform = client.health()
        platform_ok = True
    except Exception as exc:
        platform = {"error": str(exc)}
        platform_ok = False
    return {
        "status": "ok" if platform_ok else "degraded",
        "ops_assistant": "ok",
        "openclow": platform,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user_id: str = Depends(authenticate)) -> dict[str, Any]:
    if not req.session_id:
        req.session_id = session_store.create(user_id=user_id)
    result = answer(req.query, session_id=req.session_id, user_id=user_id)
    return {
        "answer": result["answer"],
        "session_id": result["session_id"],
        "user_id": user_id,
        "rewritten": result["rewritten"],
        "report": result.get("report"),
        "tool_trails": result.get("tool_trails", []),
        "elapsed_ms": result["elapsed_ms"],
        "sources": [
            {"source": r.get("metadata", {}).get("source", ""), "score": r.get("score", 0.0)}
            for r in result.get("search_results", [])
        ],
    }


# ── SSE 流式排障 ──


def _run_agent(query: str, session_id: str, user_id: str, q: "queue.Queue[dict[str, Any]]") -> None:
    try:
        answer(query, session_id=session_id, user_id=user_id, observe=lambda e: q.put(e))
    except Exception as exc:
        q.put({"type": "error", "error": str(exc)})
    finally:
        q.put({"type": "__end__"})


async def _sse_gen(query: str, session_id: str, user_id: str) -> AsyncGenerator[str, None]:
    q: "queue.Queue[dict[str, Any]]" = queue.Queue()
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(_executor, _run_agent, query, session_id, user_id, q)
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id, 'user_id': user_id}, ensure_ascii=False)}\n\n"
    while True:
        try:
            evt = await loop.run_in_executor(_executor, q.get, True, 0.5)
        except queue.Empty:
            if fut.done():
                break
            continue
        if evt.get("type") == "__end__":
            break
        if evt.get("type") == "error":
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            break
        yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, user_id: str = Depends(authenticate)) -> StreamingResponse:
    if not req.session_id:
        req.session_id = session_store.create(user_id=user_id)
    return StreamingResponse(
        _sse_gen(req.query, req.session_id, user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/sessions")
def list_sessions(user_id: str = Depends(authenticate)) -> dict[str, Any]:
    return {"sessions": session_store.list_sessions(user_id=user_id)}


@app.delete("/api/sessions")
def clear_sessions(user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """一键清空当前用户的全部历史会话。"""
    deleted = session_store.clear_user_sessions(user_id)
    return {"deleted": deleted, "user_id": user_id}


@app.get("/api/sessions/{session_id}/history")
def get_history(session_id: str, user_id: str = Depends(authenticate)) -> dict[str, Any]:
    return {"session_id": session_id, "user_id": user_id, "history": session_store.history(session_id, user_id=user_id)}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """删除某会话（按用户隔离：只能删自己的）。"""
    if not session_store.session_exists(session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found")
    deleted = session_store.delete_session(session_id, user_id)
    return {"deleted": deleted, "session_id": session_id, "user_id": user_id}


@app.get("/api/audit")
def list_audit(limit: int = 100, user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """最近的工具调用审计记录（可观测/合规）。"""
    return {"audits": session_store.list_audit(limit=limit)}


# ── 知识沉淀（self-learning 闭环）──


class KnowledgeRequest(BaseModel):
    title: str = Field(..., description="runbook 标题/故障名")
    symptom: str = Field(..., description="症状")
    root_cause: str = Field(..., description="根因")
    actions: list[str] = Field(default_factory=list, description="处置步骤")
    source: str = Field(default="用户沉淀", description="来源")
    uncovered_id: int | None = Field(default=None, description="关联的未覆盖问题 id（可选）")


@app.post("/api/knowledge", dependencies=[Depends(authenticate)])
def submit_knowledge(req: KnowledgeRequest, user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """把一次排障结论沉淀成 runbook 并灌入知识库（幂等）。"""
    from app.knowledge import persist_and_ingest

    result = persist_and_ingest(req.model_dump())
    if req.uncovered_id is not None:
        session_store.mark_uncovered_ingested(req.uncovered_id, user_id)
    return {
        "ok": result.get("ingested", False),
        "file": result.get("file"),
        "chunks": result.get("chunks", 0),
        "source": result.get("source"),
        "error": result.get("error"),
    }


@app.get("/api/knowledge/uncovered", dependencies=[Depends(authenticate)])
def list_uncovered(limit: int = 100, user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """列出知识库没答上、待沉淀的问题。"""
    return {"uncovered": session_store.list_uncovered(user_id=user_id, limit=limit)}


# ── 真实业务指标：用户反馈 + 巡检 incident ──


class FeedbackRequest(BaseModel):
    session_id: str = Field(default="", description="会话 ID")
    query: str = Field(default="", description="被反馈的问题")
    rating: int = Field(default=0, description="1=👍好评 -1=👎差评 0=未评")
    resolved: int = Field(default=-1, description="1=已解决 0=未解决 -1=未知")
    resolve_seconds: int | None = Field(default=None, description="提问→解决 的秒数（可空）")


@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest, user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """记录一条用户对回答的反馈（真实解决率/满意率的原料）。"""
    fid = session_store.record_feedback(
        req.session_id, req.query, user_id=user_id,
        rating=req.rating, resolved=req.resolved, resolve_seconds=req.resolve_seconds,
    )
    return {"ok": True, "feedback_id": fid}


@app.get("/api/metrics")
def get_metrics(user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """真实业务指标（`组织级聚合`）：反馈侧解决率/满意率/平均耗时 + incident 侧发现数/MTTR/诊断率。

    说明：这里返回全局（跨用户）聚合，作为「业务经营指标」看待；
    单条/单人明细可通过 /api/feedback、/api/incidents 单独查看。
    """
    return {
        "feedback": session_store.feedback_stats(),
        "incidents": session_store.incident_stats(),
    }


@app.get("/api/incidents", dependencies=[Depends(authenticate)])
def list_incidents(limit: int = 100, user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """巡检发现的真实 incident 列表（时间倒序）。"""
    return {"incidents": session_store.list_incidents(limit=limit)}


@app.post("/api/incidents/clear", dependencies=[Depends(authenticate)])
def clear_incidents(user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """清空 incident 记录（巡检/调试用），便于重置指标面板。"""
    deleted = session_store.clear_incidents()
    return {"ok": True, "deleted": deleted}


@app.post("/api/incidents/{incident_id}/diagnose")
def diagnose_incident_endpoint(incident_id: int, force: bool = False, user_id: str = Depends(authenticate)) -> dict[str, Any]:
    """对某个 incident 用 agent 做一次诊断（或取已缓存诊断）。"""
    inc = session_store.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    if inc.get("diagnosed") and not force:
        return {
            "ok": True, "incident_id": incident_id, "cached": True,
            "diagnosis_ok": inc["diagnosis_ok"], "diagnosis": inc["diagnosis"],
            "elapsed_ms": inc["diag_elapsed_ms"],
        }
    result = diagnose_incident(incident_id, inc.get("summary") or "该服务出现异常",
                               inc.get("user_id") or settings.incident_user)
    return {
        "ok": True, "incident_id": incident_id, "cached": False,
        "diagnosis_ok": result["ok"], "diagnosis": result["diagnosis"],
        "elapsed_ms": result["elapsed_ms"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
