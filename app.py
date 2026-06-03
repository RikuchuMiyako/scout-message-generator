"""スカウトメール自動生成ツール（Streamlit UI）。

求人票・求職者情報・検索軸を入力すると、企業風土と採用担当者のパーソナリティを
反映したスカウト文を Claude が生成する。企業プロファイルは一度作成すれば
同一企業の複数スカウトで再利用できる（プロンプトキャッシュ対応）。
"""

from __future__ import annotations

import hmac
import os

import anthropic
import streamlit as st

from src.generator import ScoutGenerator
from src.models import MID_CAREER, NEW_GRAD, CompanyProfile, ScoutInputs
from src.pdf_utils import extract_text_from_pdf
from src.profiles import list_profiles, load_profile, save_profile

st.set_page_config(page_title="スカウトメール生成ツール", page_icon="✉️", layout="wide")


# ---------------------------------------------------------------------------
# 簡易ログイン（パスワードゲート）
# ---------------------------------------------------------------------------
def _app_password() -> str:
    """st.secrets から共有パスワードを取得（未設定なら空文字）。"""
    try:
        return st.secrets.get("APP_PASSWORD", "")  # type: ignore[attr-defined]
    except Exception:
        return ""


def check_password() -> bool:
    """共有パスワードと照合する簡易ゲート。

    APP_PASSWORD が未設定の場合は認証なしで通す（ローカル開発向け）。
    単一の共有パスワードによる軽量な閲覧制限であり、ユーザー個別管理・監査ログ・
    多要素認証はできない。社外秘データの本番運用では IAP/VPN 等の利用を推奨。
    """
    correct = _app_password()
    if not correct:
        return True  # パスワード未設定 → ゲート無効
    if st.session_state.get("authenticated"):
        return True

    def _verify() -> None:
        entered = st.session_state.get("pw", "")
        if hmac.compare_digest(entered, correct):
            st.session_state["authenticated"] = True
            del st.session_state["pw"]  # 平文を残さない
        else:
            st.session_state["authenticated"] = False

    st.text_input("パスワード", type="password", key="pw", on_change=_verify)
    if st.session_state.get("authenticated") is False:
        st.error("パスワードが違います。")
    return False


