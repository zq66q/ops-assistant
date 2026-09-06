"""Query 改写：把多轮追问还原成独立问题。"""
from __future__ import annotations

from app.config import settings
from app.openclow_client import OpenClowClient


REWRITE_PROMPT = """你是一名问题改写助手。

任务：根据下面的对话历史，把用户的最新问题改写成一个不依赖上下文、可以独立理解的完整问题。

要求：
1. 用历史信息补全所有指代（它、这个、那个、他、她、这、那 等）
2. 保持用户的原始意图，不要过度泛化
3. 当用户询问“跑在哪/在哪里/位置/地址/端口”时，改写后的问题必须保留“端口”或“地址”等关键词，不要替换为“环境”“部署方式”等词
4. 只输出改写后的问题，不要解释、不要多余内容

对话历史：
{history_text}

用户最新问题：{query}

改写后的问题："""


def _history_to_text(history: list[dict[str, str]]) -> str:
    lines = []
    for turn in history[-6:]:  # 最近 3 轮
        role = turn.get("role", "")
        content = turn.get("content", "")
        label = "用户" if role == "user" else "助手"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def needs_rewrite(query: str) -> bool:
    """简单启发式：出现指代词才需要改写。"""
    return any(word in query for word in settings.rewrite_trigger_words)


def rewrite_query(query: str, history: list[dict[str, str]], client: OpenClowClient | None = None) -> str:
    """把多轮追问改写成独立问题。"""
    if not history or not needs_rewrite(query):
        return query

    client = client or OpenClowClient()
    history_text = _history_to_text(history)
    prompt = REWRITE_PROMPT.format(history_text=history_text, query=query)

    # 用 openclow 的裸 LLM 接口做改写，无记忆/无场景/无工具，避免历史污染
    rewritten = client.chat_raw(
        [{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=200,
    ).strip().strip('"').strip("？") + "？"
    return rewritten
