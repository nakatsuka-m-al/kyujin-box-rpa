# Phase 4: コンテンツサイト Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** media-career（転職コラムSEO）、salary-data（年収データ）、agent-compare（エージェント比較）の3サイトと、記事自動生成cronを構築する。

**Architecture:** 3サイトはいずれも記事コンテンツをSupabaseから取得して表示するNext.jsアプリ。記事生成はGitHub Actions cronからRender上のAPIを叩いてClaude APIで生成・投稿する。

**Tech Stack:** Next.js 15, Tailwind v4, @recruitment/db, @recruitment/ai, @recruitment/ui, GitHub Actions (cron)

**前提:** Phase 1完了済み。Supabase articlesテーブルが存在する。

---

## File Structure

```
apps/media-career/
├── package.json
├── next.config.ts
├── app/
│   ├── layout.tsx
│   ├── page.tsx              # 記事一覧
│   ├── [slug]/
│   │   └── page.tsx          # 記事詳細
│   └── globals.css

apps/salary-data/
├── package.json
├── next.config.ts
├── app/
│   ├── layout.tsx
│   ├── page.tsx              # 職種一覧
│   ├── [slug]/
│   │   └── page.tsx          # 職種別年収記事
│   └── globals.css

apps/agent-compare/
├── package.json
├── next.config.ts
├── app/
│   ├── layout.tsx
│   ├── page.tsx              # エージェント比較一覧
│   └── globals.css

apps/admin/
└── app/
    └── api/
        └── generate-articles/
            └── route.ts      # 記事生成APIエンドポイント

.github/
└── workflows/
    └── generate-articles.yml # 毎週月曜朝9時に記事生成
```

---

### Task 1: media-career サイト構築

**Files:**
- Create: `apps/media-career/package.json`
- Create: `apps/media-career/next.config.ts`
- Create: `apps/media-career/app/globals.css`
- Create: `apps/media-career/app/layout.tsx`
- Create: `apps/media-career/app/page.tsx`
- Create: `apps/media-career/app/[slug]/page.tsx`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/media-career
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

- [ ] **Step 2: package.jsonを更新**

`apps/media-career/package.json` の `dependencies`:

```json
{
  "dependencies": {
    "@recruitment/db": "workspace:*",
    "@recruitment/ui": "workspace:*",
    "@phosphor-icons/react": "^2.1.0",
    "clsx": "^2.1.0"
  }
}
```

- [ ] **Step 3: next.config.tsを設定**

`apps/media-career/next.config.ts`:

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/ui', '@recruitment/db'],
}

export default nextConfig
```

- [ ] **Step 4: globals.cssを作成**

`apps/media-career/app/globals.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 5: layout.tsxを作成**

`apps/media-career/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'キャリアメディア - 転職・キャリアの情報サイト',
  description: '20代・30代の転職・キャリアアップに役立つ情報を発信しています。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={`${geist.className} bg-white`}>
        <header className="border-b border-gray-200">
          <div className="max-w-3xl mx-auto px-4 h-14 flex items-center">
            <a href="/" className="font-bold text-gray-900">キャリアメディア</a>
          </div>
        </header>
        <main>{children}</main>
        <footer className="border-t border-gray-100 mt-16">
          <div className="max-w-3xl mx-auto px-4 py-8">
            <p className="text-sm text-gray-400">
              &copy; {new Date().getFullYear()} キャリアメディア
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
```

- [ ] **Step 6: 記事一覧ページを作成**

`apps/media-career/app/page.tsx`:

```tsx
import { createPublicClient, getPublishedArticles } from '@recruitment/db'

export default async function MediaTopPage() {
  const client = createPublicClient()
  const articles = await getPublishedArticles(client, 'media-career', { limit: 20 })

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold text-gray-900 tracking-tight mb-8">
        転職・キャリアの記事
      </h1>

      {articles.length === 0 ? (
        <p className="text-gray-400">記事がまだありません</p>
      ) : (
        <div className="space-y-6">
          {articles.map((article) => (
            <a
              key={article.id}
              href={`/${article.slug}`}
              className="block group"
            >
              <article className="border-b border-gray-100 pb-6">
                <h2 className="text-lg font-semibold text-gray-900 group-hover:text-blue-700 transition-colors">
                  {article.title}
                </h2>
                {article.excerpt && (
                  <p className="mt-1.5 text-sm text-gray-500 leading-relaxed line-clamp-2">
                    {article.excerpt}
                  </p>
                )}
                <p className="mt-2 text-xs text-gray-400">
                  {article.published_at
                    ? new Date(article.published_at).toLocaleDateString('ja-JP')
                    : ''}
                </p>
              </article>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 7: 記事詳細ページを作成**

`apps/media-career/app/[slug]/page.tsx`:

```tsx
import { notFound } from 'next/navigation'
import { createPublicClient, getArticleBySlug } from '@recruitment/db'
import type { Metadata } from 'next'

