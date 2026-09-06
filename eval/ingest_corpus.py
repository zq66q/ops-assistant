"""把 data/corpus 与 data/runbooks 下的 markdown 语料灌入 openclow 知识库。"""
from __future__ import annotations

import glob
from pathlib import Path

from app.openclow_client import OpenClowClient


def main() -> None:
    client = OpenClowClient()
    base = Path(__file__).resolve().parent.parent / "data"
    # 描述类语料 + 排障手册 runbook
    dirs = [base / "corpus", base / "runbooks"]

    total_files = 0
    for d in dirs:
        files = sorted(glob.glob(str(d / "*.md")))
        if not files:
            print(f"未找到语料文件：{d}")
            continue
        for file_path in files:
            text = Path(file_path).read_text(encoding="utf-8")
            source = Path(file_path).stem
            result = client.ingest_text(
                text,
                source=f"{d.name}/{source}",
                metadata={"category": "ops", "origin": "openclow-project", "kind": d.name},
            )
            print(f"{d.name}/{source}: chunks={result.get('chunks')}, tokens={result.get('tokens')}")
            total_files += 1

    print(f"完成，共灌入 {total_files} 个文档。")


if __name__ == "__main__":
    main()
