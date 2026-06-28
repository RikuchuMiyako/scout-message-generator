# scout-message-generator

ダイレクトリクルーティング向け **スカウトメール生成スキル**（Claude Code / Cowork 用 Skill）。

求人票・求職者情報・検索軸を渡すと、**企業風土と採用担当者のパーソナリティ**を反映した、
その求職者だけに宛てたスカウト文を Claude が生成します。単なるテンプレート文章ではなく、
「なぜあなたに送ったのか」が伝わる文面を目指しています。

> **方式**: 生成は Cowork / Claude Code のセッションを動かしている Claude 自身が行います。
> 外部 API を別途呼ばないため、**従量課金の API コストが発生しません**（既存の Claude
> サブスクリプションの利用枠内で動作）。モデルも Opus 系のまま品質を維持できます。

## 特長

- **Skill 方式**: Cowork / Claude Code でスキルを呼び出すだけ。専用アプリ・API キー不要。
- **企業プロファイル方式**: 企業風土・担当者の性格・文体指針を一度作成・保存すれば
  （`profiles/<企業名>.json`）、同一企業の複数スカウトで再利用できます。
- **素材からのプロファイル作成**: コーポレートサイト/エンゲージ本文、採用ピッチ資料
  （PDF/PPTX）、LINE WORKS トーク履歴を渡すと、Claude が企業風土・担当者の性格・文体・
  訴求点などを抽出して JSON を作成します。
- **新卒 / 中途の書き分け**、**文字数指定**、**検索軸**（年齢帯・経験職種・居住地）対応。

## 使い方（Cowork / Claude Code）

このリポジトリを Cowork / Claude Code で開くと、`scout-message` スキルが利用可能になります。

1. **スカウト作成を依頼する**
   例:「sample_company のスカウト文を書いて。中途エンジニア向け、約400文字。
   求人票と求職者情報はこれ（貼付 or PDF 添付）」
2. Claude が `profiles/<企業名>.json` を読み、執筆ガイドに従って本文を生成します。
3. 出力は**スカウト文の本文のみ**（必要に応じて先頭に「件名: ...」の1行）。

### 企業プロファイルを新しく作る
プロファイルが無い企業は、素材を渡して作成を依頼します。
例:「新しい企業のプロファイルを作って。コーポレートサイト本文（貼付）、採用ピッチ資料
（PDF/PPTX 添付）、LINE WORKS トーク履歴（貼付）はこちら」

- PDF は Claude が直接読みます。PPTX は同梱の `scripts/extract_pptx.py` で抽出します。
- 担当者の性格・語り口・文体は主に LINE WORKS トークの言葉づかいから推定します。
- 素材に無い事実は創作せず、不明な項目は空のままにします。確認後に保存します。

## 構成

```
.claude/skills/scout-message/
  SKILL.md                      スキル本体（実行フロー・原則）
  references/
    writing-guide.md            執筆ガイド（構成・書き分け・NG・プロファイル反映）
    profile-schema.md           企業プロファイルのスキーマと作成ガイド
  scripts/
    extract_pptx.py             PPTX テキスト抽出ヘルパー
profiles/
  sample_company.json           企業プロファイルの例（保存形式）
```

## 企業プロファイルのフォーマット

`profiles/sample_company.json` が例です。1社1ファイルで保存し、同一企業の複数スカウトで
再利用します。各項目の定義と作成方針は
`.claude/skills/scout-message/references/profile-schema.md` を参照してください。

主な情報源:

- コーポレートサイト
- リクルートサイト（エンゲージ掲載）
- 採用ピッチ資料・その他採用資料（PDF/PPTX）
- LINE WORKS トーク履歴

## 補足: PPTX 抽出を使う場合

```bash
pip install python-pptx
python .claude/skills/scout-message/scripts/extract_pptx.py <file.pptx>
```
