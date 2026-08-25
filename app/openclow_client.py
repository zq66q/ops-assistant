"""openclow API 调用封装（同步版，简单直接）。"""
from __future__ import annotations

import json
from typing import Any, Generator

import httpx

from app.config import settings


class OpenClowError(Exception):
    pass


class OpenClowClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or settings.openclow_base_url).rstrip("/")
        self.api_key = api_key or settings.openclow_api_key
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def health(self) -> dict[str, Any]:
        """检查 openclow 健康状态。"""
        with httpx.Client(timeout=10) as client:
            r = client.get(self._url("/health"), headers=self.headers)
            r.raise_for_status()
            return r.json()

    def chat(self, query: str, scenario: str = "general_assistant", session_id: str | None = None) -> dict[str, Any]:
        """同步对话，返回完整回答。"""
        payload = {"query": query, "scenario": scenario, "session_id": session_id or "", "stream": False}
        with httpx.Client(timeout=120) as client:
            r = client.post(self._url("/chat"), json=payload, headers=self.headers)
            r.raise_for_status()
            return r.json()

    def chat_stream(
        self,
        query: str,
        scenario: str = "general_assistant",
        session_id: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """SSE 流式对话，逐条 yield 事件。"""
        payload = {"query": query, "scenario": scenario, "session_id": session_id or "", "stream": True}
        with httpx.Client(timeout=120) as client:
            with client.stream("POST", self._url("/chat/stream"), json=payload, headers=self.headers) as response:
                response.raise_for_status()
                buffer = ""
                for chunk in response.iter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event, buffer = buffer.split("\n\n", 1)
                        data_line = next(
                            (line[6:] for line in event.splitlines() if line.startswith("data: ")), ""
                        )
                        if data_line:
                            try:
                                yield json.loads(data_line)
                            except json.JSONDecodeError:
                                continue

    def search(self, query: str, top_k: int | None = None, rerank: bool | None = None) -> list[dict[str, Any]]:
        """调用 openclow /rag/search，返回检索片段。"""
        payload = {
            "query": query,
            "top_k": top_k if top_k is not None else settings.rag_top_k,
            "rerank": rerank if rerank is not None else settings.rag_rerank,
        }
        with httpx.Client(timeout=60) as client:
            r = client.post(self._url("/rag/search"), json=payload, headers=self.headers)
            r.raise_for_status()
            return r.json().get("results", [])

    def ingest_text(self, text: str, source: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """将纯文本灌入 openclow 知识库。"""
        payload = {
            "text": text,
            "source": source,
            "metadata": metadata or {},
        }
        with httpx.Client(timeout=120) as client:
            r = client.post(self._url("/rag/ingest"), json=payload, headers=self.headers)
            r.raise_for_status()
            return r.json()

    def chat_raw(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        """裸 LLM 调用：无场景、无记忆、无工具，直接返回文本。"""
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        with httpx.Client(timeout=120) as client:
            r = client.post(self._url("/chat/raw"), json=payload, headers=self.headers)
            r.raise_for_status()
            return r.json().get("content", "")
