"""后台健康巡检（真实 incident 的来源，不依赖真人）。

定时探测配置里的靶点（openclow 平台 / 前端等）：
  - 探测异常 -> 记录/刷新一个 open incident（保留最早 detected_at 以便算真实 MTTR）；
    若开启自动诊断，则后台调 agent 对该 incident 产出一次诊断。
  - 探测恢复 -> 关闭对应 incident（记 resolved_at）。

把「实时开关」做成环境变量 OPS_MONITOR_ENABLED；间隔 OPS_MONITOR_INTERVAL_S；
自动诊断 OPS_MONITOR_AUTO_DIAGNOSE。线程安全：所有 DB 操作都走 session_store 的锁。
"""
from __future__ import annotations

import threading
import time
from typing import Any

from app.config import settings
from app.session import session_store


def _probe(url: str) -> tuple[bool, str]:
    """对一个健康接口做 GET，返回 (healthy, detail)。

    healthy 判定：HTTP < 400 且（若有 JSON）status 属于健康词集合、且各 component 均为健康。
    连接失败/超时/5xx 视为 down（真实监控语义）。

    说明：不同系统的健康词不一致（openclow 用 "running"，其它可能用 "ok"/"healthy"/"up"），
    统一按健康词集合判断，避免把 "running" 这类正常态误判为故障。
    """
    import httpx

    GOOD_STATUS = {"ok", "running", "healthy", "up", "ready", "active", "alive", "pass", "operational"}

    def _good(v) -> bool:
        return str(v).strip().lower() in GOOD_STATUS

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(url, headers={"X-API-Key": settings.openclow_api_key})
            detail = f"HTTP {r.status_code} {r.reason_phrase}\n目标: {url}\n响应体(前 200): {r.text[:200]}"
            if r.status_code >= 400:
                return False, detail
            try:
                body = r.json()  # type: ignore[union-attr]
            except Exception:
                body = None
            if isinstance(body, dict):
                st = body.get("status")
                if st is not None and not _good(st):
                    return False, detail + f"\nstatus={st}（非健康态）"
                comps = body.get("components")
                if isinstance(comps, dict):
                    bad = [k for k, v in comps.items() if not _good(v)]
                    if bad:
                        return False, detail + f"\ncomponents 异常: {bad}"
            return True, detail
    except Exception as exc:
        return False, f"探测失败 {url}: {type(exc).__name__}: {exc}"


def diagnose_incident(incident_id: int, summary: str, user_id: str = "system") -> dict[str, Any]:
    """用 agent 对某个 incident 产出诊断结果，并写回 incidents 表。"""
    from app.orchestrator import answer  # 延迟导入，避免循环依赖

    t0 = time.perf_counter()
    ok = False
    text = ""
    try:
        result = answer(summary, session_id=None, user_id=user_id)
        report = result.get("report") or {}
        ok = bool(report.get("ok", False))
        text = result.get("answer", "")
    except Exception as exc:
        text = f"诊断调用失败：{type(exc).__name__}: {exc}"
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    session_store.set_incident_diagnosis(incident_id, text, ok, elapsed_ms)
    return {"incident_id": incident_id, "ok": ok, "elapsed_ms": elapsed_ms, "diagnosis": text[:200]}


class Monitor:
    """后台健康巡检线程。start()/stop() 由 FastAPI lifespan 调用。"""

    def __init__(self, store=session_store) -> None:
        self._store = store
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not settings.monitors_enabled:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="ops-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._probe_all()
            except Exception as exc:  # 巡检自身异常不应杀死线程
                print(f"[monitor] 巡检异常: {type(exc).__name__}: {exc}")
            self._stop.wait(settings.monitors_interval_s)

    def _probe_all(self) -> None:
        for name, url in settings.monitor_targets.items():
            healthy, detail = _probe(url)
            if not healthy:
                summary = f"{name} 健康检查异常（{url}）"
                incident_id, is_new = self._store.open_incident(
                    name, url, "health", summary, detail, user_id=settings.incident_user
                )
                if settings.auto_diagnose and is_new:
                    # 新 incident：后台自动诊断，不阻塞巡检循环
                    threading.Thread(
                        target=self._diagnose,
                        args=(incident_id, summary, settings.incident_user),
                        daemon=True,
                        name="ops-diagnose",
                    ).start()
            else:
                closed = self._store.close_incident(name, user_id=settings.incident_user)
                if closed:
                    print(f"[monitor] 靶点 {name} 恢复健康，关闭 incident #{closed}")

    @staticmethod
    def _diagnose(incident_id: int, summary: str, user_id: str) -> None:
        try:
            diagnose_incident(incident_id, summary, user_id=user_id)
        except Exception as exc:
            print(f"[monitor] 诊断 incident #{incident_id} 失败: {type(exc).__name__}: {exc}")


monitor = Monitor()
