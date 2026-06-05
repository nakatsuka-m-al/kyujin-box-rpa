# 採用メディア5サイト 設計書

## 概要

人材紹介会社向け集客を目的とした、転職・求人系メディアサイトを5つ構築する。
自社の求人データ（CSV）を起点に、AIで自動的に求人票を生成・掲載する。
SEO記事も自動生成し、極力手動作業をゼロに近づける。

## ターゲット

20代・30代の転職検討層

## インフラ（既存リソース流用）

| サービス | 用途 | 費用 |
|---|---|---|
| GitHub | コード管理（モノレポ） | 無料 |
| Vercel | 5サイト + 管理画面のホスティング | 無料枠 |
| Supabase | DB（既存1プロジェクト流用） | 無料 |
| Render | バックエンド処理（AI呼び出し等） | 無料枠 |
| Claude API | CSV解析・記事自動生成 | 従量課金のみ |

月の固定費: ほぼゼロ

## リポジトリ構成（モノレポ）

```
/
├── apps/
│   ├── admin/            # 管理画面（CSV投入・記事管理）
│   ├── jobs-main/        # 求人掲載サイト（総合）
│   ├── jobs-region/      # 地域特化求人サイト
│   ├── media-career/     # 転職コラムSEOメディア
│   ├── salary-data/      # 職種・年収データサイト
│   └── agent-compare/    # 転職エージェント比較サイト
└── packages/
    ├── ui/               # 共通UIコンポーネント
    ├── db/               # Supabase クライアント
    └── ai/               # Claude API共通ラッパー
```

## サブドメイン構成

- jobs.company.co.jp
- local.company.co.jp
- media.company.co.jp
- salary.company.co.jp
- agents.company.co.jp
- admin.company.co.jp（管理画面）

## 5サイトの詳細

### 1. 求人総合サイト（jobs-main）
- 自社求人を全件掲載
- 求人ごとに外部応募URLへ誘導（応募管理機能なし）
- カテゴリ・地域・職種で絞り込み検索

### 2. 地域特化求人サイト（jobs-region）
- jobs-mainと同じDBの求人を地域別にフィルタして表示
- 追加の求人データ投入作業ゼロ
- 「大阪の求人」「東京の求人」等のロングテールSEOを狙う

### 3. 転職コラムSEOメディア（media-career）
- Claude APIがキーワードから記事を自動生成・自動投稿
- cron（GitHub Actions or Render）で週次実行
- 記事末に求人サイトへの送客CTA

### 4. 職種・年収データサイト（salary-data）
- 「営業職の平均年収」等のデータページ
- 公開データ（厚労省等）をクロール・整形してAIで記事化
- 定期更新cron

### 5. 転職エージェント比較サイト（agent-compare）
- 主要エージェントの特徴・比較コンテンツ
- 初期設定のみ、更新ほぼ不要
- 自社エージェントへの送客導線

## CSV → 求人票 自動化フロー

1. 管理画面でCSVをドラッグ&ドロップ
2. Claude APIがカラムを自動判定（職種・給与・勤務地・応募URL等）
3. プレビュー画面で確認
4. 「一括投稿」ボタン1つで全サイトに反映

CSVの必須カラム（AIが柔軟に解釈するため厳密なフォーマット不要）:
- 職種名（またはそれに相当するカラム）
- 給与情報
- 勤務地
- 応募URL ← 必須

## DB設計（Supabase 共通）

### jobs テーブル
```sql
id, site_id, title, description, salary, location,
employment_type, apply_url, published_at, created_at
```

### articles テーブル
```sql
id, site_id, title, content, slug, published_at, created_at
```

`site_id` で各サイトのデータを分離。RLSで各サイトは自分のデータのみアクセス可。

## デザイン方針

- Design Read: 求人メディア for 20-30代転職検討層、クリーンでモダン、信頼感ありつつ堅すぎない
- フォント: Geist
- カラー: ネイビー系ベース + アクセント1色
- VARIANCE: 6 / MOTION: 5 / DENSITY: 5
- 各サイトは同じデザインシステムを使いつつ、アクセントカラーで差別化

## スタック

- Framework: Next.js 15（App Router）
- Styling: Tailwind v4
- Animation: Motion（motion/react）
- Icons: @phosphor-icons/react
- DB: Supabase
- AI: Claude API（claude-sonnet-4-6）
- Package manager: pnpm（モノレポ）
