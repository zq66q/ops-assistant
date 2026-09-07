"""自动修复 + 审批（human-in-the-loop）测试：风险分级 / 白名单 / 批准 / 拒绝 / incident 联动。"""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.session import session_store

client = TestClient(app)


def _clear(*tables: str) -> None:
    with sqlite3.connect(session_store.db_path) as conn:
        for t in tables:
            conn.execute(f"DELETE FROM {t}")


def test_low_risk_auto_executes():
    _clear("remediation_approvals")
    r = client.post("/api/remediation/request", json={"action": "restart_service", "service": "openclaw-api", "target": "openclaw-api"})
    assert r.status_code == 200
    d = r.json()
    assert d["executed"] is True
    assert d["risk"] == "low"


def test_high_risk_pending_then_approve():
    _clear("remediation_approvals")
    r = client.post("/api/remediation/request", json={"action": "update_config", "key": "LLM_API_KEY", "value": "x"})
    d = r.json()
    assert d["executed"] is False
    assert d["risk"] == "high"
    rid = d["approval_id"]
    pending = client.get("/api/remediation/pending").json()["remediation"]
    assert any(x["id"] == rid for x in pending)
    ar = client.post(f"/api/remediation/{rid}/approve").json()
    assert ar["status"] == "executed"
    assert ar["ok"] is True


def test_forbidden_refused():
    _clear("remediation_approvals")
    r = client.post("/api/remediation/request", json={"action": "drop_all_tables"})
    d = r.json()
    assert d["ok"] is False
    assert d["risk"] == "forbidden"
    assert d["executed"] is False


def test_reject():
    _clear("remediation_approvals")
    r = client.post("/api/remediation/request", json={"action": "restart_database", "service": "pg"})
    rid = r.json()["approval_id"]
    rr = client.post(f"/api/remediation/{rid}/reject").json()
    assert rr["status"] == "rejected"


def test_incident_resolve_on_execute():
    _clear("remediation_approvals", "incidents")
    iid, _ = session_store.open_incident("web", "http://h", "health", "web 异常", "HTTP 503")
    r = client.post("/api/remediation/request", json={"action": "restart_service", "service": "web", "target": "web", "incident_id": iid})
    assert r.json()["executed"] is True
    assert session_store.get_incident(iid)["status"] == "resolved"
