"""真实业务指标相关测试：用户反馈 + 巡检 incident（隔离 DB，无外部依赖）。"""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.session import session_store

client = TestClient(app)


def _clear(*tables: str) -> None:
    """清空测试表，保证用例相互独立。"""
    with sqlite3.connect(session_store.db_path) as conn:
        for t in tables:
            conn.execute(f"DELETE FROM {t}")


def test_feedback_records_and_stats():
    _clear("feedback")
    session_store.record_feedback("s1", "服务503", user_id="default", rating=1, resolved=1, resolve_seconds=30)
    session_store.record_feedback("s2", "nginx挂", user_id="default", rating=-1, resolved=0, resolve_seconds=None)
    stats = session_store.feedback_stats()
    assert stats["total"] == 2
    assert stats["resolve_rate"] == 0.5  # 1 已解决 / 2 已判
    assert stats["satisfaction_rate"] == 0.5  # 1 好评 / 2 已评
    assert stats["avg_resolve_seconds"] == 30.0


def test_feedback_api():
    r = client.post(
        "/api/feedback",
        json={"session_id": "s3", "query": "探活失败", "rating": 1, "resolved": 1, "resolve_seconds": 10},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["feedback_id"] > 0


def test_metrics_api_shape():
    r = client.get("/api/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "feedback" in data and "incidents" in data
    assert isinstance(data["feedback"]["resolve_rate"], (float, type(None)))
    assert "mttr_seconds" in data["incidents"]


def test_incident_lifecycle():
    _clear("incidents")
    iid, is_new = session_store.open_incident("web", "http://h", "health", "web 异常", "HTTP 503", user_id="system")
    assert is_new is True
    # 同一 target 仍异常：只刷新，不新建（保留最早 detected_at 算 MTTR）
    iid2, is_new2 = session_store.open_incident("web", "http://h", "health", "web 异常2", "HTTP 503", user_id="system")
    assert is_new2 is False and iid2 == iid
    session_store.set_incident_diagnosis(iid, "结论：配置错误", True, 100.0)
    closed = session_store.close_incident("web")
    assert closed == iid
    stats = session_store.incident_stats()
    assert stats["total"] == 1
    assert stats["resolved"] == 1
    assert stats["diagnosed"] == 1
    assert stats["diagnosis_rate"] == 1.0


def test_incident_refresh_preserves_detected_at():
    _clear("incidents")
    iid, _ = session_store.open_incident("api", "http://a", "health", "api 异常", "HTTP 500", user_id="system")
    # 模拟下一轮仍异常：只刷新 summary
    session_store.open_incident("api", "http://a", "health", "api 异常(重)", "HTTP 500", user_id="system")
    incs = session_store.list_incidents()
    assert len(incs) == 1  # 仍是同一条
    assert incs[0]["id"] == iid
    assert incs[0]["status"] == "open"


def test_incidents_api():
    _clear("incidents")
    iid, _ = session_store.open_incident("db", "http://d", "health", "db 异常", "HTTP 503", user_id="system")
    r = client.get("/api/incidents")
    assert r.status_code == 200
    assert any(it["id"] == iid for it in r.json()["incidents"])


def test_diagnose_endpoint(monkeypatch):
    _clear("incidents")
    iid, _ = session_store.open_incident("cache", "http://c", "health", "cache 异常", "HTTP 502", user_id="system")

    # 模拟真实 diagnose_incident 的副作用：诊断后写回 incidents 表
    def fake_diagnose(incident_id, summary, user_id="system"):
        session_store.set_incident_diagnosis(incident_id, "诊断：缓存穿透", True, 50.0)
        return {"ok": True, "incident_id": incident_id, "diagnosis": "诊断：缓存穿透", "elapsed_ms": 50.0}

    monkeypatch.setattr("app.main.diagnose_incident", fake_diagnose)
    r = client.post(f"/api/incidents/{iid}/diagnose")
    assert r.status_code == 200
    body = r.json()
    assert body["diagnosis_ok"] is True
    assert body["diagnosis"].startswith("诊断")
    # 再次请求同 incident：应命中已缓存诊断
    r2 = client.post(f"/api/incidents/{iid}/diagnose")
    assert r2.status_code == 200
    assert r2.json().get("cached") is True
