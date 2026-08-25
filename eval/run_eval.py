"""运维排障助手评测集。

包含两类问题：
- direct: 直问式，考察基础召回
- followup: 追问式，考察 query 改写是否生效
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.openclow_client import OpenClowClient
from app.orchestrator import answer
from app.rewriter import rewrite_query


EVAL_QA_SET = [
    # 架构篇
    {"id": "arch-1", "category": "direct", "query": "openclow 后端和前端分别用什么框架？", "expected": ["FastAPI", "Streamlit"]},
    {"id": "arch-2", "category": "direct", "query": "openclow 的架构分层有几层？", "expected": ["7", "L1", "L7"]},
    {"id": "arch-3", "category": "direct", "query": "生产环境的反向代理用的是什么？", "expected": ["Caddy"]},
    # 部署篇
    {"id": "deploy-1", "category": "direct", "query": "服务器上 openclow 实际是用什么方式运行的？", "expected": ["systemd", "openclaw-api.service", "openclaw-ui.service"]},
    {"id": "deploy-2", "category": "direct", "query": "部署目录在哪里？", "expected": ["/opt/openclow"]},
    {"id": "deploy-3", "category": "direct", "query": "代码更新到服务器后要怎么生效？", "expected": ["SFTP", "systemctl restart", "restart"]},
    # 端口与备案
    {"id": "port-1", "category": "direct", "query": "备案期间 80 和 443 为什么访问不了？", "expected": ["被封", "备案", "管局"]},
    {"id": "port-2", "category": "direct", "query": "备案期间怎么访问后端和前端？", "expected": ["103.236.98.200:8000", "103.236.98.200:8501", "IP:8000", "IP:8501"]},
    {"id": "port-3", "category": "direct", "query": "FastAPI 和 Streamlit 默认分别跑在哪个端口？", "expected": ["8000", "8501"]},
    # 认证
    {"id": "auth-1", "category": "direct", "query": "openclow API 鉴权用什么请求头？", "expected": ["X-API-Key"]},
    {"id": "auth-2", "category": "direct", "query": "API Key 在 .env 里存在哪个变量？", "expected": ["OPENCLAW_API_KEYS"]},
    {"id": "auth-3", "category": "direct", "query": "Swagger 页面上怎么带认证？", "expected": ["Authorize", "X-API-Key"]},
    # RAG
    {"id": "rag-1", "category": "direct", "query": "RAG ingest 返回 chunks:0 一定是失败吗？", "expected": ["不一定", "去重", "内容未变"]},
    {"id": "rag-2", "category": "direct", "query": "RAG 和 memory 有什么关系？", "expected": ["两套", "独立", "不同"]},
    # 追问式（需要改写才能召回）
    {
        "id": "followup-1",
        "category": "followup",
        "query": "那备案期间怎么访问它？",
        "history": [
            {"role": "user", "content": "openclow 部署在 psyidc.com，备案还没通过"},
            {"role": "assistant", "content": "备案期间 80/443 端口会被封，但 22、8000、8501 可以访问。"},
        ],
        "expected": ["103.236.98.200:8000", "IP:8000", "8000"],
    },
    {
        "id": "followup-2",
        "category": "followup",
        "query": "它的前端跑在哪个端口？",
        "history": [
            {"role": "user", "content": "openclow 前端是 Streamlit"},
        ],
        "expected": ["8501"],
    },
    {
        "id": "followup-3",
        "category": "followup",
        "query": "这个端口能直接访问吗？",
        "history": [
            {"role": "user", "content": "openclow 后端 FastAPI 跑在 8000 端口"},
        ],
        "expected": ["可以", "能", "IP:8000", "8000"],
    },
    {
        "id": "followup-4",
        "category": "followup",
        "query": "那它是用 Docker 跑的吗？",
        "history": [
            {"role": "user", "content": "openclow 部署在 103.236.98.200"},
        ],
        "expected": ["systemd", "不是", "不是 Docker"],
    },
    {
        "id": "followup-5",
        "category": "followup",
        "query": "这种情况下我怎么查进度？",
        "history": [
            {"role": "user", "content": "我的域名 psyidc.com 在腾讯云提交备案"},
        ],
        "expected": ["腾讯云备案控制台", "console.cloud.tencent.com/beian", "腾讯云"],
    },
    {
        "id": "followup-6",
        "category": "followup",
        "query": "它的密钥存在哪里？",
        "history": [
            {"role": "user", "content": "openclow 用 X-API-Key 鉴权"},
        ],
        "expected": [".env", "OPENCLAW_API_KEYS"],
    },
    {
        "id": "followup-7",
        "category": "followup",
        "query": "这个服务启动命令是什么？",
        "history": [
            {"role": "user", "content": "服务器上用 systemd 管理 openclow"},
        ],
        "expected": ["cli.py serve", "serve"],
    },
    {
        "id": "followup-8",
        "category": "followup",
        "query": "它为什么返回 0？",
        "history": [
            {"role": "user", "content": "我用 /rag/ingest 重复导入同一份文档"},
        ],
        "expected": ["去重", "内容未变", "重复"],
    },
    {
        "id": "followup-9",
        "category": "followup",
        "query": "那我应该怎么部署？",
        "history": [
            {"role": "user", "content": "备案期间 Caddy 的 80/443 端口用不了"},
        ],
        "expected": ["IP:8000", "IP:8501", "systemd"],
    },
    {
        "id": "followup-10",
        "category": "followup",
        "query": "它在哪里配置？",
        "history": [
            {"role": "user", "content": "openclow 里知识库切分大小可以调"},
        ],
        "expected": ["配置", "chunk_size", "settings"],
    },
    # 口语化/错别字/跨文档（新增）
    {"id": "oral-1", "category": "direct", "query": "openclow 咋跑起来的啊？", "expected": ["systemd", "/opt/openclow", "不是 Docker"]},
    {"id": "oral-2", "category": "direct", "query": "我现在打不开 psyidc.com，是不是备案的关系？", "expected": ["备案", "80", "443", "被封", "IP:8000", "IP:8501"]},
    {"id": "oral-3", "category": "direct", "query": "swagger 上那个锁点不动怎么回事？", "expected": ["Authorize", "ApiKeyAuth", "securitySchemes", "X-API-Key"]},
    {"id": "oral-4", "category": "direct", "query": "代码改完了，怎么让它生效？", "expected": ["SFTP", "systemctl restart", "上传"]},
    {"id": "oral-5", "category": "direct", "query": "备案到哪查了？", "expected": ["腾讯云备案控制台", "console.cloud.tencent.com/beian", "腾讯云"]},
    {
        "id": "oral-6",
        "category": "followup",
        "query": "那现在怎么访问呢？",
        "history": [
            {"role": "user", "content": "备案期间 psyidc.com 的 80/443 被封了"},
        ],
        "expected": ["103.236.98.200:8000", "103.236.98.200:8501", "IP:8000", "IP:8501"],
    },
    {
        "id": "oral-7",
        "category": "followup",
        "query": "它跑在哪？",
        "history": [
            {"role": "user", "content": "openclow 后端用的是 FastAPI"},
        ],
        "expected": ["8000", "103.236.98.200:8000"],
    },
    {
        "id": "oral-8",
        "category": "followup",
        "query": "我怎么带上认证？",
        "history": [
            {"role": "user", "content": "openclow 接口需要 API Key 才能访问"},
        ],
        "expected": ["X-API-Key", "header", "请求头"],
    },
    {
        "id": "oral-9",
        "category": "followup",
        "query": "那个按钮出不来咋办？",
        "history": [
            {"role": "user", "content": "Swagger 页面上没有 Authorize 弹窗"},
        ],
        "expected": ["Authorize", "ApiKeyAuth", "securitySchemes", "openapi"],
    },
    {
        "id": "oral-10",
        "category": "followup",
        "query": "生产上出 500 怎么看日志？",
        "history": [
            {"role": "user", "content": "生产环境访问 /docs 返回 500"},
        ],
        "expected": ["journalctl", "openclaw-api.service", "日志"],
    },
]


def _match(answer: str, expected: list[str]) -> bool:
    answer_lower = answer.lower()
    return any(keyword.lower() in answer_lower for keyword in expected)


def _has_rewritten(query: str, history: list[dict[str, str]]) -> bool:
    from app.config import settings
    return any(word in query for word in settings.rewrite_trigger_words)


def main() -> None:
    client = OpenClowClient()
    results: list[dict[str, Any]] = []
    scores = {"direct": {"correct": 0, "total": 0}, "followup": {"correct": 0, "total": 0}}

    for item in EVAL_QA_SET:
        query = item["query"]
        history = item.get("history", [])

        if history:
            # 有历史说明是追问，使用改写后的 query 做检索
            rewritten = rewrite_query(query, history, client=client)
            search_results = client.search(rewritten, top_k=5, rerank=False)
        else:
            search_results = client.search(query, top_k=5, rerank=False)

        context = "\n\n".join(r.get("text", "") for r in search_results)
        prompt = (
            "你是 openclow 项目的运维排障助手。请基于下面提供的参考信息回答用户问题。\n"
            "规则：\n"
            "1. 优先使用参考信息中的内容，回答要准确\n"
            "2. 参考信息无答案时，明确告知用户“我没有找到相关记录”，不要编造\n"
            "3. 引用时标注来源\n"
            "4. 回答简洁、结构化\n\n"
            f"用户问题：{query}\n\n参考信息：\n{context}\n\n请回答："
        )
        answer_text = client.chat_raw(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=600,
        )

        ok = _match(answer_text, item["expected"])
        category = item["category"]
        scores[category]["total"] += 1
        if ok:
            scores[category]["correct"] += 1

        results.append({
            "id": item["id"],
            "query": query,
            "category": category,
            "expected": item["expected"],
            "answer": answer_text,
            "correct": ok,
            "rewritten": rewritten if history else query,
        })
        print(f"[{item['id']}] {'✓' if ok else '✗'} {query[:40]}...")
        time.sleep(0.5)

    direct_acc = scores["direct"]["correct"] / max(scores["direct"]["total"], 1)
    followup_acc = scores["followup"]["correct"] / max(scores["followup"]["total"], 1)
    total_acc = (scores["direct"]["correct"] + scores["followup"]["correct"]) / len(EVAL_QA_SET)

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "direct": {"correct": scores["direct"]["correct"], "total": scores["direct"]["total"], "accuracy": round(direct_acc, 2)},
        "followup": {"correct": scores["followup"]["correct"], "total": scores["followup"]["total"], "accuracy": round(followup_acc, 2)},
        "total": {"correct": scores["direct"]["correct"] + scores["followup"]["correct"], "total": len(EVAL_QA_SET), "accuracy": round(total_acc, 2)},
        "details": results,
    }

    out_path = Path(__file__).resolve().parent / "results.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n直问类准确率：{direct_acc:.0%} ({scores['direct']['correct']}/{scores['direct']['total']})")
    print(f"追问类准确率：{followup_acc:.0%} ({scores['followup']['correct']}/{scores['followup']['total']})")
    print(f"整体准确率：{total_acc:.0%}")
    print(f"详细结果已写入：{out_path}")


if __name__ == "__main__":
    main()
