"""AI プロファイル生成のプロンプト組み立てとパースのテスト（API 呼び出しなし）。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import CompanyProfile
from src.profile_ai import PROFILE_SCHEMA, build_extraction_message


def test_extraction_message_includes_provided_sources_only():
    msg = build_extraction_message(
        corporate="フラットな組織文化", chat="及川です！よろしくお願いします〜"
    )
    assert "コーポレートサイト本文" in msg
    assert "フラットな組織文化" in msg
    assert "LINE WORKS トーク履歴" in msg
    assert "及川です" in msg
    # 未提供のセクションは含めない
    assert "採用ピッチ資料・その他採用資料" not in msg


def test_extraction_message_handles_no_sources():
    msg = build_extraction_message()
    assert "素材が提供されていません" in msg


def test_schema_required_fields_map_to_profile():
    """スキーマの必須フィールドが CompanyProfile に取り込めることを確認。"""
    fields = set(CompanyProfile.__dataclass_fields__)  # type: ignore[attr-defined]
    for key in PROFILE_SCHEMA["required"]:
        assert key in fields


def test_parse_model_output_into_profile():
    """モデル出力（JSON）を CompanyProfile へ変換できる。"""
    fake_output = json.dumps({
        "industry": "SaaS",
        "culture": "挑戦を歓迎する風土",
        "recruiter_name": "及川",
        "recruiter_personality": "気さくで面倒見が良い",
        "tone": "丁寧だがフランク",
        "selling_points": ["裁量が大きい", "リモート可"],
        "ng_expressions": ["過度な煽り"],
        "notes": "カジュアル面談を推奨",
    })
    data = json.loads(fake_output)
    data["company_name"] = "テスト株式会社"
    profile = CompanyProfile.from_dict(data)
    assert profile.company_name == "テスト株式会社"
    assert profile.recruiter_name == "及川"
    assert profile.selling_points == ["裁量が大きい", "リモート可"]
