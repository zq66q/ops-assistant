"""SessionStore 单元测试：持久化、列表、工具审计。"""
from __future__ import annotations

from app.session import SessionStore


def test_create_returns_hex():
    s = SessionStore()
    sid = s.create()
    assert isinstance(sid, str) and len(sid) == 32


def test_append_and_history():
    s = SessionStore()
    sid = s.create()
    s.append(sid, "user", "服务 503 了")
    s.append(sid, "assistant", "可能是 LLM 凭据问题")
    hist = s.history(sid)
    assert [m["role"] for m in hist] == ["user", "assistant"]
    assert hist[0]["content"] == "服务 503 了"


def test_list_sessions_titles():
    s = SessionStore()
    sid = s.create()
    s.append(sid, "user", "一个很长的用户问题标题用来测试截断逻辑会不会出 bug")
    s.append(sid, "assistant", "ok")
    sessions = s.list_sessions()
    assert any(x["session_id"] == sid for x in sessions)
    found = next(x for x in sessions if x["session_id"] == sid)
    assert found["msg_count"] == 2
    assert found["title"].endswith("…")


def test_audit_tool_call_and_list():
    s = SessionStore()
    sid = s.create()
    s.audit_tool_call(session_id=sid, tool="query_logs", args={"level": "ERROR"}, evidence="line1\nline2", ok=True)
    audits = s.list_audit()
    assert audits
    assert audits[0]["tool"] == "query_logs"
    assert audits[0]["args"] == {"level": "ERROR"}
    assert audits[0]["ok"] is True


def test_user_isolation():
    s = SessionStore()
    a_sess = s.create(user_id="alice")
    b_sess = s.create(user_id="bob")
    s.append(a_sess, "user", "这是 alice 的问题", user_id="alice")
    s.append(b_sess, "user", "这是 bob 的问题", user_id="bob")

    alice_sessions = s.list_sessions(user_id="alice")
    bob_sessions = s.list_sessions(user_id="bob")
    assert any(x["session_id"] == a_sess for x in alice_sessions)
    assert not any(x["session_id"] == b_sess for x in alice_sessions)  # alice 看不到 bob 的
    assert any(x["session_id"] == b_sess for x in bob_sessions)

    # history 也按用户隔离
    assert s.history(a_sess, user_id="alice")[0]["content"] == "这是 alice 的问题"
    assert s.history(a_sess, user_id="bob") == []  # bob 看不到 alice 的历史
