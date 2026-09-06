"""知识库体检 + 去重：看内容 / 检测重复 / 核对 runbook 是否都入库 / 检索示例。

用法（在 D:\\ops-assistant 下运行，读 .env 连真实平台）：
    python -m eval.check_kb                    # 体检（只读）
    python -m eval.check_kb "Redis OOM"        # 指定示例检索词
    python -m eval.check_kb --dedupe           # 去重：删除「同内容但 source 名重复」的冗余那套
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

from app.openclow_client import OpenClowClient


def _fetch_status(c) -> list[dict]:
    st = httpx.get(c._url("/rag/status"), headers=c.headers, timeout=20).json()
    return st.get("sources", [])


def _delete_source(c, source: str) -> int:
    r = httpx.delete(c._url(f"/rag/source/{source}"), headers=c.headers, timeout=20)
    return r.status_code


def dedupe(c) -> list[str]:
    """检测「同 stem、不同 source 名」的重复，保留 corpus/<stem>（规范命名），删掉裸名那套。"""
    sources = _fetch_status(c)
    groups: dict[str, list[str]] = {}
    for s in sources:
        name = s["source"]
        stem = name.replace("corpus/", "")
        groups.setdefault(stem, []).append(name)
    removed: list[str] = []
    for stem, names in groups.items():
        if len(names) > 1:
            keep = next((n for n in names if n.startswith("corpus/")), names[0])
            for n in names:
                if n != keep:
                    code = _delete_source(c, n)
                    removed.append(n)
                    print(f"  删除 {n}: {code}")
    return removed


def main() -> int:
    c = OpenClowClient()
    print("base =", c.base_url)

    if "--dedupe" in sys.argv:
        print("== 开始去重 ==")
        removed = dedupe(c)
        print("已删除的重复 sources:", removed if removed else "（没有需要删除的重复）")
        # 去重后再看状态
        st = httpx.get(c._url("/rag/status"), headers=c.headers, timeout=20).json()
        print(f"去重后 document_count = {st.get('document_count', 0)}")
        return 0

    # 1) 状态
    sources = _fetch_status(c)
    st = httpx.get(c._url("/rag/status"), headers=c.headers, timeout=20).json()
    print(f"\n== document_count = {st.get('document_count', 0)} ；sources = {len(sources)} ==")
    for s in sorted(sources, key=lambda x: x.get("source", "")):
        print(f"  {s['source']:45s} chunks={s.get('chunks', 0)}")

    # 2) 重复检测（同 stem、不同 source 名）
    groups: dict[str, list[str]] = {}
    for s in sources:
        name = s["source"]
        groups.setdefault(name.replace("corpus/", ""), []).append(name)
    dup = {g: v for g, v in groups.items() if len(v) > 1}
    print("\n重复（同 stem 多份）:", dup if dup else "无")

    # 3) 核对本地 runbook 是否都进了库
    rb_dir = Path(__file__).resolve().parent.parent / "data" / "runbooks"
    local = [f"runbooks/{f.stem}" for f in rb_dir.glob("*.md")]
    in_kb = {n for n in [s["source"] for s in sources] if n.startswith("runbooks/")}
    missing = [n for n in local if n not in in_kb]
    print(f"本地 runbook 文件: {len(local)} 份；库中 runbook source: {len(in_kb)} 个")
    print("未入库的 runbook:", missing if missing else "无")

    # 4) 检索示例
    q = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "Nginx 一直返回 502"
    res = c.search(q, top_k=3, rerank=False)
    print(f"\n== 检索示例 '{q}' 命中 ==")
    for r in res:
        print(f"  [{r.get('score', 0):.4f}] {r.get('metadata', {}).get('source', ''):30s} {r.get('text', '')[:48]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
