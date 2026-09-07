"""SQLite 会话历史 + 工具审计（按 user_id 隔离，重启不丢）。

可替换为 Redis/PostgreSQL。user_id 用于多用户隔离：每个用户只看得到自己的会话。
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from app.config import settings


class SessionStore:
    """基于 SQLite 的线程安全会话存储，按 user_id 隔离。"""

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
                    user_id TEXT NOT NULL DEFAULT 'default',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # 兼容旧库（无 user_id 列）：SQLite 不支持 ADD COLUMN IF NOT EXISTS，用 try/except。
            # 必须在建 idx_user_id 索引之前补列，否则旧表会报 no such column。
            self._ensure_column(conn, "session_messages", "user_id", "TEXT NOT NULL DEFAULT 'default'")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_id ON session_messages(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_id ON session_messages(user_id)"
            )
            # 工具调用审计：谁、何时、调了哪个工具、参数、结果
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    tool TEXT NOT NULL,
                    args TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_column(conn, "tool_audit", "user_id", "TEXT NOT NULL DEFAULT 'default'")
            # 未覆盖问题：agent 答不上（知识库没有）时自动记录，供后续沉淀进知识库
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS uncovered_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    question TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    ingested INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # 用户反馈：回答好不好、是否解决、用时多少（真实解决率/满意率的来源）
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL DEFAULT 'default',
                    query TEXT NOT NULL DEFAULT '',
                    rating INTEGER NOT NULL DEFAULT 0,
                    resolved INTEGER NOT NULL DEFAULT -1,
                    resolve_seconds INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # 真实巡检 incident：后台健康探测发现异常即记录；agent 可对其诊断
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'system',
                    target TEXT NOT NULL,
                    url TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT 'health',
                    status TEXT NOT NULL DEFAULT 'open',
                    summary TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    diagnosed INTEGER NOT NULL DEFAULT 0,
                    diagnosis TEXT NOT NULL DEFAULT '',
                    diagnosis_ok INTEGER NOT NULL DEFAULT 0,
                    diag_elapsed_ms REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_target ON incidents(target, status)")
            # 自动修复审批：高风险/需确认的处置动作，待人工批准后才执行
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS remediation_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    action TEXT NOT NULL,
                    target TEXT NOT NULL DEFAULT '',
                    args TEXT NOT NULL DEFAULT '{}',
                    summary TEXT NOT NULL DEFAULT '',
                    risk TEXT NOT NULL DEFAULT 'high',
                    status TEXT NOT NULL DEFAULT 'pending',
                    incident_id INTEGER,
                    result TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    decided_at TIMESTAMP,
                    executed_at TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_remediation_status ON remediation_approvals(status, user_id)")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, col: str, ddl_type: str) -> None:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type}")
        except sqlite3.OperationalError:
            pass  # 列已存在

    def create(self, user_id: str = "default") -> str:
        """新建会话 ID（真正落库在首次 append 时）。"""
        return uuid.uuid4().hex

    def get(self, session_id: str, user_id: str | None = None) -> list[dict[str, str]]:
        params: list[Any] = [session_id]
        cond = "session_id = ?"
        if user_id is not None:
            cond += " AND user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"SELECT role, content FROM session_messages WHERE {cond} ORDER BY id", params
                ).fetchall()
                return [{"role": r["role"], "content": r["content"]} for r in rows]

    def append(self, session_id: str, role: str, content: str, user_id: str = "default") -> None:
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO session_messages (session_id, user_id, role, content) VALUES (?, ?, ?, ?)",
                    (session_id, user_id, role, content),
                )

    def history(self, session_id: str, user_id: str | None = None) -> list[dict[str, str]]:
        return self.get(session_id, user_id=user_id)

    def list_sessions(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """列出某用户的会话（供前端历史会话列表使用）。"""
        cond = ""
        params: list[Any] = []
        if user_id is not None:
            cond = " WHERE user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"""
                    SELECT session_id, MIN(created_at) AS created_at,
                           MAX(created_at) AS updated_at, COUNT(*) AS msg_count
                    FROM session_messages{cond}
                    GROUP BY session_id ORDER BY updated_at DESC
                    """,
                    params,
                ).fetchall()
                sessions: list[dict[str, Any]] = []
                for r in rows:
                    title_row = conn.execute(
                        "SELECT content FROM session_messages "
                        "WHERE session_id = ? AND role = 'user' ORDER BY id LIMIT 1",
                        (r["session_id"],),
                    ).fetchone()
                    title = (title_row["content"][:30] + "…") if title_row else "无标题"
                    sessions.append(
                        {
                            "session_id": r["session_id"],
                            "title": title,
                            "created_at": r["created_at"],
                            "updated_at": r["updated_at"],
                            "msg_count": r["msg_count"],
                        }
                    )
                return sessions

    def session_exists(self, session_id: str, user_id: str | None = None) -> bool:
        """判断某会话是否存在（可按用户隔离）。"""
        cond = "session_id = ?"
        params: list[Any] = [session_id]
        if user_id is not None:
            cond += " AND user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(f"SELECT 1 FROM session_messages WHERE {cond} LIMIT 1", params)
                return cur.fetchone() is not None

    def delete_session(self, session_id: str, user_id: str | None = None) -> int:
        """删除某会话及其审计记录（可按用户隔离）。返回删除的消息条数。"""
        cond = "session_id = ?"
        params: list[Any] = [session_id]
        if user_id is not None:
            cond += " AND user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(f"DELETE FROM session_messages WHERE {cond}", params)
                conn.execute(f"DELETE FROM tool_audit WHERE {cond}", params)
                return cur.rowcount

    def clear_user_sessions(self, user_id: str) -> int:
        """一键清空某用户的全部会话与审计记录。返回删除的消息条数。"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("DELETE FROM session_messages WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM tool_audit WHERE user_id = ?", (user_id,))
                return cur.rowcount

    # ------------------------------------------------------------------
    # 未覆盖问题（知识沉淀）
    # ------------------------------------------------------------------

    def record_uncovered(self, question: str, user_id: str = "default", note: str = "") -> None:
        """记录一个「知识库没答上」的问题，等待后续沉淀。"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO uncovered_questions (user_id, question, note) VALUES (?, ?, ?)",
                    (user_id, question[:500], note[:500]),
                )

    def list_uncovered(self, user_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """列出待沉淀的未覆盖问题。"""
        cond = "1=1"
        params: list[Any] = []
        if user_id is not None:
            cond = "user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"SELECT id, user_id, question, note, ingested, created_at "
                    f"FROM uncovered_questions WHERE {cond} ORDER BY id DESC LIMIT ?",
                    params + [limit],
                ).fetchall()
                return [
                    {"id": r["id"], "user_id": r["user_id"], "question": r["question"],
                     "note": r["note"], "ingested": bool(r["ingested"]), "created_at": r["created_at"]}
                    for r in rows
                ]

    def mark_uncovered_ingested(self, qid: int, user_id: str | None = None) -> bool:
        """标记某条未覆盖问题已被沉淀入知识库。"""
        cond = "id = ?"
        params: list[Any] = [qid]
        if user_id is not None:
            cond += " AND user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(f"UPDATE uncovered_questions SET ingested = 1 WHERE {cond}", params)
                return cur.rowcount > 0

    # ------------------------------------------------------------------
    # 工具审计
    # ------------------------------------------------------------------

    def audit_tool_call(
        self,
        session_id: str,
        tool: str,
        args: dict[str, Any],
        evidence: str,
        ok: bool,
        user_id: str = "default",
    ) -> None:
        """记录一次工具调用（供可观测/合规审计）。"""
        import json

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO tool_audit (session_id, user_id, tool, args, evidence, ok) VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, user_id, tool, json.dumps(args, ensure_ascii=False), evidence[:2000], 1 if ok else 0),
                )

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        """最近的工具调用审计记录（全局，供管理员/可观测）。"""
        import json

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT session_id, user_id, tool, args, evidence, ok, created_at "
                    "FROM tool_audit ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [
                    {
                        "session_id": r["session_id"],
                        "user_id": r["user_id"],
                        "tool": r["tool"],
                        "args": json.loads(r["args"] or "{}"),
                        "evidence": r["evidence"],
                        "ok": bool(r["ok"]),
                        "created_at": r["created_at"],
                    }
                    for r in rows
                ]

    # ------------------------------------------------------------------
    # 真实业务指标：用户反馈（解决率 / 满意率 / 平均耗时）
    # ------------------------------------------------------------------

    def record_feedback(
        self,
        session_id: str,
        query: str,
        user_id: str = "default",
        rating: int = 0,
        resolved: int = -1,
        resolve_seconds: int | None = None,
    ) -> "int | None":
        """记录一条用户对回答的反馈。返回反馈 id。

        rating: 1=👍 好评, -1=👎 差评, 0=未评
        resolved: 1=已解决, 0=未解决, -1=未知
        resolve_seconds: 从提问到「已解决」的秒数（可空）
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(
                    "INSERT INTO feedback (session_id, user_id, query, rating, resolved, resolve_seconds) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        user_id,
                        (query or "")[:500],
                        int(rating),
                        int(resolved),
                        int(resolve_seconds) if resolve_seconds is not None else None,
                    ),
                )
                return cur.lastrowid

    def feedback_stats(self, user_id: str | None = None) -> dict[str, Any]:
        """真实业务指标的反馈侧聚合：解决率 / 满意率 / 平均解决耗时。

        口径说明（面试会问）：
          - 解决率 = 标记「已解决」的反馈数 / 有明确 resolved 判断的反馈数
          - 满意率 = 好评数 / 已评好差评的反馈数
          - 平均解决耗时 = 有 resolve_seconds 的记录的平均值（提问→解决，秒）
        """
        cond = ""
        params: list[Any] = []
        if user_id is not None:
            cond = " WHERE user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                total = conn.execute(
                    f"SELECT COUNT(*) AS n FROM feedback{cond}", params
                ).fetchone()["n"]
                resolved_n = conn.execute(
                    f"SELECT COUNT(*) AS n FROM feedback{cond} WHERE resolved = 1", params
                ).fetchone()["n"]
                unresolved_n = conn.execute(
                    f"SELECT COUNT(*) AS n FROM feedback{cond} WHERE resolved = 0", params
                ).fetchone()["n"]
                positive_n = conn.execute(
                    f"SELECT COUNT(*) AS n FROM feedback{cond} WHERE rating = 1", params
                ).fetchone()["n"]
                negative_n = conn.execute(
                    f"SELECT COUNT(*) AS n FROM feedback{cond} WHERE rating = -1", params
                ).fetchone()["n"]
                avg_row = conn.execute(
                    f"SELECT AVG(resolve_seconds) AS s FROM feedback{cond} WHERE resolve_seconds IS NOT NULL",
                    params,
                ).fetchone()
                judged = resolved_n + unresolved_n
                rated = positive_n + negative_n
                # 按天趋势（近 14 天任一有反馈的天）
                trend = [
                    {"date": r["d"], "resolved": r["rr"], "feedback": r["ff"]}
                    for r in conn.execute(
                        "SELECT date(created_at) AS d, COUNT(*) AS ff, "
                        "SUM(CASE WHEN resolved = 1 THEN 1 ELSE 0 END) AS rr "
                        "FROM feedback GROUP BY date(created_at) ORDER BY d DESC LIMIT 14",
                    ).fetchall()
                ]
        return {
            "total": total,
            "resolved": resolved_n,
            "unresolved": unresolved_n,
            "resolve_rate": round(resolved_n / judged, 4) if judged else None,
            "positive": positive_n,
            "negative": negative_n,
            "satisfaction_rate": round(positive_n / rated, 4) if rated else None,
            "avg_resolve_seconds": round(float(avg_row["s"]), 2) if avg_row and avg_row["s"] is not None else None,
            "trend": trend,
        }

    # ------------------------------------------------------------------
    # 真实业务指标：巡检 incident（自动探测 + 自动诊断）
    # ------------------------------------------------------------------

    def open_incident(
        self,
        target: str,
        url: str,
        kind: str,
        summary: str,
        detail: str,
        user_id: str = "system",
    ) -> tuple[int, bool]:
        """记录/刷新一个「当前异常」的 incident。

        若该 target 已有 open 的 incident，则只更新 summary/detail（保留最早 detected_at，
        便于计算真实 MTTR）；否则新建。返回 (incident_id, is_new)。
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT id FROM incidents WHERE target = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                    (target,),
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE incidents SET summary = ?, detail = ?, url = ?, kind = ? WHERE id = ?",
                        (summary[:2000], detail[:4000], url, kind, row["id"]),
                    )
                    return int(row["id"]), False
                cur = conn.execute(
                    "INSERT INTO incidents (user_id, target, url, kind, status, summary, detail) "
                    "VALUES (?, ?, ?, ?, 'open', ?, ?)",
                    (user_id, target, url, kind, summary[:2000], detail[:4000]),
                )
                return int(cur.lastrowid), True

    def close_incident(self, target: str, user_id: str = "system") -> int | None:
        """把某 target 的 open incident 标记为已解决（恢复健康）。返回被关闭的 id 或 None。"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT id, detected_at FROM incidents WHERE target = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                    (target,),
                ).fetchone()
                if not row:
                    return None
                conn.execute(
                    "UPDATE incidents SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (row["id"],),
                )
                return int(row["id"])

    def list_incidents(self, user_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """巡检 incident 列表（按时间倒序）。"""
        cond = "1=1"
        params: list[Any] = []
        if user_id is not None:
            cond = "user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"SELECT id, user_id, target, url, kind, status, summary, detail, detected_at, "
                    f"resolved_at, diagnosed, diagnosis, diagnosis_ok, diag_elapsed_ms, created_at "
                    f"FROM incidents WHERE {cond} ORDER BY id DESC LIMIT ?",
                    params + [limit],
                ).fetchall()
                return [
                    {
                        "id": r["id"],
                        "user_id": r["user_id"],
                        "target": r["target"],
                        "url": r["url"],
                        "kind": r["kind"],
                        "status": r["status"],
                        "summary": r["summary"],
                        "detail": r["detail"],
                        "detected_at": r["detected_at"],
                        "resolved_at": r["resolved_at"],
                        "diagnosed": bool(r["diagnosed"]),
                        "diagnosis": r["diagnosis"],
                        "diagnosis_ok": bool(r["diagnosis_ok"]),
                        "diag_elapsed_ms": r["diag_elapsed_ms"],
                        "created_at": r["created_at"],
                    }
                    for r in rows
                ]

    def get_incident(self, incident_id: int, user_id: str | None = None) -> dict[str, Any] | None:
        cond = "id = ?"
        params: list[Any] = [incident_id]
        if user_id is not None:
            cond += " AND user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                r = conn.execute(
                    f"SELECT id, user_id, target, url, kind, status, summary, detail, detected_at, "
                    f"resolved_at, diagnosed, diagnosis, diagnosis_ok, diag_elapsed_ms "
                    f"FROM incidents WHERE {cond} LIMIT 1",
                    params,
                ).fetchone()
                return dict(r) if r else None

    def set_incident_diagnosis(
        self,
        incident_id: int,
        diagnosis: str,
        ok: bool,
        elapsed_ms: float | None = None,
    ) -> bool:
        """存储 agent 对 incident 的诊断结果。"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(
                    "UPDATE incidents SET diagnosed = 1, diagnosis = ?, diagnosis_ok = ?, diag_elapsed_ms = ? "
                    "WHERE id = ?",
                    (diagnosis[:8000], 1 if ok else 0, elapsed_ms, incident_id),
                )
                return cur.rowcount > 0

    def incident_stats(self, user_id: str | None = None) -> dict[str, Any]:
        """真实业务指标的 incident 侧聚合：发现数 / 停摆时长(MTTR) / 诊断成功率。"""
        cond = ""
        params: list[Any] = []
        if user_id is not None:
            cond = " WHERE user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                total = conn.execute(
                    f"SELECT COUNT(*) AS n FROM incidents{cond}", params
                ).fetchone()["n"]
                open_n = conn.execute(
                    f"SELECT COUNT(*) AS n FROM incidents{cond} WHERE status = 'open'", params
                ).fetchone()["n"]
                diagnosed_n = conn.execute(
                    f"SELECT COUNT(*) AS n FROM incidents{cond} WHERE diagnosed = 1", params
                ).fetchone()["n"]
                diag_ok_n = conn.execute(
                    f"SELECT COUNT(*) AS n FROM incidents{cond} WHERE diagnosed = 1 AND diagnosis_ok = 1", params
                ).fetchone()["n"]
                # MTTR：从 detected_at 到 resolved_at 的平均秒数（只统计已关闭的）
                mttr_row = conn.execute(
                    f"SELECT AVG((julianday(resolved_at) - julianday(detected_at)) * 86400) AS s "
                    f"FROM incidents{cond} WHERE status = 'resolved' AND resolved_at IS NOT NULL",
                    params,
                ).fetchone()
                # 平均诊断耗时（agent 对一个 incident 给出诊断所需毫秒）
                diag_time = conn.execute(
                    f"SELECT AVG(diag_elapsed_ms) AS s FROM incidents{cond} WHERE diag_elapsed_ms IS NOT NULL",
                    params,
                ).fetchone()
        return {
            "total": total,
            "open": open_n,
            "resolved": total - open_n,
            "diagnosed": diagnosed_n,
            "diagnosis_ok": diag_ok_n,
            "diagnosis_rate": round(diag_ok_n / diagnosed_n, 4) if diagnosed_n else None,
            "mttr_seconds": round(float(mttr_row["s"]), 2) if mttr_row and mttr_row["s"] is not None else None,
            "avg_diag_ms": round(float(diag_time["s"]), 2) if diag_time and diag_time["s"] is not None else None,
        }

    def clear_incidents(self, user_id: str | None = None) -> int:
        """清空 incident 记录（巡检/调试用）。默认清全部；传 user_id 则只清该用户。"""
        cond = "1=1"
        params: list[Any] = []
        if user_id is not None:
            cond = "user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(f"DELETE FROM incidents WHERE {cond}", params)
                return cur.rowcount

    # ------------------------------------------------------------------
    # 自动修复审批（human-in-the-loop）
    # ------------------------------------------------------------------

    def create_remediation(
        self,
        action: str,
        summary: str,
        risk: str,
        user_id: str = "default",
        target: str = "",
        args: dict[str, Any] | None = None,
        incident_id: int | None = None,
    ) -> int:
        """记录一条待审批/待执行的修复请求。"""
        import json

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(
                    "INSERT INTO remediation_approvals "
                    "(user_id, action, target, args, summary, risk, status, incident_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (user_id, action, target, json.dumps(args or {}, ensure_ascii=False),
                     summary[:1000], risk, incident_id),
                )
                return int(cur.lastrowid)

    def list_remediation(
        self, status: str | None = None, user_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        cond = "1=1"
        params: list[Any] = []
        if status is not None:
            cond += f" AND status = ?"
            params.append(status)
        if user_id is not None:
            cond += " AND user_id = ?"
            params.append(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"SELECT id, user_id, action, target, args, summary, risk, status, "
                    f"incident_id, result, created_at, decided_at, executed_at "
                    f"FROM remediation_approvals WHERE {cond} ORDER BY id DESC LIMIT ?",
                    params + [limit],
                ).fetchall()
                import json

                return [
                    {
                        "id": r["id"],
                        "user_id": r["user_id"],
                        "action": r["action"],
                        "target": r["target"],
                        "args": json.loads(r["args"] or "{}"),
                        "summary": r["summary"],
                        "risk": r["risk"],
                        "status": r["status"],
                        "incident_id": r["incident_id"],
                        "result": r["result"],
                        "created_at": r["created_at"],
                        "decided_at": r["decided_at"],
                        "executed_at": r["executed_at"],
                    }
                    for r in rows
                ]

    def get_remediation(self, rid: int) -> dict[str, Any] | None:
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                r = conn.execute(
                    "SELECT id, user_id, action, target, args, summary, risk, status, "
                    "incident_id, result, created_at, decided_at, executed_at "
                    "FROM remediation_approvals WHERE id = ? LIMIT 1",
                    (rid,),
                ).fetchone()
                if not r:
                    return None
                import json

                return {
                    "id": r["id"], "user_id": r["user_id"], "action": r["action"],
                    "target": r["target"], "args": json.loads(r["args"] or "{}"),
                    "summary": r["summary"], "risk": r["risk"], "status": r["status"],
                    "incident_id": r["incident_id"], "result": r["result"],
                    "created_at": r["created_at"], "decided_at": r["decided_at"],
                    "executed_at": r["executed_at"],
                }

    def set_remediation_status(
        self, rid: int, status: str, result: str = "", incident_id: int | None = None
    ) -> bool:
        """更新审批状态（approved/rejected/executed/error），并写时间戳/结果。"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                if status in ("approved", "rejected"):
                    cur = conn.execute(
                        "UPDATE remediation_approvals SET status = ?, result = ?, decided_at = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (status, result[:4000] if status == "rejected" else "", rid),
                    )
                elif status in ("executed", "error"):
                    cur = conn.execute(
                        "UPDATE remediation_approvals SET status = ?, result = ?, executed_at = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (status, result[:4000], rid),
                    )
                else:
                    cur = conn.execute(
                        "UPDATE remediation_approvals SET status = ?, result = ? WHERE id = ?",
                        (status, result[:4000], rid),
                    )
                return cur.rowcount > 0

    def resolve_incident(self, incident_id: int) -> bool:
        """把某 incident 标记为已解决（供自动修复成功后调用，串起 MTTR）。"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(
                    "UPDATE incidents SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP "
                    "WHERE id = ? AND status = 'open'",
                    (incident_id,),
                )
                return cur.rowcount > 0


session_store = SessionStore()
