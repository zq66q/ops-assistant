"""与 openclow /chat/raw 交互的 LLM 工具客户端。

json 协议（默认，兼容当前线上 /chat/raw）：让模型输出一个标准 JSON action：
    {"action":"tool","tool":"<name>","args":{...}} 或 {"action":"final","report":{...}}
native 协议：透传 tools 给 /chat/raw，走原生 function-calling（需 openclow 已升级该接口）。
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.openclow_client import OpenClowClient, OpenClowError


class LLMToolError(Exception):
    pass


def _extract_json(text: str) -> dict[str, Any] | None:
    """从模型输出里抠出一个 JSON 动作对象（容忍代码块、前后废话、以及多段 JSON）。

    用括号匹配找到完整对象，只返回「含 action 字段且能解析」的那个——这样即使 report 的
    evidence 里内嵌了 {"status":...} 之类的字符，或输出里有多个 JSON 片段，也能正确解析最终的决策。
    """
    if not text:
        return None
    t = text.strip()
    # 去掉 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()

    start = -1
    depth = 0
    for i, ch in enumerate(t):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    cand = t[start : i + 1]
                    start = -1
                    try:
                        obj = json.loads(cand)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict) and "action" in obj:
                        return obj
    return None


def _normalize_action(decision: dict[str, Any]) -> dict[str, Any] | None:
    """把模型输出归一化成决策；无法识别动作时返回 None。"""
    action = decision.get("action")
    if action == "tool":
        tool = decision.get("tool")
        if not tool:
            return None
        return {"type": "tool", "tool": tool, "args": decision.get("args") or {}}
    if action in ("final", "report", "answer"):
        return {"type": "final", "report": decision.get("report") or decision}
    return None


def decide(
    client: OpenClowClient,
    messages: list[dict[str, str]],
    *,
    tools_schema: list[dict[str, Any]] | None = None,
    tool_prompt: str = "",
) -> dict[str, Any]:
    """让 LLM 决定下一步：调用工具 or 给出最终诊断。

    Returns:
        {"type":"tool","tool":str,"args":dict}
        {"type":"final","report":dict}
        {"type":"text","text":str}   —— 模型输出无法解析成 action 时的兜底
    """
    if settings.is_native_tool and tools_schema:
        resp = client.chat_tools(messages, tools=tools_schema, tool_choice="auto")
        if resp.get("tool_calls"):
            tc = resp["tool_calls"][0]
            try:
                args = json.loads(tc["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            return {"type": "tool", "tool": tc["name"], "args": args}
        return {"type": "text", "text": resp.get("content", "")}

    # json 协议
    try:
        raw = client.chat_raw(messages, temperature=settings.agent_temperature, max_tokens=settings.agent_max_tokens)
    except Exception as exc:  # 含 OpenClowError / httpx 网络错误等，统一转成可重试的 LLMToolError
        raise LLMToolError(f"LLM 调用失败: {exc}") from exc
    decision = _extract_json(raw)
    if decision is None:
        return {"type": "text", "text": raw}
    norm = _normalize_action(decision)
    if norm is None:
        return {"type": "text", "text": raw}
    return norm
