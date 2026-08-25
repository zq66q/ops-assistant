"""FastAPI 入口。"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import settings
from app.openclow_client import OpenClowClient
from app.orchestrator import answer
from app.session import session_store


def verify_api_key(x_api_key: str = Header(default="")) -> None:
    """校验业务应用自身 API Key；未配置时不校验（方便本地开发）。"""
    expected = settings.ops_api_key
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

app = FastAPI(title="ops-assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str = Field(..., description="用户问题")
    session_id: str | None = Field(default=None, description="会话 ID，不传则创建新会话")


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    rewritten: str = ""
    elapsed_ms: float = 0.0
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


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(verify_api_key)])
def chat(req: ChatRequest) -> dict[str, Any]:
    if not req.session_id:
        req.session_id = session_store.create()

    result = answer(req.query, session_id=req.session_id)

    return {
        "answer": result["answer"],
        "session_id": result["session_id"],
        "rewritten": result["rewritten"],
        "elapsed_ms": result["elapsed_ms"],
        "sources": [
            {"source": r.get("metadata", {}).get("source", ""), "score": r.get("score", 0.0)}
            for r in result["search_results"]
        ],
    }


@app.get("/api/sessions/{session_id}/history", dependencies=[Depends(verify_api_key)])
def get_history(session_id: str) -> dict[str, Any]:
    return {"session_id": session_id, "history": session_store.history(session_id)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
