"""把 agent 评测的轨迹快照渲染成可读 Markdown（面试展示用）。

读取 eval/agent_results.json（由 run_agent_eval 生成），输出 eval/trail_report.md。
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main() -> int:
    src = BASE / "agent_results.json"
    if not src.exists():
        print(f"未找到 {src}，请先运行：python -m eval.run_agent_eval")
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    mode = data.get("mode", "mock")
    lines = [
        "# Agent 排障轨迹快照",
        "",
        f"- 模式：`{'真实 LLM' if mode == 'live' else 'mock（编排管线）'}`",
        f"- 工具序列正确率：**{data.get('tool_call_accuracy', 0):.1%}**",
        f"- 结论正确率：**{data.get('conclusion_accuracy', 0):.1%}**",
        f"- 拒答正确率：**{data.get('refusal_accuracy', 0):.1%}**",
        "",
    ]
    for d in data.get("details", []):
        rep = d.get("report") or {}
        tools = d.get("tools_used", []) or []
        sev = rep.get("severity", "-")
        lines.append(f"## {d['id']} · {d['symptom']}")
        lines.append("")
        lines.append(f"- 越界/拒答：{'是' if d.get('out_of_scope') else '否'}")
        lines.append(f"- 工具序列：{', '.join(tools) if tools else '（未调用工具）'}")
        lines.append(f"- 结论：ok={rep.get('ok', '?')} / 严重度={sev} / 置信度={rep.get('confidence', '-')}")
        if rep.get("root_cause"):
            lines.append(f"- 判断根因：{rep['root_cause']}")
        acts = rep.get("actions") or []
        if acts:
            lines.append(f"- 处置步骤：{len(acts)} 条 → " + "；".join(acts[:3]) + ("…" if len(acts) > 3 else ""))
        lines.append("")

    out = BASE / "trail_report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"轨迹快照已写入：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
