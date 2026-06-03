"""入力項目・企業プロファイルのデータモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field

# 新卒 / 中途 の区分値
NEW_GRAD = "新卒"
MID_CAREER = "中途"
RECRUIT_TYPES = (NEW_GRAD, MID_CAREER)


@dataclass
class ScoutInputs:
    """1通のスカウト文を生成するための入力一式。

    target_chars 以外は求人票・求職者情報・検索軸など、求職者ごとに変わる
    揮発的な入力。プロンプトキャッシュの観点ではユーザーメッセージ側に置く。
    """

    target_chars: int           # 目標文字数（100文字単位）
    recruit_type: str           # NEW_GRAD or MID_CAREER
    job_posting: str            # 求人票（PDF抽出 or コピペ）
    candidate_info: str         # 求職者情報（同上）
    age_range: str = ""         # 検索軸: 年齢帯
    experience_jobs: str = ""   # 検索軸: 経験職種
    residence: str = ""         # 検索軸: 居住地

    def validate(self) -> list[str]:
        """入力の不備をメッセージのリストで返す（空ならOK）。"""
        errors: list[str] = []
        if self.target_chars <= 0 or self.target_chars % 100 != 0:
            errors.append("文字数は100文字単位の正の値で指定してください。")
        if self.recruit_type not in RECRUIT_TYPES:
            errors.append("新卒 / 中途 のいずれかを選択してください。")
        if not self.job_posting.strip():
            errors.append("求人票を入力してください。")
        if not self.candidate_info.strip():
            errors.append("求職者情報を入力してください。")
        return errors


@dataclass
class CompanyProfile:
    """企業風土・採用担当者のパーソナル情報。

    コーポレートサイト / リクルートサイト（エンゲージ） / 採用ピッチ資料 /
    LINE WORKS トーク履歴 などから抽出した要点を一度だけ作成・保存しておき、
    同一企業の複数スカウトで再利用する（プロンプトキャッシュ対象）。
    """

    company_name: str
    industry: str = ""                              # 業界・事業内容
    culture: str = ""                               # 企業風土の要約
    recruiter_name: str = ""                        # 採用担当者名
    recruiter_personality: str = ""                 # 担当者の性格・語り口
    tone: str = ""                                  # 文体の指針（例: 丁寧で熱量高め）
    selling_points: list[str] = field(default_factory=list)   # 訴求ポイント
    ng_expressions: list[str] = field(default_factory=list)   # 避けたい表現
    sources: dict[str, str] = field(default_factory=dict)     # 参照元URL等
    notes: str = ""                                 # その他補足

    @classmethod
    def from_dict(cls, data: dict) -> "CompanyProfile":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})
