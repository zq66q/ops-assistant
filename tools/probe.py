"""探活工具：对服务健康接口发起 HTTP 请求，判断服务是否可达/健康。"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from tools import mock_data
from tools.registry import Tool


def _real(args: dict[str, Any]) -> dict[str, Any]:
    url = args.get("url") or settings.ops_target_health
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(url, headers={"X-API-Key": settings.openclow_api_key})
            body = r.text[:200]
            evidence = f"HTTP {r.status_code} {r.reason_phrase}\n目标: {url}\n响应体(前 200 字符): {body}\n耗时: {r.elapsed.total_seconds():.2f}s"
            ok = r.status_code < 500
            return {"ok": ok, "evidence": evidence}
    except Exception as exc:
        return {"ok": False, "evidence": f"探活失败 {url}: {type(exc).__name__}: {exc}"}


def _sim(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "evidence": mock_data.probe_evidence()}


def execute(args: dict[str, Any]) -> dict[str, Any]:
    return _real(args) if settings.is_real_tool else _sim(args)


TOOL = Tool(
    name="probe_http",
    description="对指定的 HTTP 健康接口做一次 GET，判断服务是否可达及返回状态码（用于确认服务到底有没有在正常回应）。",
    parameters=[
        {"name": "url", "type": "string", "desc": "要探测的完整 URL；缺省用配置里的健康检查地址", "required": False},
    ],
    handler=execute,
)
