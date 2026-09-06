"""工具包：真实/模拟双后端的排障工具。

每个工具模块导出：
    TOOL: Tool   —— 工具描述（名字/说明/参数 schema），供 LLM 决策使用
    execute(args) -> dict —— 执行并返回证据 {"ok": bool, "evidence": str}

工具在 sim 模式返回固定样本，在 real 模式对真实服务执行。
"""
from tools.registry import Tool, get_tool, list_tools, register, register_default_tools

__all__ = ["Tool", "get_tool", "list_tools", "register", "register_default_tools"]
