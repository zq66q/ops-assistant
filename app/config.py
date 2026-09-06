"""应用配置，优先从 .env 读取。

在原本 `openclow 平台调用 + 业务应用基础配置` 之上，新增了
agentic 运维排障助手（真实/模拟工具、JSON/原生工具协议、审计）所需配置。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # ── openclow 平台 ──
    openclow_base_url: str = os.getenv("OPENCLOW_BASE_URL", "http://localhost:8000").rstrip("/")
    openclow_api_key: str = os.getenv("OPENCLOW_API_KEY", "")

    # ── 业务应用 ──
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8600"))
    ops_api_key: str = os.getenv("OPS_ASSISTANT_API_KEY", "")

    # ── 会话 / 审计 ──
    session_db_path: str = os.getenv("OPS_SESSION_DB_PATH", "./data/sessions.db")
    audit_db_path: str = os.getenv("OPS_AUDIT_DB_PATH", "./data/tool_audit.db")

    # ── RAG 检索 ──
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "5"))
    rag_rerank: bool = os.getenv("RAG_RERANK", "false").lower() == "true"
    runbook_top_k: int = int(os.getenv("RUNBOOK_TOP_K", "4"))

    # ── Query 改写 ──
    rewrite_trigger_words: set[str] = frozenset(
        os.getenv("REWRITE_TRIGGER_WORDS", "它,这个,那个,他,她,这,那,前面,刚才").split(",")
    )

    # ── Agent 工具排障 ──
    # tool_mode: "sim"=用固定样本（默认，可复现/可测试）；"real"=对真实服务探活/拉日志/查资源
    tool_mode: str = os.getenv("OPS_TOOL_MODE", "sim")
    # agent_tool_protocol: "json"=LLM 输出 JSON action（对当前线上 /chat/raw 即可用）
    #                       "native"=原生 function-calling（需 openclow 升级到支持 tools 的 /chat/raw）
    agent_tool_protocol: str = os.getenv("OPS_AGENT_TOOL_PROTOCOL", "json")
    agent_max_steps: int = int(os.getenv("OPS_AGENT_MAX_STEPS", "10"))
    agent_temperature: float = float(os.getenv("OPS_AGENT_TEMPERATURE", "0.3"))
    agent_max_tokens: int = int(os.getenv("OPS_AGENT_MAX_TOKENS", "1200"))
    agent_timeout_s: float = float(os.getenv("OPS_AGENT_TIMEOUT_S", "120"))

    # ── 排障靶点（real 模式用） ──
    ops_target_health: str = os.getenv("OPS_TARGET_HEALTH", "http://103.236.98.200:8000/health")
    ops_target_ui: str = os.getenv("OPS_TARGET_UI", "http://103.236.98.200:8501")

    # ── 服务路径（real 模式查日志/进程用；无权限时降级为样本） ──
    ops_log_dir: str = os.getenv("OPS_LOG_DIR", "/opt/openclaw/logs")
    ops_service_name: str = os.getenv("OPS_SERVICE_NAME", "openclaw-api")

    # ── 真实业务指标：巡检 / incident ──
    # monitors_enabled: 是否开启后台健康巡检（真实 incident 的来源；不依赖真人）
    monitors_enabled: bool = os.getenv("OPS_MONITOR_ENABLED", "true").lower() == "true"
    # monitors_interval_s: 巡检间隔（秒）
    monitors_interval_s: int = int(os.getenv("OPS_MONITOR_INTERVAL_S", "60"))
    # auto_diagnose: 巡检发现异常后是否自动调 agent 对该 incident 产出诊断
    auto_diagnose: bool = os.getenv("OPS_MONITOR_AUTO_DIAGNOSE", "true").lower() == "true"
    # incident 归属的用户（用于多用户隔离；默认系统级）
    incident_user: str = os.getenv("OPS_INCIDENT_USER", "system")

    @property
    def is_real_tool(self) -> bool:
        return self.tool_mode.lower() == "real"

    @property
    def is_native_tool(self) -> bool:
        return self.agent_tool_protocol.lower() == "native"

    @property
    def monitor_targets(self) -> dict[str, str]:
        """巡检靶点：name -> url。默认探 openclow 平台与前端。

        可用 OPS_MONITOR_TARGETS={"openclow-api":"http://host/health",...} 覆盖（JSON）。
        探测到异常即产生真实 incident → agent 诊断 → 业务指标（MTTR/诊断率）。
        """
        import json

        raw = os.getenv("OPS_MONITOR_TARGETS", "")
        if raw:
            try:
                val = json.loads(raw)
                if isinstance(val, dict) and val:
                    return val
            except json.JSONDecodeError:
                pass
        return {
            "openclow-api": self.ops_target_health,
            "openclow-ui": self.ops_target_ui,
        }

    @property
    def users(self) -> dict[str, str]:
        """多用户：user_id -> api_key 映射（JSON 字符串）。

        配置后，身份由凭证（X-API-Key）决定，不再信任客户端自报的 X-User-Id。
        示例：OPS_ASSISTANT_USERS={"alice":"ops_key_alice","bob":"ops_key_bob"}
        """
        import json

        raw = os.getenv("OPS_ASSISTANT_USERS", "")
        if not raw:
            return {}
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except json.JSONDecodeError:
            return {}


settings = Settings()
