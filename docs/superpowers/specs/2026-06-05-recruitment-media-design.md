# 採用メディア 設計書（情報系3サイト）

## 概要

人材紹介会社向け集客を目的とした、転職・求人系SEOメディアを3サイト構築する。
Claude APIで記事を自動生成・自動投稿し、手動作業をほぼゼロにする。
求人サイトは別フェーズで追加予定。

## ターゲット

20代・30代の転職検討層

## 3サイトの構成

| サイト名 | テーマ | SEO戦略 |
|---|---|---|
| **career-stories** | 転職体験談メディア | 「〇〇業界 転職 体験談」系。共感・SNS流入も狙う |
| **salary-data** | 年収・職種データ | 「営業 平均年収」系。検索ボリューム大、離脱率低い |
| **career-tips** | 転職ノウハウ | 「職務経歴書 書き方」「面接 質問」系。ロングテールSEOに強い |

## インフラ（既存リソース流用）

| サービス | 用途 | 費用 |
|---|---|---|
| GitHub | コード管理（モノレポ） | 無料 |
| Vercel | 3サイト + 管理画面のホスティング | 無料枠 |
| Supabase | DB（既存1プロジェクト流用） | 無料 |
| Claude API | 記事自動生成 | 従量課金のみ |

**月の固定費: ほぼゼロ**

## サブドメイン構成

- stories.company.co.jp
- salary.company.co.jp
- tips.company.co.jp
- admin.company.co.jp（管理画面）

## リポジトリ構成（モノレポ）

```
/
├── apps/
│   ├── admin/             # 管理画面（記事管理・生成ステータス確認）
│   ├── career-stories/    # 転職体験談メディア
│   ├── salary-data/       # 年収・職種データ
│   └── career-tips/       # 転職ノウハウ
└── packages/
    ├── ui/                # 共通UIコンポーネント
    ├── db/                # Supabaseクライアント・型定義
    └── ai/                # Claude API記事生成ラッパー
```

## DB設計（Supabase 共通1プロジェクト）

### articles テーブル
```sql
id, site_id, title, content, excerpt, slug,
is_published, published_at, created_at, updated_at
```

`site_id` で各サイトのデータを分離。

## 記事自動生成フロー

1. GitHub Actions cron（毎週月曜朝9時）が起動
2. 管理画面のAPI（`/api/generate-articles`）を呼び出す
3. サイトごとのキーワードリストからClaude APIで記事生成
4. Supabaseに自動投稿
5. 各サイトに即時反映（Next.js ISR）

## デザイン方針

- Design Read: SEOメディア for 20-30代転職検討層、読みやすく信頼感のある情報サイト
- フォント: Geist
- サイトごとにアクセントカラーを変えて差別化:
  - career-stories: ブルー系
  - salary-data: エメラルド系
  - career-tips: バイオレット系
- VARIANCE: 5 / MOTION: 3 / DENSITY: 4（記事メディアらしいシンプルさ）

## スタック

- Framework: Next.js 15（App Router + ISR）
- Styling: Tailwind v4
- Icons: @phosphor-icons/react
- DB: Supabase
- AI: Claude API（claude-sonnet-4-6）
- Package manager: pnpm（モノレポ）

## 将来の拡張

- 求人サイト（jobs-main, jobs-region）は別フェーズで追加
- 記事からの求人サイトへの送客導線はプレースホルダーとして実装しておく
