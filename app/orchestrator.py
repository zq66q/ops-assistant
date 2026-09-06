"""核心编排：改写 → agent 工具循环 → 诊断报告。入口 answer() 兼容旧 /api/chat。"""
from __future__ import annotations

import time
from typing import Any

from agent.loop import run as agent_run
from app.openclow_client import OpenClowClient


def _detail(exc: Exception) -> str:
    """从异常里尽量抠出真实错误信息（如 openclow 返回的 402 余额不足）。"""
    if hasattr(exc, "response") and exc.response is not None:
        try:
            body = exc.response.json()
            return body.get("detail", "") or str(body)[:200]
        except Exception:
            return exc.response.text[:200]
    return str(exc)


def answer(
    query: str,
    session_id: str | None = None,
    client: OpenClowClient | None = None,
    observe=None,
    user_id: str = "default",
) -> dict[str, Any]:
    """一次问答的完整编排（非流式）——委托给 agent 工具循环。

    observe: 可选回调，每发生一次工具调用/最终结论时触发（供 SSE 流式推送消息）。
    user_id: 用户标识，用于会话按用户隔离。
    """
    t0 = time.perf_counter()
    try:
        return agent_run(query, session_id=session_id, client=client, observe=observe, user_id=user_id)
    except Exception as exc:
        # openclow 平台 / 排障引擎故障时给出友好提示，不让前端直接 500
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "answer": f"⚠️ 排障引擎调用失败（{type(exc).__name__}）：{_detail(exc)}",
            "session_id": session_id,
            "rewritten": query,
            "report": None,
            "tool_trails": [],
            "search_results": [],
            "elapsed_ms": elapsed_ms,
        }
