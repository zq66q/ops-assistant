"""工具层测试：sim 模式返回证据、未知工具兜底。"""
from __future__ import annotations

from app.config import settings
from tools.executor import execute_tool
from tools.registry import get_tool, list_tools


def test_tools_registered():
    names = {t.name for t in list_tools()}
    assert {"probe_http", "query_logs", "check_resources", "service_status", "search_runbook"} <= names


def test_probe_sim_returns_evidence():
    assert settings.is_real_tool is False
    r = execute_tool("probe_http", {})
    assert r["ok"] is True
    assert "HTTP 503" in r["evidence"] or "503" in r["evidence"]


def test_query_logs_sim_evidence():
    r = execute_tool("query_logs", {"level": "ERROR"})
    assert r["ok"] is True
    assert "Invalid API key" in r["evidence"]


def test_unknown_tool_graceful():
    r = execute_tool("no_such_tool", {})
    assert r["ok"] is False
    assert "未知工具" in r["evidence"]


def test_search_runbook_sim():
    r = execute_tool("search_runbook", {"query": "503"})
    assert r["ok"] is True
    assert "模型初始化失败" in r["evidence"]
