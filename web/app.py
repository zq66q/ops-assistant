"""Streamlit 聊天界面。"""
from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE = os.getenv("OPS_ASSISTANT_API", "http://localhost:8600")
API_KEY = os.getenv("OPS_ASSISTANT_API_KEY", "")

HEADERS = {"Content-Type": "application/json"}
if API_KEY:
    HEADERS["X-API-Key"] = API_KEY

st.set_page_config(page_title="运维排障助手", page_icon="🛠️")
st.title("🛠️ openclow 运维排障助手")

if "session_id" not in st.session_state:
    st.session_state.session_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

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
