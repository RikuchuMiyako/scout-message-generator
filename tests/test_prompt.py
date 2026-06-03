"""プロンプト組み立てとモデル検証のテスト（API 呼び出しなし）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import MID_CAREER, NEW_GRAD, CompanyProfile, ScoutInputs
from src.prompt import build_company_context, build_user_message


def _profile() -> CompanyProfile:
    return CompanyProfile(
        company_name="テスト株式会社",
        industry="SaaS",
        culture="フラットな組織",
        recruiter_name="山田",
        recruiter_personality="気さくで面倒見が良い",
        tone="丁寧だがフランク",
        selling_points=["裁量が大きい", "リモート可"],
        ng_expressions=["過度な煽り"],
    )


def _inputs() -> ScoutInputs:
    return ScoutInputs(
        target_chars=400,
        recruit_type=MID_CAREER,
        job_posting="バックエンドエンジニア募集。Python/Go。",
        candidate_info="現職でPython開発5年。マネジメント志向。",
        age_range="30〜34歳",
        experience_jobs="サーバーサイドエンジニア",
        residence="東京都",
    )


def test_company_context_includes_key_fields():
    ctx = build_company_context(_profile())
    assert "テスト株式会社" in ctx
    assert "山田" in ctx
    assert "気さくで面倒見が良い" in ctx
    assert "裁量が大きい" in ctx
    assert "過度な煽り" in ctx


def test_user_message_includes_inputs():
    msg = build_user_message(_inputs())
    assert "中途" in msg
    assert "400" in msg
    assert "Python/Go" in msg
    assert "マネジメント志向" in msg
    assert "30〜34歳" in msg


def test_validate_ok():
    assert _inputs().validate() == []


def test_validate_catches_bad_char_count():
    inp = _inputs()
    inp.target_chars = 350  # 100単位でない
    errors = inp.validate()
    assert any("100文字単位" in e for e in errors)


def test_validate_catches_empty_fields():
    inp = ScoutInputs(
        target_chars=400, recruit_type=NEW_GRAD, job_posting="", candidate_info=""
    )
    errors = inp.validate()
    assert any("求人票" in e for e in errors)
    assert any("求職者情報" in e for e in errors)


def test_profile_from_dict_ignores_unknown_keys():
    p = CompanyProfile.from_dict(
        {"company_name": "A社", "unknown_field": "x", "tone": "丁寧"}
    )
    assert p.company_name == "A社"
    assert p.tone == "丁寧"
