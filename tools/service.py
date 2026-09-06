"""服务状态工具：查询 systemd 服务状态与重启次数，识别 crash-restart 循环。"""
from __future__ import annotations

from typing import Any

from app.config import settings
from tools import mock_data
from tools.registry import Tool


def _real(args: dict[str, Any]) -> dict[str, Any]:
    name = args.get("name") or settings.ops_service_name
    try:
        import subprocess  # noqa: PLC0415

        out = subprocess.run(["systemctl", "show", name], capture_output=True, text=True, timeout=10).stdout
        fields = {
            k: v for k, v in (ln.split("=", 1) for ln in out.splitlines() if "=" in ln)
        }
        evidence = (
            f"systemd 服务 {name}:\n"
            f"状态: {fields.get('ActiveState', 'n/a')}\n"
            f"主进程 PID: {fields.get('MainPID', 'n/a')}\n"
            f"NRestarts: {fields.get('NRestarts', 'n/a')}\n"
            f"ActiveEnterTimestamp: {fields.get('ActiveEnterTimestamp', 'n/a')}"
        )
        return {"ok": True, "evidence": evidence}
    except Exception as exc:
        return {
            "ok": False,
            "evidence": f"服务状态采集不可用（{type(exc).__name__}: {exc}）。降级为样本：\n{mock_data.service_evidence()}",
        }


def _sim(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "evidence": mock_data.service_evidence()}


def execute(args: dict[str, Any]) -> dict[str, Any]:
    return _real(args) if settings.is_real_tool else _sim(args)


TOOL = Tool(
    name="service_status",
    description="查询 systemd 服务当前状态、主进程 PID 与重启次数，用于判断是否 crash-restart 循环。",
    parameters=[
        {"name": "name", "type": "string", "desc": "systemd 服务名，缺省用配置的 key", "required": False},
    ],
    handler=execute,
)
