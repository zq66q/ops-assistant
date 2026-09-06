"""RAG 检索评测：Recall@k / MRR（评测集的第 4 项指标）。

--live   : 调用真实 openclow /rag/search，测真实召回（需已灌入 runbooks + 语料）。
默认/mock: 用合成检索结果验证指标数学是否正确（非真实效果）。

输出：eval/retrieval_results.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.openclow_client import OpenClowClient

BASE = Path(__file__).resolve().parent


def _sources(results: list[dict]) -> list[str]:
    return [r.get("metadata", {}).get("source", "") for r in results]


def recall_at_k(sources: list[str], relevant: set[str], k: int) -> float:
    # 统计 top-k 里命中的“不同相关来源”，再除以相关来源总数（上限 1.0，避免同一来源多个 chunk 重复计数）
    top = [s for s in sources[:k]]
    distinct_hits = len({s for s in top if s in relevant})
    return min(distinct_hits / max(len(relevant), 1), 1.0)


def mrr(sources: list[str], relevant: set[str]) -> float:
    for rank, s in enumerate(sources, 1):
        if s in relevant:
            return 1.0 / rank
    return 0.0


class MockSearch:
    """把相关 source 放在 rank≈2，用于验证指标计算为「非」全 1 的确定值。"""

    def __init__(self, cases: list[dict]) -> None:
        self.by_query = {c["query"]: c["relevant_sources"] for c in cases}

    def search(self, query: str, top_k: int | None = None, rerank: bool | None = None) -> list[dict]:
        rel = self.by_query.get(query, [])
        # order: 无关源, 相关源[0], 相关源[1], ... => recall@1=0, MRR=0.5（用于证明 metric 真在算）
        vals = ["runbook/mock_无关源", *rel][: (top_k or 5)]
        return [{"metadata": {"source": s}, "text": s, "score": 1.0} for s in vals]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="用真实 openclow /rag/search")
    args = ap.parse_args()

    cases = json.loads((BASE / "retrieval_cases.json").read_text(encoding="utf-8"))
    client: "OpenClowClient | MockSearch" = OpenClowClient() if args.live else MockSearch(cases)

    agg = {"recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0, "mrr": 0.0}
    details = []
    for case in cases:
        rel = set(case["relevant_sources"])
        results = client.search(case["query"], top_k=5, rerank=False)
        sources = _sources(results)
        row = {
            "id": case["id"],
            "recall@1": round(recall_at_k(sources, rel, 1), 3),
            "recall@3": round(recall_at_k(sources, rel, 3), 3),
            "recall@5": round(recall_at_k(sources, rel, 5), 3),
            "mrr": round(mrr(sources, rel), 3),
            "retrieved_sources": sources[:5],
        }
        agg["recall@1"] += row["recall@1"]
        agg["recall@3"] += row["recall@3"]
        agg["recall@5"] += row["recall@5"]
        agg["mrr"] += row["mrr"]
        details.append(row)

    n = max(len(cases), 1)
    for key in agg:
        agg[key] = round(agg[key] / n, 3)

    summary = {"mode": "live" if args.live else "mock", "cases": len(cases), **agg, "details": details}
    out = BASE / "retrieval_results.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"模式: {'live（真实 RAG 检索）' if args.live else 'mock（验证指标数学）'}")
    print(f"Recall@1: {agg['recall@1']:.1%}")
    print(f"Recall@3: {agg['recall@3']:.1%}")
    print(f"Recall@5: {agg['recall@5']:.1%}")
    print(f"MRR:      {agg['mrr']:.3f}")
    print(f"结果写入: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
