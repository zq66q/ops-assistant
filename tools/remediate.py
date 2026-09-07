"""自动修复工具（human-in-the-loop）。

原则：
- 只执行白名单（OPS_REMEDIATE_ALLOWED）里的动作；不在白名单 -> 拒绝，仅作建议。
- 风险分级：low（幂等/安全）在 OPS_REMEDIATE_AUTO 含 low 时自动执行；
  high（改配置/重启数据库等）一律生成待审批，必须人工批准后才执行。
- OPS_REMEDIATE_MODE=sim（默认，安全、可测、不碰真实服务）；=real（服务器）执行真实白名单命令。
- 执行后可选验证（OPS_REMEDIATE_VERIFY_URL），并串起 incident 关闭/MTTR。
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.session import session_store
from tools.registry import Tool


def _allowed(action: str) -> dict[str, Any] | None:
    return settings.remediation_allowlist.get(action)


def _fmt_args(args: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in args.items()) or "无"


def _real_run(action: str, cmd: str, args: dict[str, Any]) -> tuple[bool, str]:
    import shlex
    import subprocess

    try:
        formatted = cmd.format(**{k: str(v) for k, v in args.items()})
    except Exception as exc:
        return False, f"命令模板格式化失败（{action}）: {type(exc).__name__}: {exc}"
    try:
        cmd_list = shlex.split(formatted, posix=True)
        out = subprocess.run(cmd_list, capture_output=True, text=True, timeout=30)
        ok = out.returncode == 0
        return ok, f"执行 `{formatted}` 返回码 {out.returncode}\nstdout: {out.stdout[:400]}\nstderr: {out.stderr[:400]}"
    except Exception as exc:
        return False, f"执行失败 `{formatted}`: {type(exc).__name__}: {exc}"


def _sim_run(action: str, cmd: str, args: dict[str, Any]) -> tuple[bool, str]:
    return True, f"[sim] 模拟执行 `{cmd}`（动作={action}，参数: {_fmt_args(args)}）。未触碰真实服务（OPS_REMEDIATE_MODE=sim）。"


def _execute(action: str, args: dict[str, Any]) -> dict[str, Any]:
    """模拟/真实执行，返回 {"ok": bool, "txt": str}。"""
    item = _allowed(action)
    assert item is not None  # 调用前必须已过白名单
    if settings.remediate_mode.lower() == "real":
        ok, txt = _real_run(action, item.get("cmd", ""), args)
    else:
        ok, txt = _sim_run(action, item.get("cmd", ""), args)
    return {"ok": ok, "txt": txt}


def _verify() -> str:
    url = settings.remediate_verify_url
    if not url:
        return "（未配置 OPS_REMEDIATE_VERIFY_URL，跳过执行后验证）"
    try:
        import httpx

        r = httpx.get(url, timeout=8)
        return f"执行后验证 {url} -> HTTP {r.status_code}" + ("（已恢复）" if r.status_code < 400 else "（仍异常，需人工确认）")
    except Exception as exc:
        return f"执行后验证 {url} 失败: {type(exc).__name__}: {exc}"


def execute(args: dict[str, Any]) -> dict[str, Any]:
    action = str(args.get("action", "")).strip()
    target = str(args.get("target", "")).strip()
    incident_id = args.get("incident_id")
    params = {k: v for k, v in args.items() if k not in ("action", "target", "incident_id")}

    if not action:
        return {"ok": True, "evidence": "（remediate 缺少 action 参数）"}

    item = _allowed(action)
    if item is None:
        return {
            "ok": False,
            "evidence": f"动作 `{action}` 不在白名单（OPS_REMEDIATE_ALLOWED），拒绝执行，仅作建议。危险/未知操作需人工处理。",
            "risk": "forbidden",
            "executed": False,
        }

    risk = str(item.get("risk", "high"))
    desc = str(item.get("desc", ""))
    summary = f"{desc}（{action}）；目标={target or params.get('service') or '-'}；参数: {_fmt_args(params)}"

    # 不在自动范围内 -> 生成待审批（高风险强制人工审批）
    if risk not in settings.remediate_auto:
        rid = session_store.create_remediation(
            action, summary, risk, user_id="default", target=target, args=params, incident_id=incident_id
        )
        return {
            "ok": True,
            "evidence": (
                f"风险等级 **{risk}**，不自动执行（human-in-the-loop 安全设计）。\n"
                f"{summary}\n已生成**待审批请求 #审批id={rid}**，请通过界面/接口**批准后**执行。"
            ),
            "risk": risk,
            "approval_id": rid,
            "executed": False,
        }

    # 自动执行（low 且 OPS_REMEDIATE_AUTO 含 low）
    res = _execute(action, params)
    rid = session_store.create_remediation(
        action, summary + "（自动执行）", risk, user_id="default", target=target, args=params, incident_id=incident_id
    )
    if res["ok"] and incident_id:
        session_store.resolve_incident(int(incident_id))
    session_store.set_remediation_status(rid, "executed", res["txt"] + "\n" + _verify())
    evidence = f"风险等级 **{risk}**，已自动执行（OPS_REMEDIATE_AUTO 含 {risk}）。\n{res['txt']}\n{_verify()}"
    if incident_id and res["ok"]:
        evidence += f"\n已关闭关联 incident #{incident_id}（恢复，计入 MTTR）。"
    return {"ok": res["ok"], "evidence": evidence, "risk": risk, "executed": True, "approval_id": rid}


TOOL = Tool(
    name="remediate",
    description="执行自动修复/处置（受控、白名单、风险分级、按需人工审批）。低风险幂等动作可自动执行；高风险动作先生成待审批，批准后才执行；不在白名单一律拒绝。",
    parameters=[
        {"name": "action", "type": "string", "desc": "动作名，如 restart_service / clear_cache / update_config / restart_database", "required": True},
        {"name": "target", "type": "string", "desc": "目标服务/主机名（可选）", "required": False},
        {"name": "service", "type": "string", "desc": "要操作的服务名（可选）", "required": False},
        {"name": "incident_id", "type": "integer", "desc": "关联的 incident id（可选）；执行成功后自动关闭该 incident", "required": False},
    ],
    handler=execute,
)
