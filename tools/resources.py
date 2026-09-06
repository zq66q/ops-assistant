"""资源查询工具：CPU / 内存 / 磁盘，判断是否资源耗尽导致故障。"""
from __future__ import annotations

from typing import Any

from app.config import settings
from tools import mock_data
from tools.registry import Tool


def _real(args: dict[str, Any]) -> dict[str, Any]:
    try:
        import subprocess  # noqa: PLC0415

        def _get(cmd: list[str]) -> str:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout.strip()

        cpu = _get(["sh", "-c", "top -bn1 | grep '%Cpu' | awk -F: '{print $2}' | awk '{print $1}'"])
        mem = _get(["free", "-m"])
        disk = _get(["df", "-h", "/"])
        evidence = f"宿主资源 (本机):\nCPU: {cpu or 'n/a'}\n内存:\n{mem}\n磁盘:\n{disk}"
        return {"ok": True, "evidence": evidence}
    except Exception as exc:
        return {
            "ok": False,
            "evidence": f"资源采集不可用（{type(exc).__name__}: {exc}）。降级为样本：\n{mock_data.resources_evidence()}",
        }


def _sim(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "evidence": mock_data.resources_evidence()}


def execute(args: dict[str, Any]) -> dict[str, Any]:
    return _real(args) if settings.is_real_tool else _sim(args)


TOOL = Tool(
    name="check_resources",
    description="查询主机的 CPU / 内存 / 磁盘使用率，用于判断故障是否由资源耗尽引起。",
    parameters=[
        {"name": "host", "type": "string", "desc": "目标主机，缺省本机", "required": False},
    ],
    handler=execute,
)
