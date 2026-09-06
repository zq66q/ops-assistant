"""日志查询工具：按级别/关键词过滤最近日志，定位报错。"""
from __future__ import annotations

import re
from typing import Any

from app.config import settings
from tools import mock_data
from tools.registry import Tool


def _real(args: dict[str, Any]) -> dict[str, Any]:
    # 说明：日志采集依赖目标主机本地权限（journalctl / 文件读取）。
    # ops-assistant 与 openclow 同机部署时可用；否则降级为样本。
    lines = int(args.get("lines", 30))
    level = str(args.get("level", "ERROR")).upper()
    keyword = str(args.get("keyword", ""))
    try:
        import subprocess  # noqa: PLC0415

        cmd = ["journalctl", "-u", settings.ops_service_name, "-n", str(lines), "--no-pager"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
        # 简单过滤级别/关键词
        filtered = "\n".join(
            ln for ln in out.splitlines() if (level in ln.upper() or not level) and (keyword.lower() in ln.lower() or not keyword)
        )
        if not filtered.strip():
            filtered = f"（未命中 level={level} keyword={keyword} 的日志，返回前 {lines} 条）\n" + "\n".join(out.splitlines()[:lines])
        return {"ok": True, "evidence": filtered[:2000]}
    except Exception as exc:
        return {
            "ok": False,
            "evidence": f"日志采集不可用（{type(exc).__name__}: {exc}）。降级为样本：\n{mock_data.logs_evidence()}",
        }


def _sim(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "evidence": mock_data.logs_evidence()}


def execute(args: dict[str, Any]) -> dict[str, Any]:
    return _real(args) if settings.is_real_tool else _sim(args)


TOOL = Tool(
    name="query_logs",
    description="读取并过滤某个服务最近的运行日志，按级别/关键词定位报错（用于找出故障根因线索）。",
    parameters=[
        {"name": "service", "type": "string", "desc": "服务名，缺省用配置的 key", "required": False},
        {"name": "level", "type": "string", "desc": "过滤级别，如 ERROR/CRITICAL/DEBUG；空则不过滤", "required": False},
        {"name": "keyword", "type": "string", "desc": "按关键词过滤日志行", "required": False},
        {"name": "lines", "type": "integer", "desc": "返回最近多少行（默认 30）", "required": False},
    ],
    handler=execute,
)
