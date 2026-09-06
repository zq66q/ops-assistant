"""排障手册检索工具：RAG 检索 openclow 知识库中的排障手册片段。

检索总是【优先查真实知识库 /rag/search】（无论 sim/real 模式，因为知识库才是重点）；
只有真实检索失败/无结果时，才回退到内置样本（保证演示不崩）。
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from tools import mock_data
from tools.registry import Tool

# 是否允许在 sim 模式下也尝试真实知识库检索（默认 true；你连了真实服务器，就该用真库）
_TRY_REAL_IN_SIM = True


def _real(args: dict[str, Any]) -> dict[str, Any]:
    from app.openclow_client import OpenClowClient  # 延迟导入防循环

    query = str(args.get("query", "")).strip()
    if not query:
        return {"ok": True, "evidence": "（search_runbook 缺少 query 参数）"}
    try:
        results = OpenClowClient().search(query, top_k=settings.runbook_top_k, rerank=settings.rag_rerank)
    except Exception as exc:
        return {"ok": False, "evidence": f"RAG 检索失败（{type(exc).__name__}: {exc}）"}
    if not results:
        return {"ok": True, "evidence": "（未检索到相关排障手册片段）"}
    parts = []
    for i, r in enumerate(results, 1):
        src = r.get("metadata", {}).get("source", "unknown")
        txt = r.get("text", "")
        score = r.get("score", 0.0)
        parts.append(f"[{i}] 来源: {src} (相关度: {score:.4f})\n{txt}")
    return {"ok": True, "evidence": "\n\n".join(parts)}


def _sim(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "evidence": mock_data.runbook_evidence(str(args.get("query", "")))}


def execute(args: dict[str, Any]) -> dict[str, Any]:
    """优先查真实知识库；失败或无结果时回退内置样本。"""
    if settings.is_real_tool or _TRY_REAL_IN_SIM:
        res = _real(args)
        if res.get("ok", False) and res["evidence"].strip() and not res["evidence"].startswith("（未检索到"):
            return res
        # 真实检索失败或没命中 → 回退内置样本（避免演示崩）
        return _sim(args)
    return _sim(args)


TOOL = Tool(
    name="search_runbook",
    description="在排障手册知识库里检索与该问题相关的运维文档片段，用于给判断提供已知故障模式与处置步骤。",
    parameters=[
        {"name": "query", "type": "string", "desc": "检索关键词/问题描述", "required": True},
        {"name": "top_k", "type": "integer", "desc": "返回片段数，缺省 4", "required": False},
    ],
    handler=execute,
)
