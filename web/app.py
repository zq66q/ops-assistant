"""Streamlit 聊天界面 — SSE 流式展示 agent 工具轨迹 + 多用户（按凭证）隔离。

每个用户用自己的 API Key：后端根据 X-API-Key 解析出真实的 user_id（不再信任 X-User-Id 头）。
本地开发未配置 Key 时，用 X-User-Id 作为便捷占位。
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests
import streamlit as st
from dotenv import load_dotenv

try:
    from streamlit_js_eval import (
        remove_local_storage,
        set_local_storage,
        streamlit_js_eval,
    )
    _JS_STORAGE_OK = True
except ImportError:
    _JS_STORAGE_OK = False

load_dotenv()

API_BASE = os.getenv("OPS_ASSISTANT_API", "http://localhost:8600")
DEFAULT_API_KEY = os.getenv("OPS_ASSISTANT_API_KEY", "")

SID_STORAGE_KEY_BASE = "ops_assistant_session_id"  # 每个 user 一个 key：_<user_id>

st.set_page_config(page_title="运维排障助手", page_icon="🛠️", layout="wide")


def _headers(user_id: str, api_key: str = "") -> dict[str, str]:
    h = {"Content-Type": "application/json", "X-User-Id": user_id or "default"}
    key = api_key or DEFAULT_API_KEY
    if key:
        h["X-API-Key"] = key
    return h


def _sid_key(user_id: str) -> str:
    return f"{SID_STORAGE_KEY_BASE}_{user_id or 'default'}"


@st.cache_data(show_spinner=False)
def _fetch_history(sid: str, user_id: str, api_key: str, version: int) -> list[dict[str, str]]:
    try:
        r = requests.get(f"{API_BASE}/api/sessions/{sid}/history", headers=_headers(user_id, api_key), timeout=15)
        if r.ok:
            hist = r.json().get("history") or []
            return [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in hist]
    except Exception:
        pass
    return []


@st.cache_data(show_spinner=False)
def _fetch_sessions(user_id: str, api_key: str, version: int) -> list[dict[str, Any]]:
    try:
        r = requests.get(f"{API_BASE}/api/sessions", headers=_headers(user_id, api_key), timeout=15)
        if r.ok:
            return r.json().get("sessions") or []
    except Exception:
        pass
    return []


@st.cache_data(show_spinner=False)
def _fetch_metrics(user_id: str, api_key: str, version: int) -> dict[str, Any]:
    try:
        r = requests.get(f"{API_BASE}/api/metrics", headers=_headers(user_id, api_key), timeout=15)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}


@st.cache_data(show_spinner=False)
def _fetch_incidents(user_id: str, api_key: str, version: int) -> list[dict[str, Any]]:
    try:
        r = requests.get(f"{API_BASE}/api/incidents", headers=_headers(user_id, api_key), timeout=15)
        if r.ok:
            return r.json().get("incidents") or []
    except Exception:
        pass
    return []


@st.cache_data(show_spinner=False)
def _fetch_remediation(user_id: str, api_key: str, version: int, status: str | None = None) -> list[dict[str, Any]]:
    try:
        url = f"{API_BASE}/api/remediation/pending" if status == "pending" else f"{API_BASE}/api/remediation"
        r = requests.get(url, headers=_headers(user_id, api_key), timeout=15)
        if r.ok:
            return r.json().get("remediation") or []
    except Exception:
        pass
    return []


# ---------- 会话恢复 ----------
if "user_id" not in st.session_state:
    st.session_state.user_id = "default"
if "api_key" not in st.session_state:
    st.session_state.api_key = DEFAULT_API_KEY
if "cache_version" not in st.session_state:
    st.session_state.cache_version = 0
if "feedback_ctx" not in st.session_state:
    st.session_state.feedback_ctx = None


def _bump() -> None:
    """数据变化时使前端缓存失效（下次重拉会话/历史）。"""
    st.session_state.cache_version = st.session_state.get("cache_version", 0) + 1


if not st.session_state.get("sid_checked"):
    saved_sid = ""
    if _JS_STORAGE_OK:
        saved_sid = streamlit_js_eval(
            js_expressions=f"localStorage.getItem('{_sid_key(st.session_state.user_id)}') || ''",
            key=f"ops_sid_load_{st.session_state.user_id}",
        )
        if saved_sid is None:
            st.info("正在恢复会话…")
            st.stop()
    st.session_state.sid_checked = True
    if isinstance(saved_sid, str) and len(saved_sid) == 32:
        st.session_state.session_id = saved_sid
        st.session_state.messages = _fetch_history(saved_sid, st.session_state.user_id, st.session_state.api_key, st.session_state.cache_version)
        st.session_state.just_restored = len(st.session_state.messages)

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🛠️ 智能运维排障助手")

_restored_count = st.session_state.pop("just_restored", 0)
if _restored_count:
    st.caption(f"🔁 已恢复本浏览器的历史会话（{_restored_count} 条消息）")

# ---------- 侧边栏 ----------
with st.sidebar:
    st.caption("身份由 **API Key** 决定（多用户鉴权开启时）；用户ID 仅本地免鉴权开发模式用。")
    new_user = st.text_input("👤 用户ID（本地免鉴权模式用）", value=st.session_state.user_id).strip() or "default"
    new_key = st.text_input("🔑 API Key（身份由它决定；切用户请改这里）", value=st.session_state.api_key, type="password")
    changed_user = new_user != st.session_state.user_id
    changed_key = new_key != st.session_state.api_key
    st.session_state.user_id = new_user
    st.session_state.api_key = new_key
    if changed_user or changed_key:
        # 切换身份：重置会话 + 清掉对应 storage
        st.session_state.session_id = None
        st.session_state.messages = []
        st.session_state.feedback_ctx = None
        st.session_state.pop("just_restored", None)
        st.session_state.pop("ops_session_selector", None)
        if _JS_STORAGE_OK:
            remove_local_storage(_sid_key(new_user))
        st.rerun()

    sid = st.session_state.session_id
    if sid:
        st.caption(f"用户：`{st.session_state.user_id}`　会话：`{sid[:8]}…`")
    else:
        st.caption(f"用户：`{st.session_state.user_id}`　会话：发送首条消息后创建")

    if st.button("🆕 新建会话", use_container_width=True):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.session_state.feedback_ctx = None
        st.session_state.pop("ops_session_selector", None)
        if _JS_STORAGE_OK:
            remove_local_storage(_sid_key(st.session_state.user_id))
        st.rerun()

    st.divider()
    st.caption("📜 历史会话")
    sessions = _fetch_sessions(st.session_state.user_id, st.session_state.api_key, st.session_state.cache_version)
    if sessions:
        for s in sessions:
            sid_ = s["session_id"]
            title = f"{s['title']} ({s['msg_count']}条)"
            is_current = sid_ == st.session_state.session_id
            c1, c2 = st.columns([0.78, 0.22])
            with c1:
                label = ("" if is_current else "🟢 ") + title
                if st.button(label, key=f"sel_{sid_}", use_container_width=True, disabled=is_current):
                    st.session_state.session_id = sid_
                    st.session_state.messages = _fetch_history(sid_, st.session_state.user_id, st.session_state.api_key, st.session_state.cache_version)
                    if _JS_STORAGE_OK:
                        set_local_storage(_sid_key(st.session_state.user_id), sid_)
                    st.rerun()
            with c2:
                if st.button("❌", key=f"del_{sid_}", help="删除该会话", use_container_width=True):
                    try:
                        r = requests.delete(
                            f"{API_BASE}/api/sessions/{sid_}",
                            headers=_headers(st.session_state.user_id, st.session_state.api_key), timeout=15,
                        )
                        if r.ok:
                            _bump()
                            if st.session_state.session_id == sid_:
                                st.session_state.session_id = None
                                st.session_state.messages = []
                                st.session_state.feedback_ctx = None
                                if _JS_STORAGE_OK:
                                    remove_local_storage(_sid_key(st.session_state.user_id))
                            st.rerun()
                        else:
                            st.error(f"删除失败：HTTP {r.status_code}")
                    except Exception as exc:
                        st.error(f"删除失败：{exc}")
    else:
        st.caption("暂无历史会话")

    st.divider()
    c_confirm, c_btn = st.columns([0.66, 0.34])
    with c_confirm:
        confirm_all = st.checkbox("确认删除全部历史会话", key="confirm_clear_all")
    with c_btn:
        if st.button("🗑 一键删除全部", key="clear_all", use_container_width=True, disabled=not confirm_all):
            try:
                r = requests.delete(
                    f"{API_BASE}/api/sessions",
                    headers=_headers(st.session_state.user_id, st.session_state.api_key), timeout=15,
                )
                if r.ok:
                    _bump()
                    st.session_state.session_id = None
                    st.session_state.messages = []
                    st.session_state.feedback_ctx = None
                    if _JS_STORAGE_OK:
                        remove_local_storage(_sid_key(st.session_state.user_id))
                    st.rerun()
                else:
                    st.error(f"删除失败：HTTP {r.status_code}")
            except Exception as exc:
                st.error(f"删除失败：{exc}")

    st.divider()
    st.caption("📥 沉淀知识库（把新错误教会它）")
    with st.expander("添加一条排障知识", expanded=False):
        if st.button("📋 预填最近一次回答（可再改）", key="k_prefill", use_container_width=True):
            _last = st.session_state.get("last_diagnosis") or {}
            if _last:
                st.session_state["k_title"] = _last.get("title", "")
                st.session_state["k_symptom"] = _last.get("symptom", "")
                st.session_state["k_root"] = _last.get("root_cause", "")
                st.session_state["k_actions"] = ",".join(_last.get("actions", []))
                st.rerun()
            else:
                st.info("还没有可预填的诊断，请先问一个问题")
        _q = st.text_input("故障名", key="k_title")
        _s = st.text_area("症状", key="k_symptom")
        _r = st.text_area("根因", key="k_root")
        _a = st.text_input("处置步骤（逗号分隔）", key="k_actions")
        if st.button("提交沉淀进知识库", key="k_submit", use_container_width=True):
            if _q and _r:
                _actions = [x.strip() for x in _a.split(",") if x.strip()]
                try:
                    _rr = requests.post(
                        f"{API_BASE}/api/knowledge",
                        json={"title": _q, "symptom": _s, "root_cause": _r, "actions": _actions},
                        headers=_headers(st.session_state.user_id, st.session_state.api_key), timeout=40,
                    )
                    if _rr.ok:
                        _d = _rr.json()
                        _bump()
                        st.success(f"已沉淀进知识库：`{_d.get('source')}`（chunks={_d.get('chunks')}），下次可检索")
                    else:
                        st.error(f"沉淀失败：HTTP {_rr.status_code}")
                except Exception as exc:
                    st.error(f"沉淀失败：{exc}")
            else:
                st.warning("请至少填「故障名」和「根因」")

    st.divider()
    st.caption("📊 真实业务指标（解决率 / 满意率 / 平均耗时 / 巡检诊断）")
    metrics = _fetch_metrics(st.session_state.user_id, st.session_state.api_key, st.session_state.cache_version)
    fb = metrics.get("feedback") or {}
    inc = metrics.get("incidents") or {}
    with st.expander("指标", expanded=False):
        if st.button("🔄 刷新指标", key="metrics_refresh", use_container_width=True):
            _bump()
            st.rerun()
        # 安全格式化：指标可能为 None（如还没有"已解决/未解决"判断或好评差评），此时显示"—"而非 0/报错
        def _pct(v):
            return f"{v*100:.0f}%" if v is not None else "—"
        def _secs(v):
            return f"{v}s" if v is not None else "—"
        if fb.get("total"):
            st.metric("解决率", _pct(fb.get("resolve_rate")))
            st.metric("满意率", _pct(fb.get("satisfaction_rate")))
            st.metric("平均解决耗时", _secs(fb.get("avg_resolve_seconds")))
            st.caption(f"反馈数 {fb.get('total')}（已解决 {fb.get('resolved')} / 未解决 {fb.get('unresolved')}；好评 {fb.get('positive')} / 差评 {fb.get('negative')}；已评判断数 {fb.get('resolved', 0) + fb.get('unresolved', 0)}）")
        else:
            st.caption("暂无反馈。去回答下方点 👍/👎 并标记是否解决，就会累计。")
        if inc.get("total"):
            st.metric("巡检发现 incident", f"{inc.get('total')}")
            st.metric("自动诊断成功率", _pct(inc.get("diagnosis_rate")))
            st.metric("MTTR(发现→恢复)", _secs(inc.get("mttr_seconds")))
            st.caption(f"open {inc.get('open')} / 已解决 {inc.get('resolved')}；诊断 {inc.get('diagnosed')} / 有效 {inc.get('diagnosis_ok')}；平均诊断耗时 {inc.get('avg_diag_ms') or '—'}ms")
        else:
            st.caption("暂无巡检 incident。后台健康巡检发现异常会自动产生。")

    st.divider()
    st.caption("🚨 巡检 Incident（真实异常，自动/手动诊断）")
    incidents = _fetch_incidents(st.session_state.user_id, st.session_state.api_key, st.session_state.cache_version)
    with st.expander("Incident 列表", expanded=False):
        c_head, c_clear = st.columns([0.68, 0.32])
        with c_clear:
            if st.button("🗑 清空", key="incidents_clear", use_container_width=True, help="清空 incident 记录，重置指标面板"):
                try:
                    _r = requests.post(
                        f"{API_BASE}/api/incidents/clear",
                        headers=_headers(st.session_state.user_id, st.session_state.api_key), timeout=15,
                    )
                    if _r.ok:
                        _bump()
                        st.rerun()
                    else:
                        st.error(f"清空失败：HTTP {_r.status_code}")
                except Exception as exc:
                    st.error(f"清空失败：{exc}")
        if not incidents:
            st.caption("暂无 incident。")
        for it in incidents[:10]:
            head = f"#{it['id']} · {it['target']} · {'🚨' if it['status'] == 'open' else '✅'}{'open' if it['status'] == 'open' else 'resolved'}"
            st.markdown(f"**{head}**")
            st.caption(it.get("summary", "")[:80])
            if it.get("status") == "open" and not it.get("diagnosed"):
                if st.button("🔍 用 agent 诊断", key=f"diag_{it['id']}", use_container_width=True):
                    try:
                        _r = requests.post(
                            f"{API_BASE}/api/incidents/{it['id']}/diagnose",
                            headers=_headers(st.session_state.user_id, st.session_state.api_key), timeout=180,
                        )
                        if _r.ok:
                            _bump()
                            st.rerun()
                        else:
                            st.error(f"诊断失败：HTTP {_r.status_code}")
                    except Exception as exc:
                        st.error(f"诊断失败：{exc}")
            elif it.get("diagnosis"):
                st.caption(f"诊断：{it['diagnosis'][:120]}{'…' if len(it['diagnosis']) > 120 else ''}")

    st.divider()
    st.caption("🛠 自动修复 + 审批（human-in-the-loop）")
    pending = _fetch_remediation(st.session_state.user_id, st.session_state.api_key, st.session_state.cache_version, status="pending")
    records = _fetch_remediation(st.session_state.user_id, st.session_state.api_key, st.session_state.cache_version, status=None)

    # 持久反馈：上次发起/审批的结果（不被 rerun 清掉）
    _last = st.session_state.get("rem_last")
    if _last:
        if _last.get("error"):
            st.error(_last["error"])
        else:
            st.info(
                f"已发起：`{_last.get('action')}` risk=**{_last.get('risk')}** "
                f"executed=**{_last.get('executed')}** approval_id={_last.get('approval_id') or '—'}"
            )
            if _last.get("approval_id"):
                st.caption("↑ 这是一条**待审批**，请到「待审批修复」点【批准执行】或【拒绝】。")
            elif _last.get("executed"):
                st.caption("↑ 低风险已**自动执行**（模拟）。可从下方「最近修复记录」看结果。")

    with st.expander("待审批修复", expanded=False):
        if st.button("🔄 刷新", key="rem_refresh", use_container_width=True):
            _bump()
            st.rerun()
        if not pending:
            st.caption("暂无待审批修复。")
        for it in pending[:10]:
            st.markdown(f"**#{it['id']} · {it['action']} · {it['risk']}**")
            st.caption(it.get("summary", "")[:100])
            c_app, c_rej = st.columns(2)
            with c_app:
                if st.button("✅ 批准执行", key=f"app_{it['id']}", use_container_width=True):
                    try:
                        _r = requests.post(f"{API_BASE}/api/remediation/{it['id']}/approve",
                                           headers=_headers(st.session_state.user_id, st.session_state.api_key), timeout=60)
                        _d = _r.json() if _r.ok else {"error": f"HTTP {_r.status_code}"}
                        st.session_state["rem_last"] = {"action": it["action"], "risk": it["risk"], "executed": _d.get("ok", False), "approval_id": None}
                        _bump()
                        st.rerun()
                    except Exception as exc:
                        st.session_state["rem_last"] = {"error": f"批准失败：{exc}"}
                        st.rerun()
            with c_rej:
                if st.button("⛔ 拒绝", key=f"rej_{it['id']}", use_container_width=True):
                    try:
                        requests.post(f"{API_BASE}/api/remediation/{it['id']}/reject",
                                      headers=_headers(st.session_state.user_id, st.session_state.api_key), timeout=15)
                        st.session_state["rem_last"] = {"action": it["action"], "risk": it["risk"], "executed": False, "approval_id": None}
                        _bump()
                        st.rerun()
                    except Exception as exc:
                        st.session_state["rem_last"] = {"error": f"拒绝失败：{exc}"}
                        st.rerun()

    # 最近修复记录（所有状态，含自动执行/已批准/已拒绝，展示结果）
    with st.expander("最近修复记录", expanded=False):
        if not records:
            st.caption("暂无修复记录。")
        for it in records[:10]:
            _status_icon = {"executed": "✅", "pending": "⏳", "rejected": "⛔", "approved": "🟡", "error": "❌"}.get(it.get("status"), "•")
            st.markdown(f"**{_status_icon} #{it['id']} · {it['action']} · {it['risk']} · {it['status']}**")
            st.caption((it.get("summary", "") or "")[:80])
            if it.get("result"):
                st.caption(f"结果：{it['result'][:120]}{'…' if len(it['result']) > 120 else ''}")

    # 测试用：直接发起一个修复请求
    with st.expander("请求修复（测试）", expanded=False):
        action = st.selectbox("动作", ["restart_service", "clear_cache", "update_config", "restart_database"], key="rem_action")
        service = st.text_input("service", value="openclaw-api", key="rem_service")
        incident_id = st.number_input("incident_id（可选）", min_value=0, value=0, step=1, key="rem_inc")
        if st.button("🚀 发起修复请求", key="rem_send", use_container_width=True):
            payload = {"action": action, "service": service, "target": service}
            if int(incident_id) > 0:
                payload["incident_id"] = int(incident_id)
            try:
                _r = requests.post(f"{API_BASE}/api/remediation/request", json=payload,
                                   headers=_headers(st.session_state.user_id, st.session_state.api_key), timeout=60)
                if _r.ok:
                    _d = _r.json()
                    st.session_state["rem_last"] = {"action": action, "risk": _d.get("risk"), "executed": _d.get("executed"), "approval_id": _d.get("approval_id")}
                    _bump()
                    st.rerun()
                else:
                    st.session_state["rem_last"] = {"error": f"请求失败：HTTP {_r.status_code}"}
                    st.rerun()
            except Exception as exc:
                st.session_state["rem_last"] = {"error": f"请求失败：{exc}"}
                st.rerun()

    st.divider()
    st.caption("身份由凭证决定（后端按 X-API-Key 解析 user）；localStorage 记 session_id，后端 SQLite 存消息。")


def _render_tool_trail(tool_lines: list[str]) -> str:
    return "\n\n".join(tool_lines) if tool_lines else ""


def _render_feedback(ctx: dict[str, Any]) -> None:
    """渲染一次回答的反馈控件（👍/👎 + 是否解决 + 用时），写入真实业务指标。"""
    sid = ctx.get("session_id", "")
    if not sid:
        return
    done_key = f"fb_done_{sid}"
    if st.session_state.get(done_key):
        st.caption("✅ 已记录本次反馈，感谢！")
        return
    st.markdown("---")
    st.markdown("**请为这次回答评分（用于真实业务指标）**")
    c = st.columns(3)
    rating = c[0].radio("评价", ["👍 有帮助", "👎 没帮助", "跳过"], index=2,
                        horizontal=True, key=f"fb_r_{sid}", label_visibility="collapsed")
    resolved = c[1].radio("是否解决", ["已解决", "未解决", "跳过"], index=2,
                          horizontal=True, key=f"fb_s_{sid}", label_visibility="collapsed")
    secs = c[2].number_input("用时(秒)", min_value=0, value=0, step=1,
                             key=f"fb_c_{sid}", label_visibility="collapsed")
    if st.button("📤 提交反馈", key=f"fb_submit_{sid}", type="primary"):
        rating_val = {"👍 有帮助": 1, "👎 没帮助": -1, "跳过": 0}[rating]
        res_val = {"已解决": 1, "未解决": 0, "跳过": -1}[resolved]
        secs_val = int(secs) if int(secs) > 0 else None
        try:
            _r = requests.post(
                f"{API_BASE}/api/feedback",
                json={
                    "session_id": sid,
                    "query": ctx.get("query", ""),
                    "rating": rating_val,
                    "resolved": res_val,
                    "resolve_seconds": secs_val,
                },
                headers=_headers(st.session_state.user_id, st.session_state.api_key),
                timeout=15,
            )
            if _r.ok:
                st.session_state[done_key] = True
                _bump()
                st.rerun()
            else:
                st.error(f"反馈提交失败：HTTP {_r.status_code}")
        except Exception as exc:
            st.error(f"反馈提交失败：{exc}")


# ---------- 历史消息 ----------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

query = st.chat_input("请输入运维问题，例如：服务 /health 返回 503，日志报 Invalid API key")
if query:
    user_id = st.session_state.user_id
    api_key = st.session_state.api_key
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        tool_lines: list[str] = []
        answer = ""
        try:
            with requests.post(
                f"{API_BASE}/api/chat/stream",
                json={"query": query, "session_id": st.session_state.session_id, "user_id": user_id},
                headers=_headers(user_id, api_key), stream=True, timeout=180,
            ) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                for raw in r.iter_lines(decode_unicode=True):
                    if not raw or not raw.startswith("data: "):
                        continue
                    try:
                        evt = json.loads(raw[6:])
                    except json.JSONDecodeError:
                        continue
                    etype = evt.get("type")
                    if etype == "session":
                        new_sid = evt.get("session_id")
                        if new_sid and new_sid != st.session_state.session_id:
                            st.session_state.session_id = new_sid
                            _bump()  # 新建了会话 -> 历史列表变化
                            if _JS_STORAGE_OK:
                                set_local_storage(_sid_key(user_id), new_sid)
                    elif etype == "tool":
                        tool_lines.append(
                            f"🔧 调用工具 `{evt['tool']}`（步骤 {evt['step']}）" + ("✅" if evt.get("ok") else "⚠️")
                        )
                        placeholder.markdown(_render_tool_trail(tool_lines) + "\n\n_正在收集证据…_")
                    elif etype == "final":
                        answer = evt.get("answer", "")
                        rewritten = (evt.get("rewritten") or "").strip()
                        if rewritten and rewritten != query:
                            answer = f"> 🔍 多轮追问已改写为独立问题：**{rewritten}**（据此检索）\n\n{answer}"
                        # 捕获最近一次诊断，供「沉淀知识库」一键预填
                        _rep = evt.get("report") or {}
                        st.session_state.last_diagnosis = {
                            "title": (rewritten or query),
                            "symptom": _rep.get("symptom", "") or "",
                            "root_cause": _rep.get("root_cause", "") or "",
                            "actions": _rep.get("actions") or [],
                            "sources": _rep.get("sources") or [],
                        }
                        placeholder.markdown(_render_tool_trail(tool_lines) + ("\n\n" if tool_lines else "") + answer)
                    elif etype == "error":
                        answer = f"⚠️ {evt.get('error', '未知错误')}"
        except Exception as exc:
            answer = f"调用失败：{exc}"

        final_md = (_render_tool_trail(tool_lines) + ("\n\n" if tool_lines else "")) + answer
        placeholder.markdown(final_md)
        st.session_state.messages.append({"role": "assistant", "content": final_md})
        _bump()  # 本轮对话已写入会话 -> 历史列表条数/时间更新
        # 记录本次回答的上下文，供下方反馈控件使用
        st.session_state.feedback_ctx = {"query": query, "session_id": st.session_state.session_id}

# ---------- 用户反馈（针对最近一次回答；仅当前会话显示）----------
_ctx = st.session_state.feedback_ctx
if _ctx and _ctx.get("session_id") == st.session_state.session_id:
    _render_feedback(_ctx)
