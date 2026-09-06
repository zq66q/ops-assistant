"""独立冒烟测试：验证 import、工具执行、agent 循环（脚本化客户端）不报错。

不从 tests/ 跑，避免 pytest 收集。
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# 模拟 conftest：隔离 DB、固定 sim+json（DB 放在 D:\hardness 下，沙盒可写）
_tmp = ROOT / ".test_tmp"
_tmp.mkdir(exist_ok=True)
os.environ["OPS_SESSION_DB_PATH"] = str(_tmp / "sessions.db")
os.environ["OPS_AUDIT_DB_PATH"] = str(_tmp / "audit.db")
os.environ["OPS_TOOL_MODE"] = "sim"
os.environ["OPS_AGENT_TOOL_PROTOCOL"] = "json"
os.environ["OPENCLOW_BASE_URL"] = "http://localhost:8000"
os.environ["OPENCLOW_API_KEY"] = "test"


class FakeClient:
    def __init__(self, script):
        self.script = list(script)

    def chat_raw(self, messages, temperature=0.3, max_tokens=None):
        if not self.script:
            raise AssertionError("脚本用尽")
        return self.script.pop(0)

    def chat_tools(self, messages, tools, tool_choice="auto", temperature=0.3, max_tokens=None):
        return {"content": "", "tool_calls": None}

    def health(self):
        return {"status": "ok"}

    def search(self, query, top_k=None, rerank=None):
        return []


def main() -> int:
    from agent.loop import run
    from tools.executor import execute_tool
    from tools.registry import list_tools

    # 1) 工具在执行
    print("工具注册:", [t.name for t in list_tools()])
    r = execute_tool("probe_http", {})
    assert r["ok"] and "503" in r["evidence"], r
    print("probe_http ok ->", r["evidence"][:40])

    FINAL = json.dumps(
        {
            "action": "final",
            "report": {"ok": True, "symptom": "/health 503", "evidence": ["Invalid API key"],
                       "root_cause": "LLM_API_KEY 无效", "severity": "high",
                       "actions": ["核对 .env 的 LLM_API_KEY", "重启服务"], "confidence": 0.85,
                       "sources": ["runbook/01"]},
        },
        ensure_ascii=False,
    )
    script = [
        json.dumps({"action": "tool", "tool": "search_runbook", "args": {"query": "服务 503"}}, ensure_ascii=False),
        json.dumps({"action": "tool", "tool": "query_logs", "args": {"level": "ERROR"}}, ensure_ascii=False),
        FINAL,
    ]
    client = FakeClient(script)
    result = run("服务 503 了", session_id=None, client=client)
    print("tool_trails:", [t["tool"] for t in result["tool_trails"]])
    print("severity:", result["report"]["severity"], "ok:", result["report"]["ok"])
    assert [t["tool"] for t in result["tool_trails"]] == ["search_runbook", "query_logs"]
    assert result["report"]["ok"] is True
    assert "重启" in result["answer"]
    print("answer snippet:", result["answer"][:80].replace("\n", " "))
    print("\nSMOKE OK")

    # 2) 可视化纯文本渲染
    from agent.report import DiagnosisReport
    rep = DiagnosisReport(ok=True, symptom="x", root_cause="y", severity="high",
                          actions=["a"], confidence=0.8, sources=["s"])
    print("--- report markdown ---\n" + rep.to_markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())