type Props = { params: Promise<{ slug: string }> }

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const client = createPublicClient()
  const article = await getArticleBySlug(client, 'media-career', slug)
  if (!article) return { title: '記事が見つかりません' }
  return {
    title: `${article.title} | キャリアメディア`,
    description: article.excerpt ?? undefined,
  }
}

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params
  const client = createPublicClient()
  const article = await getArticleBySlug(client, 'media-career', slug)
  if (!article) notFound()

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <a href="/" className="text-sm text-blue-700 hover:underline">
        ← 記事一覧に戻る
      </a>

      <article className="mt-8">
        <h1 className="text-3xl font-bold text-gray-900 leading-snug">
          {article.title}
        </h1>
        <p className="mt-2 text-sm text-gray-400">
          {article.published_at
            ? new Date(article.published_at).toLocaleDateString('ja-JP')
            : ''}
        </p>

        <div className="mt-8 prose prose-gray max-w-none">
          {article.content.split('\n\n').map((para, i) => (
            <p key={i} className="mb-4 text-gray-700 leading-relaxed">
              {para}
            </p>
          ))}
        </div>

        <div className="mt-12 p-6 bg-blue-50 rounded-2xl">
          <p className="font-semibold text-blue-900">転職を考えていますか？</p>
          <p className="mt-1 text-sm text-blue-700">
            求人情報をチェックして、次のステップを踏み出しましょう。
          </p>
          <a
            href="https://jobs.company.co.jp"
            className="mt-4 inline-block px-5 py-2.5 bg-blue-700 text-white text-sm font-medium rounded-lg hover:bg-blue-800"
          >
            求人を探す
          </a>
        </div>
      </article>
    </div>
  )
}
```

- [ ] **Step 8: 依存関係インストールと動作確認**

```bash
cd ../.. && pnpm install
cd apps/media-career && pnpm dev
```

Expected: http://localhost:3000 で記事一覧（空）が表示される

- [ ] **Step 9: コミット**

```bash
git add apps/media-career/
git commit -m "feat: media-career - 転職コラムSEOメディア構築"
```

---

### Task 2: salary-data サイト構築

**Files:**
- Create: `apps/salary-data/package.json`
- Create: `apps/salary-data/next.config.ts`
- Create: `apps/salary-data/app/layout.tsx`
- Create: `apps/salary-data/app/globals.css`
- Create: `apps/salary-data/app/page.tsx`
- Create: `apps/salary-data/app/[slug]/page.tsx`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/salary-data
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

- [ ] **Step 2: package.jsonを更新（media-careerと同じ）**

```json
{
  "dependencies": {
    "@recruitment/db": "workspace:*",
    "@recruitment/ui": "workspace:*",
    "@phosphor-icons/react": "^2.1.0",
    "clsx": "^2.1.0"
  }
}
```

- [ ] **Step 3: next.config.tsを設定（media-careerと同じ）**

```typescript
import type { NextConfig } from 'next'
const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/ui', '@recruitment/db'],
}
export default nextConfig
```

- [ ] **Step 4: layout.tsxを作成**

`apps/salary-data/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: '職種別年収データ - 平均年収・給与情報',
  description: '職種別の平均年収・給与データを解説しています。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={`${geist.className} bg-white`}>
        <header className="border-b border-gray-200">
          <div className="max-w-3xl mx-auto px-4 h-14 flex items-center">
            <a href="/" className="font-bold text-gray-900">年収データ</a>
          </div>
        </header>
        <main>{children}</main>
        <footer className="border-t border-gray-100 mt-16">
          <div className="max-w-3xl mx-auto px-4 py-8">
            <p className="text-sm text-gray-400">
              &copy; {new Date().getFullYear()} 年収データ
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
```

- [ ] **Step 5: 記事一覧・詳細ページを作成（media-careerと同じ構造、site_idのみ異なる）**

`apps/salary-data/app/page.tsx`:

```tsx
import { createPublicClient, getPublishedArticles } from '@recruitment/db'

