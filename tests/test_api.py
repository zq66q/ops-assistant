"""FastAPI 端点测试（用 TestClient，不发起真实外部调用）。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ops_assistant"] == "ok"
    assert data["status"] in ("ok", "degraded")  # 未连 openclow 时为 degraded


def test_chat_returns_answer(monkeypatch):
    canned = {
        "answer": "诊断：LLM_API_KEY 配置无效。",
        "session_id": "sess-123",
        "rewritten": "服务 503 了",
        "report": {"ok": True, "root_cause": "LLM_API_KEY 无效", "severity": "high"},
        "tool_trails": [{"step": 1, "tool": "query_logs"}],
        "search_results": [],
        "elapsed_ms": 3.2,
    }
    monkeypatch.setattr("app.main.answer", lambda *a, **k: canned)
    r = client.post("/api/chat", json={"query": "服务 503 了"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"].startswith("诊断")
    assert data["tool_trails"][0]["tool"] == "query_logs"
    assert data["session_id"] == "sess-123"


def test_chat_creates_session_when_missing(monkeypatch):
    canned = {"answer": "ok", "session_id": "auto-sess", "rewritten": "x",
              "report": None, "tool_trails": [], "search_results": [], "elapsed_ms": 1.0}
    monkeypatch.setattr("app.main.answer", lambda *a, **k: canned)
    r = client.post("/api/chat", json={"query": "hi"})
    assert r.status_code == 200
    assert r.json()["session_id"] == "auto-sess"
