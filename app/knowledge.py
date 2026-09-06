"""知识沉淀：把一次排障结论写成 runbook 并灌入知识库（幂等）。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.openclow_client import OpenClowClient


def build_runbook(entry: dict[str, Any]) -> str:
    """把 {title, symptom, root_cause, actions, source} 渲染成 markdown runbook。"""
    title = str(entry.get("title") or "未命名排障").strip()
    symptom = str(entry.get("symptom") or "").strip()
    root_cause = str(entry.get("root_cause") or "").strip()
    actions = entry.get("actions") or []
    if isinstance(actions, str):
        actions = [actions]
    source = str(entry.get("source") or "用户沉淀").strip()
    lines = [f"# {title}", "", "症状：", f"- {symptom}", "", "根因：", f"- {root_cause}", "", "处置步骤："]
    if actions:
        lines.extend(f"{i}. {a}" for i, a in enumerate(actions, 1))
    else:
        lines.append("- （补充处置步骤）")
    lines += ["", f"来源：{source}", ""]
    return "\n".join(lines)


def persist_and_ingest(entry: dict[str, Any]) -> dict[str, Any]:
    """写 runbook 文件到 data/runbooks/，并调 /rag/ingest 灌进知识库（同 title 幂等）。

    Returns:
        {"file": str, "ingested": bool, "chunks": int, "source": str}
    """
    title = str(entry.get("title") or "knowledge").strip().replace(" ", "_")[:60] or "knowledge"
    md = build_runbook(entry)
    # 1. 写本地文件（幂等：同 title 覆盖同名文件）
    runbooks_dir = Path(__file__).resolve().parent.parent / "data" / "runbooks"
    runbooks_dir.mkdir(parents=True, exist_ok=True)
    fpath = runbooks_dir / f"{title}.md"
    fpath.write_text(md, encoding="utf-8")
    # 2. 灌库（幂等：同 source + 同内容会跳过，返回 chunks:0）
    source = f"runbooks/{title}"
    client = OpenClowClient()
    try:
        ingest = client.ingest_text(
            md,
            source=source,
            metadata={"category": "ops", "origin": "user-ingested", "kind": "runbooks"},
        )
        chunks = int(ingest.get("chunks", 0))
    except Exception as exc:
        return {"file": str(fpath), "ingested": False, "chunks": 0, "source": source, "error": str(exc)}
    return {"file": str(fpath), "ingested": True, "chunks": chunks, "source": source}
