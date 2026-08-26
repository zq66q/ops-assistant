"""Streamlit 聊天界面。"""
from __future__ import annotations

import os

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
except ImportError:  # 未安装时退回旧行为：会话只在页面内存里
    _JS_STORAGE_OK = False

load_dotenv()  # 读取 .env（systemd 注入的环境变量优先级更高，不会覆盖）

API_BASE = os.getenv("OPS_ASSISTANT_API", "http://localhost:8600")
API_KEY = os.getenv("OPS_ASSISTANT_API_KEY", "")

HEADERS = {"Content-Type": "application/json"}
if API_KEY:
    HEADERS["X-API-Key"] = API_KEY

# session_id 在浏览器 localStorage 的键名；刷新/重启浏览器后凭它找回会话
SID_STORAGE_KEY = "ops_assistant_session_id"

st.set_page_config(page_title="运维排障助手", page_icon="🛠️")


def _fetch_history(sid: str) -> list[dict[str, str]]:
    """从后端拉取会话历史（后端 SQLite 持久化，重启不丢）。"""
    try:
        r = requests.get(f"{API_BASE}/api/sessions/{sid}/history", headers=HEADERS, timeout=15)
        if r.ok:
            hist = r.json().get("history") or []
            return [
                {"role": m.get("role", "user"), "content": m.get("content", "")} for m in hist
            ]
    except Exception:
        pass
    return []


# ---------- 会话恢复 ----------
# st.session_state 只是页面内存，刷新即清空；这里从 localStorage 找回 session_id，
# 再用后端 /api/sessions/{id}/history 回填消息，实现"刷新/重启浏览器后对话还在"。
if not st.session_state.get("sid_checked"):
    saved_sid = ""
    if _JS_STORAGE_OK:
        # 注意 || '' 兜底：getItem 找不到时返回 null，会和"JS 尚未回传"混淆，
        # 且 null 不会触发组件重跑；空字符串两个问题都避开。
        saved_sid = streamlit_js_eval(
            js_expressions=f"localStorage.getItem('{SID_STORAGE_KEY}') || ''",
            key="ops_sid_load",
        )
        if saved_sid is None:
            # 首次加载会短暂走到这里；组件回传结果后自动触发重跑
            st.info("正在恢复会话…")
            st.stop()
    st.session_state.sid_checked = True
    if isinstance(saved_sid, str) and len(saved_sid) == 32:
        st.session_state.session_id = saved_sid
        st.session_state.messages = _fetch_history(saved_sid)
        st.session_state.just_restored = len(st.session_state.messages)

if "session_id" not in st.session_state:
    st.session_state.session_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# 新建会话后顺带清掉 localStorage（延迟到下一轮渲染执行，避免 st.rerun() 打断脚本）
if st.session_state.pop("clear_storage", False) and _JS_STORAGE_OK:
    remove_local_storage(SID_STORAGE_KEY)

st.title("🛠️ openclow 运维排障助手")

_restored_count = st.session_state.pop("just_restored", 0)
if _restored_count:
    st.caption(f"🔁 已恢复本浏览器的历史会话（{_restored_count} 条消息）")

# ---------- 侧边栏 ----------
with st.sidebar:
    sid = st.session_state.session_id
    st.caption(f"会话 ID：`{sid[:8]}…`" if sid else "会话 ID：发送首条消息后创建")
    if st.button("🆕 新建会话", use_container_width=True):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.session_state.clear_storage = True
        st.rerun()
    st.divider()
    st.caption(
        "会话双重持久化：浏览器 localStorage 记 session_id（刷新/重启浏览器不丢），"
        "后端 SQLite 存消息（服务重启不丢）。"
    )

# ---------- 历史消息 ----------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

query = st.chat_input("请输入你的运维问题，例如：备案期间怎么访问服务？")
if query:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("思考中..."):
            try:
                r = requests.post(
                    f"{API_BASE}/api/chat",
                    json={"query": query, "session_id": st.session_state.session_id},
                    headers=HEADERS,
                    timeout=120,
                )
                r.raise_for_status()
                data = r.json()
                answer_text = data["answer"]

                # 会话 id 变化（新会话首条消息）→ 写入 localStorage，刷新后可找回
                if data["session_id"] != st.session_state.session_id:
                    if _JS_STORAGE_OK:
                        set_local_storage(SID_STORAGE_KEY, data["session_id"])
                    st.session_state.session_id = data["session_id"]

                # 展示改写信息（调试用，面试演示可以隐藏）
                if data.get("rewritten") and data["rewritten"] != query:
                    st.caption(f"🔍 改写后检索：{data['rewritten']}")
                if data.get("sources"):
                    sources = ", ".join(s["source"] for s in data["sources"][:3])
                    st.caption(f"📚 参考来源：{sources}")
            except Exception as exc:
                answer_text = f"调用失败：{exc}"

        st.markdown(answer_text)
        st.session_state.messages.append({"role": "assistant", "content": answer_text})
