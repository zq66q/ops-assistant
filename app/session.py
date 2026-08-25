"""SQLite 会话历史（重启不丢，生产环境可换成 Redis/PostgreSQL）。"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from app.config import settings


class SessionStore:
    """基于 SQLite 的线程安全会话存储。"""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or settings.session_db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_id ON session_messages(session_id)"
            )

    def create(self) -> str:
        return uuid.uuid4().hex

    def get(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT role, content FROM session_messages WHERE session_id = ? ORDER BY id",
                    (session_id,),
                ).fetchall()
                return [{"role": r["role"], "content": r["content"]} for r in rows]

    def append(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO session_messages (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, role, content),
                )

    def history(self, session_id: str) -> list[dict[str, str]]:
        return self.get(session_id)


session_store = SessionStore()
