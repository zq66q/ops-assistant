"""应用配置，优先从 .env 读取。"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    openclow_base_url: str = os.getenv("OPENCLOW_BASE_URL", "http://localhost:8000").rstrip("/")
    openclow_api_key: str = os.getenv("OPENCLOW_API_KEY", "")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8600"))
    session_db_path: str = os.getenv("OPS_SESSION_DB_PATH", "./data/sessions.db")
    ops_api_key: str = os.getenv("OPS_ASSISTANT_API_KEY", "")
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "5"))
    rag_rerank: bool = os.getenv("RAG_RERANK", "false").lower() == "true"
    rewrite_trigger_words: set[str] = frozenset(
        os.getenv("REWRITE_TRIGGER_WORDS", "它,这个,那个,他,她,这,那,前面,刚才").split(",")
    )


settings = Settings()
