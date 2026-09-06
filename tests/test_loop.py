"""Agent 循环集成测试：脚本化 LLM 决策，验证工具序列/报告/审计。

使用 sim 工具模式 + 脚本化 FakeClient，确定、无外部依赖。
"""
from __future__ import annotations

import json

from agent.loop import run
from app.session import session_store


class FakeClient:
    """脚本化 openclow 客户端：按顺序返回预设的 LLM 决策 JSON。"""

    def __init__(self, script: list[str]) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def chat_raw(self, messages, temperature=0.3, max_tokens=None):
        self.calls.append({"messages": messages, "temperature": temperature})
        if not self.script:
            raise AssertionError("脚本用尽，但 agent 仍想调用 LLM")
        return self.script.pop(0)

    def chat_tools(self, messages, tools, tool_choice="auto", temperature=0.3, max_tokens=None):
        return {"content": "", "tool_calls": None}

    def search(self, query, top_k=None, rerank=None):
        return []

    def health(self):
        return {"status": "ok"}

    def ingest_text(self, text, source, metadata=None):
        return {"chunks": 0, "tokens": 0}


FINAL = json.dumps(
    {
        "action": "final",
        "report": {
            "ok": True,
            "symptom": "服务 /health 返回 503",
            "evidence": ["日志出现 Invalid API key"],
            "root_cause": "LLM_API_KEY 配置无效导致模型初始化失败",
            "severity": "high",
            "actions": ["核对 .env 的 LLM_API_KEY", "修正后重启服务"],
            "confidence": 0.85,
            "sources": ["runbook/01"],
        },
    },
    ensure_ascii=False,
)


def test_loop_executes_tool_sequence_and_report():
    client = FakeClient(
        [
            json.dumps({"action": "tool", "tool": "search_runbook", "args": {"query": "服务 503"}}, ensure_ascii=False),
            json.dumps({"action": "tool", "tool": "probe_http", "args": {}}, ensure_ascii=False),
            json.dumps({"action": "tool", "tool": "query_logs", "args": {"level": "ERROR"}}, ensure_ascii=False),
            json.dumps({"action": "tool", "tool": "service_status", "args": {"name": "openclaw-api"}}, ensure_ascii=False),
            FINAL,
        ]
    )
    result = run("服务 503 了", session_id=None, client=client)

    tools = [t["tool"] for t in result["tool_trails"]]
    assert tools == ["search_runbook", "probe_http", "query_logs", "service_status"]
    assert result["report"]["ok"] is True
    assert result["report"]["severity"] == "high"
    assert "LLM_API_KEY" in result["answer"]
    assert "重启" in result["answer"]


def test_loop_stops_on_final_early():
    # 只一步就给 final：不再调用其它工具，但 RAG-first 种子检索(search_runbook)仍会先执行一次
    client = FakeClient([FINAL])
    result = run("服务 503 了", session_id=None, client=client)
    assert [t["tool"] for t in result["tool_trails"]] == ["search_runbook"]  # 仅有 RAG-first 种子检索
    assert result["report"]["ok"] is True


def test_loop_refusal_on_insufficient():
    refuse = json.dumps(
        {"action": "final", "report": {"ok": False, "root_cause": "信息不足", "severity": "unknown", "confidence": 0.1}},
        ensure_ascii=False,
    )
    client = FakeClient([refuse])
    result = run("这个根因没法判断", session_id=None, client=client)
    assert result["report"]["ok"] is False
    assert result["report"]["severity"] == "unknown"


def test_loop_records_audit():
    client = FakeClient(
        [
            json.dumps({"action": "tool", "tool": "query_logs", "args": {"level": "ERROR"}}, ensure_ascii=False),
            FINAL,
        ]
    )
    session_id = "audit-session"
    run("服务 503 了", session_id=session_id, client=client)
    audits = session_store.list_audit(limit=50)
    names = [a["tool"] for a in audits]
    assert "query_logs" in names
