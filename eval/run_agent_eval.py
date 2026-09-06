"""Agent 排障评测。

--live   : 用真实 openclow /chat/raw 驱动真实 LLM 决策（需配置 OPENCLOW_BASE_URL/API_KEY，
           工具走 sim 模式）。指标：工具序列正确率、结论命中、越界拒答。
默认/--mock: 用脚本化客户端走 agent 循环，验证编排管线是否生效（CI/无网络用，
           不衡量真实模型效果）。

输出：eval/agent_results.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.openclow_client import OpenClowClient

BASE = Path(__file__).resolve().parent


class ScriptClient:
    """脚本化客户端：按 expected_tools 依次返回工具 action，最后返回 expected_report。"""

    def __init__(self, case: dict) -> None:
        self.case = case
        self.script: list[str] = []
        for tool in case.get("expected_tools", []):
            self.script.append(json.dumps({"action": "tool", "tool": tool, "args": {}}, ensure_ascii=False))
        final = {"action": "final", "report": case.get("expected_report", {})}
        self.script.append(json.dumps(final, ensure_ascii=False))

    def chat_raw(self, messages, temperature=0.3, max_tokens=None):
        if not self.script:
            raise AssertionError("脚本用尽")
        return self.script.pop(0)

    def chat_tools(self, messages, tools, tool_choice="auto", temperature=0.3, max_tokens=None):
        return {"content": "", "tool_calls": None}

    def health(self):
        return {"status": "ok"}

    def search(self, query, top_k=None, rerank=None):
        return []


def _match(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    t = (text or "").lower()
    return any(k.lower() in t for k in keywords)


def _grade_live(case: dict, result: dict) -> tuple[bool, bool, bool]:
    """真实模式下：工具序列、结论、拒答是否达标。"""
    answer = result.get("answer", "")
    report = result.get("report") or {}
    tools = [t.get("tool", "") for t in result.get("tool_trails", [])]
    want_tools = case.get("expected_tools", [])
    # 允许子集：搜 runbook 等关键工具被调用即可
    tool_ok = any(w in tools for w in want_tools) if want_tools else True
    # 最终回答是自然语言 markdown，直接按结论文本里的关键词打
    conclusion_ok = _match(answer, case.get("expect_root_cause", [])) and \
        _match(answer, case.get("expect_actions", []))
    if case.get("out_of_scope"):
        refusal_ok = report.get("ok", True) is False or _match(answer, ("信息不足", "无法确定", "超出", "无法"))
    else:
        refusal_ok = report.get("ok", False) is True  # 正常情况必须给出结论
    return tool_ok, conclusion_ok, refusal_ok


def _grade_mock(case: dict, result: dict) -> tuple[bool, bool, bool]:
    """模拟模式：验证编排是否正确执行工具序列并产出结构化报告。"""
    tools = [t.get("tool", "") for t in result.get("tool_trails", [])]
    tool_ok = tools == case.get("expected_tools", [])
    report = result.get("report") or {}
    if case.get("out_of_scope"):
        rejection_ok = report.get("ok", True) is False
        return tool_ok, True, rejection_ok
    structured_ok = (report.get("ok", False) is True and bool(report.get("root_cause")) and bool(report.get("actions")))
    return tool_ok, structured_ok, True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="用真实 LLM 驱动（需要线上 openclow 连接）")
    args = ap.parse_args()

    cases = json.loads((BASE / "cases.json").read_text(encoding="utf-8"))
    from agent.loop import run

    stats = {"tool": 0, "conclusion": 0, "refusal": 0, "total": 0}
    details = []

    for case in cases:
        client = OpenClowClient() if args.live else ScriptClient(case)
        t0 = time.time()
        result = run(case["symptom"], session_id=None, client=client)
        elapsed = round((time.time() - t0) * 1000, 1)

        grader = _grade_live if args.live else _grade_mock
        tool_ok, conclusion_ok, refusal_ok = grader(case, result)

        stats["tool"] += int(tool_ok)
        stats["conclusion"] += int(conclusion_ok)
        stats["refusal"] += int(refusal_ok)
        stats["total"] += 1

        details.append({
            "id": case["id"], "symptom": case["symptom"], "out_of_scope": case.get("out_of_scope", False),
            "tool_ok": tool_ok, "conclusion_ok": conclusion_ok, "refusal_ok": refusal_ok,
            "tools_used": [t.get("tool", "") for t in result.get("tool_trails", [])],
            "report": result.get("report"), "elapsed_ms": elapsed,
        })

    summary = {
        "mode": "live" if args.live else "mock",
        "tool_call_accuracy": round(stats["tool"] / max(stats["total"], 1), 3),
        "conclusion_accuracy": round(stats["conclusion"] / max(stats["total"], 1), 3),
        "refusal_accuracy": round(stats["refusal"] / max(stats["total"], 1), 3),
        "total": stats["total"],
        "details": details,
    }
    out = BASE / "agent_results.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"模式: {'live（真实 LLM）' if args.live else 'mock（编排管线）'}")
    print(f"工具序列正确率: {summary['tool_call_accuracy']:.1%}")
    print(f"结论正确率: {summary['conclusion_accuracy']:.1%}")
    print(f"拒答正确率: {summary['refusal_accuracy']:.1%}")
    print(f"结果写入: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