export default async function SalaryTopPage() {
  const client = createPublicClient()
  const articles = await getPublishedArticles(client, 'salary-data', { limit: 20 })

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold text-gray-900 tracking-tight mb-8">
        職種別 年収・給与データ
      </h1>
      {articles.length === 0 ? (
        <p className="text-gray-400">記事がまだありません</p>
      ) : (
        <div className="space-y-6">
          {articles.map((article) => (
            <a key={article.id} href={`/${article.slug}`} className="block group">
              <article className="border-b border-gray-100 pb-6">
                <h2 className="text-lg font-semibold text-gray-900 group-hover:text-emerald-700 transition-colors">
                  {article.title}
                </h2>
                {article.excerpt && (
                  <p className="mt-1.5 text-sm text-gray-500 line-clamp-2">{article.excerpt}</p>
                )}
              </article>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
```

`apps/salary-data/app/[slug]/page.tsx`:

```tsx
import { notFound } from 'next/navigation'
import { createPublicClient, getArticleBySlug } from '@recruitment/db'
import type { Metadata } from 'next'

type Props = { params: Promise<{ slug: string }> }

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const client = createPublicClient()
  const article = await getArticleBySlug(client, 'salary-data', slug)
  if (!article) return { title: '記事が見つかりません' }
  return {
    title: `${article.title} | 年収データ`,
    description: article.excerpt ?? undefined,
  }
}

export default async function SalaryArticlePage({ params }: Props) {
  const { slug } = await params
  const client = createPublicClient()
  const article = await getArticleBySlug(client, 'salary-data', slug)
  if (!article) notFound()

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <a href="/" className="text-sm text-emerald-700 hover:underline">← 記事一覧に戻る</a>
      <article className="mt-8">
        <h1 className="text-3xl font-bold text-gray-900">{article.title}</h1>
        <div className="mt-8">
          {article.content.split('\n\n').map((para, i) => (
            <p key={i} className="mb-4 text-gray-700 leading-relaxed">{para}</p>
          ))}
        </div>
        <div className="mt-12 p-6 bg-emerald-50 rounded-2xl">
          <p className="font-semibold text-emerald-900">年収アップを目指しませんか？</p>
          <a
            href="https://jobs.company.co.jp"
            className="mt-3 inline-block px-5 py-2.5 bg-emerald-700 text-white text-sm font-medium rounded-lg hover:bg-emerald-800"
          >
            求人を探す
          </a>
        </div>
      </article>
    </div>
  )
}
```

- [ ] **Step 6: コミット**

```bash
git add apps/salary-data/
git commit -m "feat: salary-data - 年収データサイト構築"
```

---

### Task 3: agent-compare サイト構築

**Files:**
- Create: `apps/agent-compare/package.json`
- Create: `apps/agent-compare/next.config.ts`
- Create: `apps/agent-compare/app/layout.tsx`
- Create: `apps/agent-compare/app/globals.css`
- Create: `apps/agent-compare/app/page.tsx`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/agent-compare
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

- [ ] **Step 2: package.jsonを更新**

```json
{
  "dependencies": {
    "@recruitment/db": "workspace:*",
    "@phosphor-icons/react": "^2.1.0",
    "clsx": "^2.1.0"
  }
}
```

- [ ] **Step 3: next.config.tsを設定**

```typescript
import type { NextConfig } from 'next'
const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/db'],
}
export default nextConfig
```

- [ ] **Step 4: 比較コンテンツページを作成（静的コンテンツ）**

`apps/agent-compare/app/page.tsx`:

```tsx
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: '転職エージェント比較 - 20代・30代におすすめのエージェント',
  description: '20代・30代向けの転職エージェントを特徴・強みで比較しています。',
}

const AGENTS = [
  {
    name: 'リクルートエージェント',
    target: '全年齢・全職種',
    strength: '求人数No.1。幅広い業種・職種をカバー。',
    bestFor: '初めての転職・幅広く探したい人',
    url: 'https://www.r-agent.com',
  },
  {
    name: 'doda',
    target: '20代・30代',
    strength: 'スカウト機能が充実。エージェントとの相性が良い。',
    bestFor: 'スカウトを活用したい人',
    url: 'https://doda.jp',
  },
  {
    name: 'マイナビエージェント',
    target: '20代・第二新卒',
    strength: '20代に強い。第二新卒サポートが手厚い。',
    bestFor: '20代・第二新卒',
    url: 'https://mynavi-agent.jp',
  },
  {
    name: 'レバテックキャリア',
    target: 'ITエンジニア',
    strength: 'IT・Web業界特化。技術理解のある担当者。',
    bestFor: 'エンジニア・デザイナー',
    url: 'https://career.levtech.jp',
  },
]

export default function AgentComparePage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold text-gray-900 tracking-tight">
        転職エージェント比較
      </h1>
      <p className="mt-2 text-gray-500">
        20代・30代の転職に役立つエージェントを比較しました
      </p>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {AGENTS.map((agent) => (
          <div
            key={agent.name}
            className="p-6 bg-white border border-gray-200 rounded-2xl"
          >
            <h2 className="font-bold text-gray-900">{agent.name}</h2>
            <p className="mt-1 text-xs text-gray-400">{agent.target}</p>
            <p className="mt-3 text-sm text-gray-700">{agent.strength}</p>
            <p className="mt-2 text-xs font-medium text-indigo-700">
              こんな人に: {agent.bestFor}
            </p>
            <a
              href={agent.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-block text-xs text-gray-500 underline hover:text-gray-700"
            >
              公式サイトを見る
            </a>
          </div>
        ))}
      </div>

      <div className="mt-12 p-6 bg-indigo-50 rounded-2xl">
        <p className="font-semibold text-indigo-900">
          エージェント経由で求人を探す
        </p>
        <p className="mt-1 text-sm text-indigo-700">
          当サービスでも転職サポートを行っています。
        </p>
        <a
          href="https://jobs.company.co.jp"
          className="mt-3 inline-block px-5 py-2.5 bg-indigo-700 text-white text-sm font-medium rounded-lg hover:bg-indigo-800"
        >
          求人を見る
        </a>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: layout.tsxを作成**

`apps/agent-compare/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={`${geist.className} bg-white`}>
        <header className="border-b border-gray-200">
          <div className="max-w-4xl mx-auto px-4 h-14 flex items-center">
            <a href="/" className="font-bold text-gray-900">転職エージェント比較</a>
          </div>
        </header>
        <main>{children}</main>
        <footer className="border-t border-gray-100 mt-16">
          <div className="max-w-4xl mx-auto px-4 py-8">
            <p className="text-sm text-gray-400">
              &copy; {new Date().getFullYear()} 転職エージェント比較
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
```

- [ ] **Step 6: globals.cssを作成**

`apps/agent-compare/app/globals.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 7: コミット**

```bash
git add apps/agent-compare/
git commit -m "feat: agent-compare - エージェント比較サイト構築"
```

---

### Task 4: 記事自動生成API

**Files:**
- Create: `apps/admin/app/api/generate-articles/route.ts`

- [ ] **Step 1: 記事生成APIルートを作成**

`apps/admin/app/api/generate-articles/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { getAnthropicClient } from '@recruitment/ai'
import { createServiceClient, insertArticle } from '@recruitment/db'
import type { SiteId } from '@recruitment/db'

const TOPICS: { siteId: SiteId; keyword: string; title: string }[] = [
  {
    siteId: 'media-career',
    keyword: '転職 20代 成功',
    title: '20代の転職を成功させるための5つのポイント',
  },
  {
    siteId: 'media-career',
    keyword: '30代 転職 タイミング',
    title: '30代の転職に最適なタイミングとは',
  },
  {
    siteId: 'salary-data',
    keyword: '営業職 平均年収',
    title: '営業職の平均年収はいくら？職種別データを解説',
  },
  {
    siteId: 'salary-data',
    keyword: 'ITエンジニア 年収 相場',
    title: 'ITエンジニアの年収相場と年収アップの方法',
  },
]

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get('authorization')
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const client = getAnthropicClient()
  const db = createServiceClient()
  const results: { title: string; status: string }[] = []

  for (const topic of TOPICS) {
    try {
      const message = await client.messages.create({
        model: 'claude-sonnet-4-6',
        max_tokens: 2048,
        system: `あなたは転職・キャリアの専門ライターです。
SEOを意識した読みやすい日本語記事を書いてください。
記事は800〜1200文字程度で、段落を空行で区切ってください。
最後に転職を検討している読者への一言アドバイスを添えてください。
タイトルや見出し記号は使わず、本文のみ出力してください。`,
        messages: [
          {
            role: 'user',
            content: `次のテーマで記事を書いてください: ${topic.title}`,
          },
        ],
      })

      const content = message.content[0]
      if (content.type !== 'text') continue

      const slug = `${topic.siteId}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
      const excerpt = content.text.slice(0, 120).replace(/\n/g, '') + '...'

      await insertArticle(db, {
        site_id: topic.siteId,
        title: topic.title,
        content: content.text,
        excerpt,
        slug,
        is_published: true,
        published_at: new Date().toISOString(),
      })

      results.push({ title: topic.title, status: 'ok' })
    } catch (e) {
      results.push({ title: topic.title, status: `error: ${String(e)}` })
    }
  }

  return NextResponse.json({ results })
}
```

- [ ] **Step 2: CRON_SECRETを環境変数に追加**

`.env.example` に追記:

```bash
# 記事生成cron認証
CRON_SECRET=
```

Vercel管理画面の `apps/admin` プロジェクトにも `CRON_SECRET` を設定（ランダムな文字列を生成して使用）:

```bash
openssl rand -hex 32
```

- [ ] **Step 3: コミット**

```bash
git add apps/admin/app/api/ .env.example
git commit -m "feat: admin - 記事自動生成APIエンドポイント"
```

---

### Task 5: GitHub Actions cron設定

**Files:**
- Create: `.github/workflows/generate-articles.yml`

- [ ] **Step 1: cronワークフローを作成**

`.github/workflows/generate-articles.yml`:

```yaml
name: 記事自動生成

on:
  schedule:
    # 毎週月曜 日本時間 午前9時（UTC 00:00）
    - cron: '0 0 * * 1'
  workflow_dispatch:  # 手動実行も可能

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - name: 記事生成APIを呼び出す
        run: |
          curl -X POST \
            -H "Authorization: Bearer ${{ secrets.CRON_SECRET }}" \
            -H "Content-Type: application/json" \
            "${{ secrets.ADMIN_URL }}/api/generate-articles"
```

- [ ] **Step 2: GitHub Secretsを設定**

GitHubリポジトリ → Settings → Secrets and variables → Actions で以下を追加:

| Secret名 | 値 |
|---|---|
| `CRON_SECRET` | Vercelに設定したものと同じ値 |
| `ADMIN_URL` | Vercelにデプロイした管理画面のURL（例: https://admin-xxx.vercel.app） |

- [ ] **Step 3: 手動でワークフローを実行してテスト**

GitHub → Actions タブ → 「記事自動生成」→ 「Run workflow」

- [ ] **Step 4: Supabaseで記事が生成されているか確認**

Supabase → Table Editor → articles テーブルに記事が入っていることを確認

- [ ] **Step 5: コミット**

```bash
git add .github/
git commit -m "feat: GitHub Actions - 記事自動生成cron"
git push
```

---

## Phase 4 完了チェックリスト

- [ ] media-career: 記事一覧・詳細ページが表示される
- [ ] salary-data: 記事一覧・詳細ページが表示される
- [ ] agent-compare: 比較ページが表示される
- [ ] 手動でcronを実行して記事がSupabaseに投入される
- [ ] 投入された記事がmedia-career・salary-dataのサイトに反映される
- [ ] 5サイト全てがVercelにデプロイされている
- [ ] 各サイトの記事末CTAが求人サイトに正しくリンクしている

---

## 全フェーズ完了後のサブドメイン設定

Vercel → 各プロジェクト → Settings → Domains で以下を追加:

| サイト | ドメイン |
|---|---|
| jobs-main | jobs.company.co.jp |
| jobs-region | local.company.co.jp |
| media-career | media.company.co.jp |
| salary-data | salary.company.co.jp |
| agent-compare | agents.company.co.jp |
| admin | admin.company.co.jp |

DNSの設定はメインドメインのDNSプロバイダでCNAMEレコードを追加:
```
jobs    CNAME  cname.vercel-dns.com
local   CNAME  cname.vercel-dns.com
media   CNAME  cname.vercel-dns.com
salary  CNAME  cname.vercel-dns.com
agents  CNAME  cname.vercel-dns.com
admin   CNAME  cname.vercel-dns.com
```
