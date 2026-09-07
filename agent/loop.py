"""Agent 工具循环：改写 → (可选)RAG seed → 决策/调用工具 → 最终诊断报告。

对外提供 run(query, session_id, client) -> dict，与旧 orchestrator.answer() 返回键兼容，
并额外带上 report(结构化诊断) 与 tool_trails(工具轨迹，供前端/评测)。
"""
from __future__ import annotations

import time
from typing import Any, Callable

from agent.llm_tool_client import LLMToolError, decide
from agent.report import DiagnosisReport
from app.config import settings
from app.openclow_client import OpenClowClient
from app.rewriter import rewrite_query
from app.session import session_store
from tools.executor import execute_tool
from tools.registry import list_tools

AGENT_SYSTEM_PROMPT = """你是智能运维排障助手。目标是针对用户报告的服务/应用问题，先收集真实证据，再给出诊断与处置。

规则：
1. 优先调用工具收集证据（探活、日志、资源、服务状态、排障手册），不要凭经验直接下结论。
2. 每个工具调用都要有明确目的；一次只调一个工具，拿到结果后再决定下一步。
3. 收集到足够证据后，给出最终诊断：症状、依据(证据)、判断根因、严重度、处置步骤、置信度、来源。
4. 证据不足或超出能力时，明确说明无法确定，不要编造。
5. 涉及破坏性操作（重启/改配置）只建议，不要声称已执行。
6. 【收敛】一般调用 2~4 个工具、证据足够后，就必须立刻给出最终诊断；不要重复调用已用过的工具，不要为了“检查”而无休止调用。
7. 【修复】用户明确要求“帮我修/重启/清理”时，可调用 remediate 工具发起处置。工具会做风险分级：低风险自动执行、高风险生成待审批、不在白名单一律拒绝。你只需发起动作并把工具返回结果如实呈现，由系统保证安全与审批；不要绕过工具、不要声称已执行高风险操作。

输出格式：
A) 需要调用工具时，输出一个 JSON（不要输出其它文字）：
{"action":"tool","tool":"<工具名>","args":{...}}
B) 收集完证据、可以直接给结论时，直接输出一段可读的 markdown 自然语言诊断。
   不要输出任何 JSON、不要以 { 开头。自然包含：症状、依据(证据)、判断根因、严重度、处置步骤、一句话总结。
"""


def _user_round_prompt(query: str, history: list[dict[str, str]]) -> str:
    hist = ""
    if history:
        parts = [f"{('用户' if m['role'] == 'user' else '助手')}: {m['content']}" for m in history[-4:]]
        hist = "\n".join(parts)
        hist = f"\n\n对话历史：\n{hist}"
    return f"用户问题：{query}{hist}"


def _tool_prompt() -> str:
    tools = list_tools()
    return "\n".join(t.to_prompt() for t in tools)


def _final_from_dict(data: dict[str, Any]) -> DiagnosisReport:
    """尽力把模型输出的 report 塞进 DiagnosisReport（缺字段给默认值）。

    ok 由内容自动判定：有「根因」且给出「处置步骤」且根因不是拒绝性表述 → True；
    否则（信息不足 / 越界 / 无处置）→ False，避免模型误设 ok。
    """
    rep = data if isinstance(data, dict) else {}
    evidence = rep.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    actions = rep.get("actions") or []
    if isinstance(actions, str):
        actions = [actions]
    sources = rep.get("sources") or []
    if isinstance(sources, str):
        sources = [sources]
    root_cause = str(rep.get("root_cause", "")).strip()
    actions = [str(a) for a in actions]
    refusal_markers = ("信息不足", "无法确定", "无法判断", "信息不够", "不足以", "超出", "未知", "无法给出")
    has_conclusion = bool(root_cause) and bool(actions) and not any(m in root_cause for m in refusal_markers)
    return DiagnosisReport(
        ok=has_conclusion,
        symptom=str(rep.get("symptom", "")),
        evidence=[str(e) for e in evidence],
        root_cause=root_cause,
        severity=str(rep.get("severity", "medium")),
        actions=actions,
        confidence=float(rep.get("confidence", 0.5) or 0.5),
        sources=[str(s) for s in sources],
    )


def _fallback(text: str) -> DiagnosisReport:
    """模型没按 JSON 输出时兜底：把原文当答复，置信度给低。"""
    return DiagnosisReport(
        ok=False,
        symptom="",
        evidence=[],
        root_cause="",
        severity="unknown",
        actions=[],
        confidence=0.2,
        sources=[],
    )


