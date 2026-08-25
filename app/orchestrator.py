"""核心编排：改写 → 检索 → 生成。"""
from __future__ import annotations

import time
from typing import Any

from app.config import settings
from app.openclow_client import OpenClowClient
from app.rewriter import rewrite_query
from app.session import session_store


SYSTEM_PROMPT = """你是 openclow 项目的运维排障助手。请基于下面提供的参考信息回答用户问题。

规则：
1. 优先使用参考信息中的内容，回答要准确
2. 参考信息无答案时，明确告知用户“我没有找到相关记录”，不要编造
3. 引用时标注来源
4. 回答简洁、结构化"""


def _format_context(results: list[dict[str, Any]]) -> str:
    if not results:
        return "（无相关参考信息）"
    parts = []
    for i, item in enumerate(results, 1):
        md = item.get("metadata", {})
        source = md.get("source", "unknown")
        text = item.get("text", "")
        score = item.get("score", 0.0)
        parts.append(f"[{i}] 来源: {source} (相关度: {score:.4f})\n{text}")
    return "\n\n".join(parts)


def answer(
    query: str,
    session_id: str | None = None,
    client: OpenClowClient | None = None,
) -> dict[str, Any]:
    """一次问答的完整编排（非流式）。"""
    t0 = time.perf_counter()
    client = client or OpenClowClient()

    # 1. 取历史
    history = session_store.history(session_id) if session_id else []

    try:
        # 2. Query 改写
        rewritten = rewrite_query(query, history, client=client)

        # 3. RAG 检索
        search_results = client.search(rewritten, top_k=settings.rag_top_k, rerank=settings.rag_rerank)

        # 4. 拼装最终 prompt
        context = _format_context(search_results)

        # 5. 调用 LLM 生成（用裸接口，避免 openclow 场景记忆污染）
        answer_text = client.chat_raw(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"问题：{query}\n\n参考信息：\n{context}\n\n请回答："},
            ],
            temperature=0.3,
            max_tokens=800,
        ) or "[生成失败]"
    except Exception as exc:
        # openclow 平台故障时给出友好提示，不让前端直接 500
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "answer": f"⚠️ openclow 平台暂时无法连接（{type(exc).__name__}），运维助手无法获取参考信息。请检查平台服务状态或稍后再试。",
            "session_id": session_id,
            "rewritten": query,
            "search_results": [],
            "elapsed_ms": round(elapsed_ms, 2),
        }

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # 6. 保存会话
    if session_id:
        session_store.append(session_id, "user", query)
        session_store.append(session_id, "assistant", answer_text)

    return {
        "answer": answer_text,
        "session_id": session_id,
        "rewritten": rewritten,
        "search_results": search_results,
        "elapsed_ms": round(elapsed_ms, 2),
    }
