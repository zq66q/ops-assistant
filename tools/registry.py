"""工具注册表：登记工具、列出工具描述、按名字取执行函数。

子模块在 register_default_tools() 内延迟导入，避免与 tools/__init__ 循环依赖。
"""
from __future__ import annotations

from typing import Any, Callable


class Tool:
    """一个排障工具的元数据 + 执行函数。"""

    __slots__ = ("name", "description", "parameters", "handler")

    def __init__(
        self,
        name: str,
        description: str,
        parameters: list[dict[str, Any]],
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters  # [{"name":..., "type":..., "desc":...}, ...]
        self.handler = handler

    def to_prompt(self) -> str:
        """转成给 LLM 看的工具说明（JSON 协议用）。"""
        params = "；".join(
            f"{p['name']}({p.get('type', 'str')})={p.get('desc', '')}" for p in self.parameters
        )
        return f"- {self.name}: {self.description}。参数: {params}"

    def to_schema(self) -> dict[str, Any]:
        """转成原生 function-calling 的 tools 格式（native 协议用）。"""
        props: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            t = p.get("type", "string")
            props[p["name"]] = {"type": t, "description": p.get("desc", "")}
            if p.get("required", False):
                required.append(p["name"])
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        }


_registry: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _registry[tool.name] = tool


def get_tool(name: str) -> Tool | None:
    return _registry.get(name)


def list_tools() -> list[Tool]:
    return list(_registry.values())


def register_default_tools() -> None:
    """一次性登记内置工具（幂等）。"""
    import tools.logs as logs  # 内联导入，打破循环
    import tools.probe as probe
    import tools.resources as resources
    import tools.runbook as runbook
    import tools.service as service

    register(probe.TOOL)
    register(logs.TOOL)
    register(resources.TOOL)
    register(service.TOOL)
    register(runbook.TOOL)


register_default_tools()