_NATURAL_REFUSAL = ("信息不足", "无法确定", "无法判断", "信息不够", "不足以", "超出", "无法给出", "未知", "不清楚")


def _final_from_natural(text: str) -> DiagnosisReport:
    """自然语言最终回答 → 判定是否为有效诊断（非拒绝），供 markdown/评测使用。"""
    is_refusal = any(m in text for m in _NATURAL_REFUSAL)
    return DiagnosisReport(
        ok=not is_refusal,
        symptom="",
        evidence=[],
        root_cause="",
        severity="unknown" if is_refusal else "medium",
        actions=[],
        confidence=0.25 if is_refusal else 0.7,
        sources=[],
    )


# 证据截断上限（避免工具输出过长撑爆 prompt / 上下文）
_EVIDENCE_MAX = 1200


def _truncate(text: str, limit: int = _EVIDENCE_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…(已截断，原长 {len(text)} 字符)"


def _decide_with_retry(client, messages, tools_schema, tool_prompt, retries: int = 2, delay: float = 1.0):
    """LLM 决策调用带有限重试（幂等重试），仍失败则抛出 LLMToolError 由上层兜底。"""
    import time

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return decide(client, messages, tools_schema=tools_schema, tool_prompt=tool_prompt)
        except LLMToolError as exc:
            last = exc
            if attempt < retries:
                time.sleep(delay * (attempt + 1))
    if last is not None:
        raise last
    raise LLMToolError("LLM 决策重试失败")


def run(
    query: str,
    session_id: str | None = None,
    client: OpenClowClient | None = None,
    observe: Callable[[dict[str, Any]], None] | None = None,
    user_id: str = "default",
) -> dict[str, Any]:
    t0 = time.perf_counter()
    client = client or OpenClowClient()
    history = session_store.history(session_id, user_id=user_id) if session_id else []

    # 1. Query 改写（复用）：把「那怎么修复？」这类追问还原成独立问题
    rewritten = rewrite_query(query, history, client=client)
    is_rewritten = rewritten != query
    # sim 模式：按当前问句设置场景上下文，让工具返回对应场景的样本证据
    import tools.mock_data as mock_data

    mock_data.set_context(rewritten or query)

    tools_schema = [t.to_schema() for t in list_tools()]
    tool_prompt = _tool_prompt()
    system_prompt = f"{AGENT_SYSTEM_PROMPT}\n\n可用工具：\n{tool_prompt}"

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _user_round_prompt(query, history)},
    ]

    report = DiagnosisReport()
    tool_trails: list[dict[str, Any]] = []
    search_results: list[dict[str, Any]] = []
    last_text = ""
    nudged = False  # 工具数较多后给一次“请收敛”的提示，避免无限调用
    runbook_used = False  # search_runbook 是否已用过（用于硬拦截重复调用）
    steps_done = 0

    # 2. RAG-first：每次提问都【先查知识库】，确保回答有依据（真实 agent 只基于知识库）
    seed_q = rewritten or query
    seed = execute_tool("search_runbook", {"query": seed_q})
    runbook_used = True
    steps_done = 1
    tool_trails.append({"step": 1, "tool": "search_runbook", "args": {"query": seed_q},
                        "ok": seed["ok"], "elapsed_ms": seed["elapsed_ms"]})
    session_store.audit_tool_call(session_id or "anon", "search_runbook", {"query": seed_q},
                                  seed["evidence"], seed["ok"], user_id)
    messages.append({"role": "user", "content": f"工具 search_runbook 返回：\n{_truncate(seed['evidence'])}"})
    messages.append({"role": "user", "content":
                     "已检索知识库。请【只】基于上面检索到的知识库信息回答；若未检索到相关内容，请明确说明“知识库中没有相关信息”，不要编造。"
                     "如确需更多证据可调用其它工具，但不要重复调用 search_runbook。"})
    if observe:
        observe({"type": "tool", "step": 1, "tool": "search_runbook", "args": {"query": seed_q},
                 "ok": seed["ok"], "elapsed_ms": seed["elapsed_ms"],
                 "summary": seed["evidence"][:200], "rewritten": rewritten})
    if seed["ok"]:
        search_results.append({"metadata": {"source": "runbook"}, "text": seed["evidence"], "score": 1.0})
    # 知识库没检索到相关内容 -> 记录为「未覆盖问题」，供后续沉淀进知识库
    if seed["ok"] and ("未检索到相关排障手册片段" in seed["evidence"] or "未找到与描述匹配的排障手册" in seed["evidence"]):
        try:
            session_store.record_uncovered(seed_q, user_id=user_id)
        except Exception:
            pass

    for step in range(settings.agent_max_steps):
        # 已用 >=4 个工具仍没给结论：注入一次收敛提示
        if len(tool_trails) >= 4 and not nudged:
            nudged = True
            messages.append({"role": "user", "content": "证据已足够。请不要再调用工具，直接给出最终诊断（markdown 自然语言）。"})
        try:
            decision = _decide_with_retry(client, messages, tools_schema=tools_schema, tool_prompt=tool_prompt)
        except LLMToolError as exc:
            last_text = f"⚠️ 排障引擎调用失败（{exc}）。"
            report = _fallback(last_text)
            answer_text = last_text
            break

        if decision["type"] == "tool":
            name = decision["tool"]
            args = decision.get("args", {})
            # 硬拦截：search_runbook 只允许用一次；重复调用则强引导收敛，不再真检索
            if name == "search_runbook" and runbook_used:
                messages.append(
                    {"role": "user", "content": "search_runbook 已调用过，不能重复检索。请基于已有证据直接给出最终诊断（不要再调用 search_runbook）。"}
                )
                continue
            result = execute_tool(name, args)
            if name == "search_runbook":
                runbook_used = True
            summary = result["evidence"][:160]
            tool_trails.append(
                {"step": step + 1 + steps_done, "tool": name, "args": args, "ok": result["ok"], "elapsed_ms": result["elapsed_ms"]}
            )
            # 审计：写工具调用记录
            session_store.audit_tool_call(
                session_id=session_id or "anon", tool=name, args=args,
                evidence=result["evidence"], ok=result["ok"], user_id=user_id,
            )
            messages.append(
                {"role": "user", "content": f"工具 {name} 返回：\n{_truncate(result['evidence'])}"}
            )
            # 已用过 search_runbook：提醒模型别再重复调，直接给结论
            if name == "search_runbook":
                messages.append({"role": "user", "content": "已检索到排障手册片段（见上）。若证据已足够，请直接给出最终诊断，不要重复调用 search_runbook。"})
            if observe:
                observe({"type": "tool", "step": step + 1 + steps_done, "tool": name, "args": args, "ok": result["ok"], "elapsed_ms": result["elapsed_ms"], "summary": result["evidence"][:200], "rewritten": rewritten})
            # 保留检索片段（search_runbook 才会产生）
            if name == "search_runbook" and result["ok"]:
                search_results.append({"metadata": {"source": "runbook"}, "text": result["evidence"], "score": 1.0})
            continue

        if decision["type"] == "final":
            report = _final_from_dict(decision.get("report", {}))
            answer_text = report.to_markdown()
            break

        # 自然语言最终回答（模型未走 JSON action）：直接渲染，绝不再显示原始 JSON
        natural = decision.get("text", "").strip()
        if not natural or natural.startswith("{"):
            # 模型仍输出了 JSON（可能是坏的）或空：不把原始 JSON 给用户，给一句干净提示
            natural = "模型未按格式给出最终结论（可能返回了 JSON）。请结合上方工具已收集到的证据，或换个问法再试。"
        report = _final_from_natural(natural)
        answer_text = natural
        break
    else:
        # 达到最大步数仍没给出 final
        report = DiagnosisReport(
            ok=False,
            symptom=query,
            evidence=[t["tool"] for t in tool_trails],
            root_cause="达到最大工具调用步数仍未收敛，请补充更多现象。",
            severity="unknown",
            confidence=0.3,
        )
        answer_text = report.to_markdown()

    if observe:
        observe({"type": "final", "report": report.to_dict(), "answer": answer_text, "rewritten": rewritten})

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    # 轻量遥测：步数、工具数、估算 token（len/4 粗略）
    steps_taken = len(tool_trails) + (1 if report.ok else 0)
    est_tokens = (len(query) + sum(len(t["tool"]) for t in tool_trails) + len(answer_text)) // 4

    # 保存会话
    if session_id:
        session_store.append(session_id, "user", query, user_id=user_id)
        session_store.append(session_id, "assistant", answer_text, user_id=user_id)

    return {
        "answer": answer_text,
        "session_id": session_id,
        "rewritten": rewritten,
        "report": report.to_dict(),
        "tool_trails": tool_trails,
        "search_results": search_results,
        "elapsed_ms": elapsed_ms,
        "steps_taken": steps_taken,
        "tool_count": len(tool_trails),
        "est_tokens": est_tokens,
    }
