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
from src.pdf_utils import extract_document_text, extract_text_from_pdf
from src.profile_ai import generate_profile_from_sources
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


def _load_profile_into_form(p: CompanyProfile) -> None:
    """CompanyProfile の値をフォーム用の session_state キーに流し込む。

    各ウィジェットは key のみで session_state を参照するため、ウィジェット生成前に
    ここで値を設定しておくことで、プロファイル選択・AI生成の結果を反映できる。
    """
    st.session_state["prof_name"] = p.company_name
    st.session_state["prof_ind"] = p.industry
    st.session_state["prof_cul"] = p.culture
    st.session_state["prof_rn"] = p.recruiter_name
    st.session_state["prof_tone"] = p.tone
    st.session_state["prof_rp"] = p.recruiter_personality
    st.session_state["prof_sp"] = "\n".join(p.selling_points)
    st.session_state["prof_ng"] = "\n".join(p.ng_expressions)
    st.session_state["prof_notes"] = p.notes
    st.session_state["prof_sources"] = dict(p.sources)


def _profile_from_session() -> CompanyProfile:
    """フォームの現在値から CompanyProfile を組み立てる。"""
    return CompanyProfile(
        company_name=st.session_state.get("prof_name", "").strip(),
        industry=st.session_state.get("prof_ind", "").strip(),
        culture=st.session_state.get("prof_cul", "").strip(),
        recruiter_name=st.session_state.get("prof_rn", "").strip(),
        tone=st.session_state.get("prof_tone", "").strip(),
        recruiter_personality=st.session_state.get("prof_rp", "").strip(),
        selling_points=[s.strip() for s in st.session_state.get("prof_sp", "").splitlines() if s.strip()],
        ng_expressions=[s.strip() for s in st.session_state.get("prof_ng", "").splitlines() if s.strip()],
        notes=st.session_state.get("prof_notes", "").strip(),
        sources=st.session_state.get("prof_sources", {}),
    )


def _render_profile_form() -> None:
    st.text_input("企業名", key="prof_name")
    st.text_input("業界・事業内容", key="prof_ind")
    st.text_area("企業風土の要約（コーポレートサイト・採用ピッチ資料などから）",
                 key="prof_cul", height=120)
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("採用担当者名", key="prof_rn")
    with col2:
        st.text_input("文体・トーンの指針", key="prof_tone",
                      placeholder="例: 丁寧で誠実、ほどよくフランク")
    st.text_area("担当者の性格・語り口（LINE WORKS トーク履歴などから）",
                 key="prof_rp", height=100)
    st.text_area("訴求ポイント（1行に1つ）", key="prof_sp", height=80)
    st.text_area("避けたい表現・NG事項（1行に1つ）", key="prof_ng", height=80)
    st.text_area("補足", key="prof_notes", height=60)


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

# 起動直後・選択変更時に、選択したプロファイルをフォームへ読み込む（ウィジェット生成前）
if st.session_state.get("loaded_profile_name") != selected:
    st.session_state["loaded_profile_name"] = selected
    if selected == "＋ 新規作成":
        _load_profile_into_form(CompanyProfile(company_name=""))
    else:
        _load_profile_into_form(load_profile(selected) or CompanyProfile(company_name=""))

# AI生成結果の保留読み込み（ボタン押下 → rerun 後にここで反映）
if "pending_profile" in st.session_state:
    _load_profile_into_form(st.session_state.pop("pending_profile"))

# --- 資料からAIで自動生成 ---
with st.sidebar.expander("🤖 資料からAIで自動生成", expanded=False):
    st.caption("コーポレートサイト/エンゲージ本文・採用資料・LINE WORKSトークを"
               "貼付/アップロードすると、AIが各項目を自動入力します。")
    ai_corp = st.text_area("コーポレートサイト本文", key="ai_corp", height=80)
    ai_recruit = st.text_area("リクルートサイト（エンゲージ）本文", key="ai_recruit", height=80)
    pitch_files = st.file_uploader("採用ピッチ資料（PDF/PPTX・複数可）",
                                   type=["pdf", "pptx"], accept_multiple_files=True,
                                   key="ai_pitch_files")
    ai_pitch_paste = st.text_area("（または）資料テキストを貼付", key="ai_pitch_paste",
                                  height=60)
    chat_file = st.file_uploader("LINE WORKS トーク履歴（.txt）", type=["txt"],
                                 key="ai_chat_file")
    ai_chat_paste = st.text_area("（または）トーク履歴を貼付", key="ai_chat_paste",
                                 height=80)

    if st.button("🤖 AIでプロファイル項目を生成", use_container_width=True):
        if not api_key:
            st.error("Anthropic API キーを設定してください。")
        else:
            pitch_text = ai_pitch_paste or ""
            for f in pitch_files or []:
                try:
                    pitch_text += "\n" + extract_document_text(f.name, f.getvalue())
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"{f.name} の読み取りに失敗: {exc}")
            chat_text = ai_chat_paste or ""
            if chat_file is not None:
                chat_text += "\n" + chat_file.getvalue().decode("utf-8", errors="replace")

            if not any([ai_corp.strip(), ai_recruit.strip(),
                        pitch_text.strip(), chat_text.strip()]):
                st.error("少なくとも1つの素材を入力してください。")
            else:
                with st.spinner("AIがプロファイルを生成中…"):
                    try:
                        generated = generate_profile_from_sources(
                            company_name=st.session_state.get("prof_name", "").strip(),
                            corporate=ai_corp,
                            recruit=ai_recruit,
                            pitch=pitch_text,
                            chat=chat_text,
                            sources=st.session_state.get("prof_sources", {}),
                            client=anthropic.Anthropic(api_key=api_key),
                        )
                        st.session_state["pending_profile"] = generated
                        st.session_state["ai_msg"] = (
                            "AIで生成しました。下の編集欄に反映済みです。"
                            "内容を確認・修正して保存してください。"
                        )
                        st.rerun()
                    except anthropic.APIError as exc:
                        st.error(f"API エラー: {exc}")

# --- 編集 / 保存 ---
with st.sidebar.expander("プロファイルを編集 / 作成", expanded=(selected == "＋ 新規作成")):
    msg = st.session_state.pop("ai_msg", None)
    if msg:
        st.success(msg)
    _render_profile_form()
    if st.button("💾 プロファイルを保存", use_container_width=True):
        prof = _profile_from_session()
        if not prof.company_name:
            st.error("企業名を入力してください。")
        else:
            path = save_profile(prof)
            st.success(f"保存しました: {path.name}")
            st.rerun()

# 生成に使うプロファイル（フォームの現在値）
active_profile = _profile_from_session()
if not active_profile.company_name:
    active_profile = None


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
