"""把 data/corpus/ 下的 markdown 语料灌入 openclow 知识库。"""
from __future__ import annotations

import glob
from pathlib import Path

from app.openclow_client import OpenClowClient


def main() -> None:
    client = OpenClowClient()
    corpus_dir = Path(__file__).resolve().parent.parent / "data" / "corpus"

    files = sorted(glob.glob(str(corpus_dir / "*.md")))
    if not files:
        print(f"未找到语料文件：{corpus_dir}")
        return

    for file_path in files:
        text = Path(file_path).read_text(encoding="utf-8")
        source = Path(file_path).stem
        result = client.ingest_text(
            text,
            source=source,
            metadata={"category": "ops", "origin": "openclow-project"},
        )
        print(f"{source}: chunks={result.get('chunks')}, tokens={result.get('tokens')}")


if __name__ == "__main__":
    main()
