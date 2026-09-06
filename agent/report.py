"""结构化诊断报告：agent 输出的规范化结果，便于前端展示与评测。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DiagnosisReport(BaseModel):
    """一次排障的结论。"""

    ok: bool = Field(False, description="是否给出了可执行的诊断结论")
    symptom: str = Field("", description="用户描述的症状/复述")
    evidence: list[str] = Field(default_factory=list, description="关键证据摘要（来自工具调用）")
    root_cause: str = Field("", description="判断的根因")
    severity: str = Field("medium", description="严重度: critical/high/medium/low/unknown")
    actions: list[str] = Field(default_factory=list, description="可执行的处置步骤")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="置信度 0~1")
    sources: list[str] = Field(default_factory=list, description="参考来源（runbook/文档）")

    def to_markdown(self) -> str:
        """渲染成给用户看的多行文本。"""
        sev = {
            "critical": "🔴 严重", "high": "🟠 高", "medium": "🟡 中",
            "low": "🟢 低", "unknown": "⚪ 未知",
        }.get(self.severity.lower(), self.severity)
        lines: list[str] = []
        if self.symptom:
            lines.append(f"**症状**：{self.symptom}")
        if self.evidence:
            lines.append("**采集到的证据**：")
            lines.extend(f"- {e}" for e in self.evidence[:6])
        if self.root_cause:
            lines.append(f"**判断根因**：{self.root_cause}")
        lines.append(f"**严重度**：{sev}（置信度 {self.confidence:.0%}）")
        if self.actions:
            lines.append("**建议处置**：")
            lines.extend(f"{i}. {a}" for i, a in enumerate(self.actions, 1))
        if self.sources:
            lines.append(f"**参考来源**：{', '.join(self.sources)}")
        if not self.ok:
            lines.append("（当前信息不足以给出确定结论，建议补充更多现象或由人工介入。）")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
