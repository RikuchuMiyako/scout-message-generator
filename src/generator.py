"""Claude API を用いたスカウト文生成。

プロンプトキャッシュ:
  system を2ブロック（共通プロンプト / 企業プロファイル）に分割し、それぞれに
  cache_control を付与する。これにより
    - 同一企業の別求職者 → 共通プロンプト + 企業プロファイルがキャッシュヒット
    - 企業を切り替え       → 共通プロンプトはヒット、プロファイル以降のみ再作成
  となる。揮発的な入力（求人票・求職者情報・検索軸）は messages 側に置く。

注: Opus のキャッシュ最小プレフィックスは約 4096 トークン。共通プロンプト単体が
これに満たない場合、先頭ブロックのキャッシュは黙って無効化される（エラーにはならない）。
2つ目のブロック（共通 + プロファイルの合算）は通常この閾値を超えるためヒットする。
"""

from __future__ import annotations

from typing import Iterator

import anthropic

from .models import CompanyProfile, ScoutInputs
from .prompt import SYSTEM_PROMPT, build_company_context, build_user_message

MODEL = "claude-opus-4-8"


class ScoutGenerator:
    """スカウト文を生成するジェネレーター。

    1インスタンスを使い回すことで HTTP 接続とプロンプトキャッシュを活用する。
    """

    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL):
        # client 未指定時は ANTHROPIC_API_KEY 等を環境から解決
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.last_usage = None  # 直近レスポンスの usage（キャッシュ確認用）

    def _system_blocks(self, profile: CompanyProfile) -> list[dict]:
        return [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": build_company_context(profile),
                "cache_control": {"type": "ephemeral"},
            },
        ]

    def stream(self, inputs: ScoutInputs, profile: CompanyProfile) -> Iterator[str]:
        """テキストデルタを逐次 yield する。完了後 self.last_usage を更新。"""
        system = self._system_blocks(profile)
        user_message = build_user_message(inputs)

        with self.client.messages.stream(
            model=self.model,
            max_tokens=16000,                 # adaptive thinking 分の余裕を含める
            system=system,
            thinking={"type": "adaptive"},    # 文章のニュアンス調整に有効
            output_config={"effort": "high"},
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                yield text
            self.last_usage = stream.get_final_message().usage

    def generate(self, inputs: ScoutInputs, profile: CompanyProfile) -> str:
        """ストリームを消費し、生成された本文を一括で返す。"""
        return "".join(self.stream(inputs, profile))