if not check_password():
    st.stop()  # 認証が通るまで以降のUIを描画しない


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------
def _resolve_api_key() -> str | None:
    """環境変数 → Streamlit secrets の順に API キーを解決。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            key = st.secrets.get("ANTHROPIC_API_KEY")  # type: ignore[attr-defined]
        except Exception:
            key = None
    return key


def _text_or_pdf_input(label: str, key: str) -> str:
    """テキスト貼り付け or PDF アップロードのいずれかでテキストを取得する。"""
    tab_paste, tab_pdf = st.tabs(["コピペ", "PDF読み取り"])
    with tab_paste:
        pasted = st.text_area(label, key=f"{key}_paste", height=220,
                              label_visibility="collapsed")
    with tab_pdf:
        uploaded = st.file_uploader(f"{label}（PDF）", type=["pdf"], key=f"{key}_pdf")
        extracted = ""
        if uploaded is not None:
            try:
                extracted = extract_text_from_pdf(uploaded.getvalue())
                st.success(f"PDF から {len(extracted)} 文字を抽出しました。")
                st.text_area("抽出結果（編集可）", value=extracted,
                             key=f"{key}_pdf_text", height=180)
                extracted = st.session_state.get(f"{key}_pdf_text", extracted)
            except Exception as exc:  # noqa: BLE001
                st.error(f"PDF の読み取りに失敗しました: {exc}")
    # PDF 側に内容があればそちらを優先
    return (extracted or pasted or "").strip()


def _profile_from_form(prefix: str, base: CompanyProfile | None) -> CompanyProfile:
    base = base or CompanyProfile(company_name="")
    company_name = st.text_input("企業名", value=base.company_name, key=f"{prefix}_name")
    industry = st.text_input("業界・事業内容", value=base.industry, key=f"{prefix}_ind")
    culture = st.text_area(
        "企業風土の要約（コーポレートサイト・採用ピッチ資料などから）",
        value=base.culture, key=f"{prefix}_cul", height=120,
    )
    col1, col2 = st.columns(2)
    with col1:
        recruiter_name = st.text_input("採用担当者名", value=base.recruiter_name,
                                       key=f"{prefix}_rn")
    with col2:
        tone = st.text_input("文体・トーンの指針", value=base.tone, key=f"{prefix}_tone",
                             placeholder="例: 丁寧で誠実、ほどよくフランク")
    recruiter_personality = st.text_area(
        "担当者の性格・語り口（LINE WORKS トーク履歴などから）",
        value=base.recruiter_personality, key=f"{prefix}_rp", height=100,
    )
    selling = st.text_area("訴求ポイント（1行に1つ）",
                           value="\n".join(base.selling_points), key=f"{prefix}_sp",
                           height=80)
    ng = st.text_area("避けたい表現・NG事項（1行に1つ）",
                      value="\n".join(base.ng_expressions), key=f"{prefix}_ng", height=80)
    notes = st.text_area("補足", value=base.notes, key=f"{prefix}_notes", height=60)

    return CompanyProfile(
        company_name=company_name.strip(),
        industry=industry.strip(),
        culture=culture.strip(),
        recruiter_name=recruiter_name.strip(),
        recruiter_personality=recruiter_personality.strip(),
        tone=tone.strip(),
        selling_points=[s.strip() for s in selling.splitlines() if s.strip()],
        ng_expressions=[s.strip() for s in ng.splitlines() if s.strip()],
        sources=base.sources,
        notes=notes.strip(),
    )


# ---------------------------------------------------------------------------
# サイドバー: API キー & 企業プロファイル管理
# ---------------------------------------------------------------------------
st.sidebar.header("⚙️ 設定")

api_key = _resolve_api_key()
if not api_key:
    api_key = st.sidebar.text_input("Anthropic API キー", type="password",
                                    help="環境変数 ANTHROPIC_API_KEY でも設定できます。")

st.sidebar.divider()
st.sidebar.header("🏢 企業プロファイル")

existing = list_profiles()
options = ["＋ 新規作成"] + existing
selected = st.sidebar.selectbox("プロファイルを選択", options)

if selected == "＋ 新規作成":
    current_profile = None
else:
    current_profile = load_profile(selected)

with st.sidebar.expander("プロファイルを編集 / 作成", expanded=(selected == "＋ 新規作成")):
    edited_profile = _profile_from_form("prof", current_profile)
    if st.button("💾 プロファイルを保存", use_container_width=True):
        if not edited_profile.company_name:
            st.error("企業名を入力してください。")
        else:
            path = save_profile(edited_profile)
            st.success(f"保存しました: {path.name}")
            st.rerun()

# 生成に使うプロファイル（選択 or 編集中）
active_profile = edited_profile if edited_profile.company_name else current_profile


# ---------------------------------------------------------------------------
# メイン: スカウト生成
# ---------------------------------------------------------------------------
st.title("✉️ スカウトメール生成ツール")
st.caption("求人票・求職者情報・検索軸から、企業風土と担当者の人柄を反映した"
           "スカウト文を生成します。")

col_left, col_right = st.columns(2)
with col_left:
    recruit_type = st.radio("区分", [NEW_GRAD, MID_CAREER], horizontal=True)
with col_right:
    target_chars = st.number_input("目標文字数（100文字単位）", min_value=100,
                                   max_value=2000, value=400, step=100)

st.subheader("🔎 検索軸")
ax1, ax2, ax3 = st.columns(3)
with ax1:
    age_range = st.text_input("年齢帯", placeholder="例: 25〜29歳")
with ax2:
    experience_jobs = st.text_input("経験職種", placeholder="例: 法人営業")
with ax3:
    residence = st.text_input("居住地", placeholder="例: 東京都")

st.subheader("📄 求人票")
job_posting = _text_or_pdf_input("求人票", "job")

st.subheader("👤 求職者情報")
candidate_info = _text_or_pdf_input("求職者情報", "candidate")

st.divider()

if st.button("🚀 スカウト文を生成", type="primary", use_container_width=True):
    inputs = ScoutInputs(
        target_chars=int(target_chars),
        recruit_type=recruit_type,
        job_posting=job_posting,
        candidate_info=candidate_info,
        age_range=age_range,
        experience_jobs=experience_jobs,
        residence=residence,
    )

    errors = inputs.validate()
    if not api_key:
        errors.append("Anthropic API キーを設定してください。")
    if active_profile is None or not active_profile.company_name:
        errors.append("企業プロファイルを選択または作成してください。")

    if errors:
        for e in errors:
            st.error(e)
    else:
        try:
            generator = ScoutGenerator(client=anthropic.Anthropic(api_key=api_key))
            st.subheader("📝 生成結果")
            with st.spinner("生成中…"):
                result = st.write_stream(generator.stream(inputs, active_profile))

            st.session_state["last_result"] = result

            usage = generator.last_usage
            if usage is not None:
                cached = getattr(usage, "cache_read_input_tokens", 0) or 0
                created = getattr(usage, "cache_creation_input_tokens", 0) or 0
                st.caption(
                    f"トークン使用量 — 入力: {usage.input_tokens} / 出力: "
                    f"{usage.output_tokens} / キャッシュ読込: {cached} / "
                    f"キャッシュ作成: {created}"
                )
        except anthropic.AuthenticationError:
            st.error("API キーが無効です。設定を確認してください。")
        except anthropic.APIError as exc:
            st.error(f"API エラー: {exc}")

if st.session_state.get("last_result"):
    st.download_button(
        "⬇️ テキストとして保存",
        data=st.session_state["last_result"],
        file_name="scout_message.txt",
        mime="text/plain",
    )
