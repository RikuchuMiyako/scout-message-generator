"""PDF からのテキスト抽出ユーティリティ。"""

from __future__ import annotations

import io


def extract_text_from_pdf(data: bytes) -> str:
    """PDF のバイト列からプレーンテキストを抽出して返す。

    求人票・求職者情報の PDF を読み取る用途。pypdf を遅延 import することで、
    PDF を使わない場合は依存を要求しない。
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - 依存未導入時の案内
        raise RuntimeError(
            "PDF を読み取るには pypdf が必要です。`pip install pypdf` を実行してください。"
        ) from exc

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()
