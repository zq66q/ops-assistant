"""核心编排：改写 → 检索 → 生成。"""
from __future__ import annotations

import time
from typing import Any

from app.config import settings
from app.openclow_client import OpenClowClient
from app.rewriter import rewrite_query
from app.session import session_store


SYSTEM_PROMPT = """你是 openclow 项目的运维排障助手。请基于下面提供的参考信息和对话历史回答用户问题。

规则：
1. 优先使用参考信息中的内容，回答要准确
2. 当前问题涉及历史对话时（如“我刚才问的是什么”），优先基于对话历史回答，不要强行依赖参考信息
3. 参考信息无答案时，明确告知用户“我没有找到相关记录”，不要编造
4. 引用时标注来源
5. 回答简洁、结构化"""


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


def _format_history(messages: list[dict[str, str]]) -> str:
    if not messages:
        return "（无历史对话）"
    parts = []
    for msg in messages:
        role = "用户" if msg["role"] == "user" else "助手"
        parts.append(f"{role}：{msg['content']}")
    return "\n".join(parts)


def _build_user_prompt(
    query: str,
    context: str,
    history: list[dict[str, str]],
) -> str:
    return f"""对话历史：
{_format_history(history)}

当前问题：{query}

参考信息：
{context}

请回答当前问题。如果当前问题需要依赖对话历史（例如“我刚才问的是什么”），请基于对话历史回答，不要检索参考信息。"""


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
        user_prompt = _build_user_prompt(query, context, history)

        # 5. 调用 LLM 生成（用裸接口，避免 openclow 场景记忆污染）
        answer_text = client.chat_raw(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        ) or "[生成失败]"
    except Exception as exc:
        # openclow 平台故障时给出友好提示，不让前端直接 500
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # 优先暴露 openclow 返回的真实错误（如 402 Insufficient Balance），
        # 否则用户只看到笼统的“无法连接”会误以为是连接问题
        detail = ""
        if hasattr(exc, "response") and exc.response is not None:
            try:
                body = exc.response.json()
                detail = body.get("detail", "") or str(body)[:200]
            except Exception:
                detail = exc.response.text[:200]
        if not detail:
            detail = str(exc)
        return {
            "answer": f"⚠️ openclow 调用失败（{type(exc).__name__}）：{detail}",
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
