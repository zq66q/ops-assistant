"""Query 改写测试。"""
from __future__ import annotations

from app.rewriter import needs_rewrite, rewrite_query


def test_needs_rewrite_heuristic():
    assert needs_rewrite("那前端呢？") is True
    assert needs_rewrite("它跑在哪？") is True
    assert needs_rewrite("服务 503 了") is False


def test_rewrite_skipped_without_history():
    # 没历史直接返回原问题，不调用 LLM
    assert rewrite_query("服务 503 了", [], client=None) == "服务 503 了"


def test_rewrite_uses_llm_when_needed():
    class FakeClient:
        def chat_raw(self, messages, temperature=0.3, max_tokens=None):
            return "openclow 前端 Streamlit 跑在哪个端口？"

    out = rewrite_query("那前端呢？", [{"role": "user", "content": "openclow 前端是 Streamlit"}], client=FakeClient())
    assert "Streamlit" in out
    assert "端口" in out
