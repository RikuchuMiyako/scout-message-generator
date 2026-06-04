"""採用資料・サイト本文・トーク履歴から企業プロファイルを自動生成する。

コーポレートサイト / リクルートサイト（エンゲージ）の本文、採用ピッチ資料、
LINE WORKS トーク履歴などの素材を Claude に渡し、CompanyProfile の各項目
（企業風土・担当者の性格・文体・訴求点など）を構造化出力で自動抽出する。

Web 取得は行わず、素材は呼び出し側（UI）が貼付・アップロードで用意する前提。
"""

from __future__ import annotations

import json

import anthropic

from .models import CompanyProfile

MODEL = "claude-opus-4-8"

# 構造化出力スキーマ（CompanyProfile の自動入力対象フィールド）
PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "industry": {"type": "string", "description": "業界・事業内容の簡潔な要約"},
        "culture": {"type": "string", "description": "企業風土の要約"},
        "recruiter_name": {"type": "string", "description": "採用担当者名（不明なら空文字）"},
        "recruiter_personality": {
            "type": "string",
            "description": "担当者の性格・語り口。主に LINE WORKS トークの文体から推定",
        },
        "tone": {"type": "string", "description": "スカウト文に適した文体・トーンの指針"},
        "selling_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "求職者への訴求ポイント（3〜6個程度）",
        },
        "ng_expressions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "風土・トーンに照らして避けるべき表現（なければ空配列）",
        },
        "notes": {"type": "string", "description": "スカウト作成に役立つ補足（なければ空文字）"},
    },
    "required": [
        "industry",
        "culture",
        "recruiter_name",
        "recruiter_personality",
        "tone",
        "selling_points",
        "ng_expressions",
        "notes",
    ],
    "additionalProperties": False,
}

EXTRACT_SYSTEM = """\
あなたは採用ブランディングのアナリストです。与えられた素材（企業サイト本文、
採用ピッチ資料、LINE WORKS トーク履歴など）を読み解き、ダイレクトリクルーティングの
スカウト文作成に使う「企業プロファイル」を構造化して抽出します。

# 抽出の方針
- 企業風土(culture)・業界(industry)・訴求ポイント(selling_points)は、企業サイトや
  採用ピッチ資料の記述から要約する。
- 担当者の性格・語り口(recruiter_personality)と文体指針(tone)は、主に LINE WORKS の
  トーク履歴に表れる言葉づかい・温度感・一人称・絵文字の使い方などから推定する。
  トークが無い場合は、企業の文化や採用メッセージのトーンから無理のない範囲で推定する。
- 避けたい表現(ng_expressions)は、企業の価値観・トーンに照らして不適切になりそうな
  表現を挙げる。判断材料が乏しければ空配列にする。

# 厳守事項
- 素材に書かれていない事実（数値・制度・固有名詞など）を創作しないこと。
- 不明な項目は、文字列なら空文字、配列なら空配列にする。推測で埋めない。
- 出力はスキーマに従った JSON のみ。"""


def _section(title: str, body: str) -> str:
    body = (body or "").strip()
    if not body:
        return ""
    return f"\n## {title}\n{body}\n"


def build_extraction_message(
    corporate: str = "",
    recruit: str = "",
    pitch: str = "",
    chat: str = "",
) -> str:
    sections = "".join(
        [
            _section("コーポレートサイト本文", corporate),
            _section("リクルートサイト（エンゲージ）本文", recruit),
            _section("採用ピッチ資料・その他採用資料", pitch),
            _section("LINE WORKS トーク履歴", chat),
        ]
    )
    if not sections:
        sections = "\n（素材が提供されていません）\n"
    return (
        "以下の素材から企業プロファイルを抽出してください。\n"
        "# 素材\n" + sections
    )


def generate_profile_from_sources(
    company_name: str,
    corporate: str = "",
    recruit: str = "",
    pitch: str = "",
    chat: str = "",
    sources: dict[str, str] | None = None,
    client: anthropic.Anthropic | None = None,
    model: str = MODEL,
) -> CompanyProfile:
    """素材から CompanyProfile を生成して返す。"""
    client = client or anthropic.Anthropic()
    user_message = build_extraction_message(corporate, recruit, pitch, chat)

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=EXTRACT_SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": PROFILE_SCHEMA}},
        messages=[{"role": "user", "content": user_message}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    data = json.loads(text)
    data["company_name"] = company_name
    if sources:
        data["sources"] = sources
    return CompanyProfile.from_dict(data)
