"""工具执行器：按名字分发到具体工具 handler，统一异常兜底。"""
from __future__ import annotations

import time
from typing import Any

from tools.registry import get_tool


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """执行一个工具，返回标准化证据结构。

    Returns:
        {"tool": str, "ok": bool, "evidence": str, "elapsed_ms": float}
    """
    tool = get_tool(name)
    t0 = time.perf_counter()
    if tool is None:
        return {"tool": name, "ok": False, "evidence": f"未知工具: {name}", "elapsed_ms": 0.0}
    try:
        result = tool.handler(args or {})
    except Exception as exc:  # 工具内部异常兜底，不影响 agent 循环
        result = {"ok": False, "evidence": f"{type(exc).__name__}: {exc}"}
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "tool": name,
        "ok": bool(result.get("ok", False)),
        "evidence": str(result.get("evidence", "")),
        "elapsed_ms": elapsed_ms,
    }
