# Phase 3: 3コンテンツサイト構築 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** career-stories（転職体験談）・salary-data（年収データ）・career-tips（転職ノウハウ）の3サイトを構築し、Vercelにデプロイする

**Architecture:** 3つとも同じNext.js構成（記事一覧 + 記事詳細）。site_idとアクセントカラーだけ異なる。ISRで記事更新を自動反映する。

**Tech Stack:** Next.js 15, Tailwind v4, @recruitment/db, @recruitment/ui, @phosphor-icons/react

**前提:** Phase 1・Phase 2完了済み。Supabaseに記事データが入っている。

---

## File Structure

```
apps/career-stories/
├── package.json
├── next.config.ts
├── app/
│   ├── layout.tsx          # ヘッダー・フッター
│   ├── page.tsx            # 記事一覧
│   ├── [slug]/page.tsx     # 記事詳細
│   └── globals.css

apps/salary-data/
├── （career-storiesと同じ構成、site_idとカラーのみ異なる）

apps/career-tips/
├── （career-storiesと同じ構成、site_idとカラーのみ異なる）
```

---

### Task 1: career-stories 構築

**Files:**
- Create: `apps/career-stories/package.json`
- Create: `apps/career-stories/next.config.ts`
- Create: `apps/career-stories/app/globals.css`
- Create: `apps/career-stories/app/layout.tsx`
- Create: `apps/career-stories/app/page.tsx`
- Create: `apps/career-stories/app/[slug]/page.tsx`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/career-stories
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

- [ ] **Step 2: package.jsonの依存関係を更新**

`apps/career-stories/package.json` の `dependencies`:

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

`apps/career-stories/next.config.ts`:

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/ui', '@recruitment/db'],
}

export default nextConfig
```

- [ ] **Step 4: globals.cssを作成**

`apps/career-stories/app/globals.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 5: layout.tsxを作成**

`apps/career-stories/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: '転職体験談メディア - リアルな転職ストーリー',
  description: '20代・30代のリアルな転職体験談を紹介しています。業界別・職種別の転職ストーリーが読めます。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={`${geist.className} bg-white text-gray-900`}>
        <header className="border-b border-gray-200">
          <div className="max-w-2xl mx-auto px-4 h-14 flex items-center justify-between">
            <a href="/" className="font-bold text-gray-900">転職体験談</a>
            <a
              href="https://jobs.company.co.jp"
              className="text-sm text-blue-700 font-medium hover:underline"
            >
              求人を見る
            </a>
          </div>
        </header>
        <main>{children}</main>
        <footer className="border-t border-gray-100 mt-20">
          <div className="max-w-2xl mx-auto px-4 py-8">
            <p className="text-sm text-gray-400">
              &copy; {new Date().getFullYear()} 転職体験談メディア
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
```

- [ ] **Step 6: 記事一覧ページを作成**

`apps/career-stories/app/page.tsx`:

```tsx
import { createPublicClient, getPublishedArticles } from '@recruitment/db'
import { ArticleCard } from '@recruitment/ui'

export const revalidate = 3600 // 1時間キャッシュ

export default async function HomePage() {
  const client = createPublicClient()
  const articles = await getPublishedArticles(client, 'career-stories', { limit: 30 })

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight">転職体験談</h1>
        <p className="mt-2 text-gray-500">
          20代・30代のリアルな転職ストーリー
        </p>
      </div>

      {articles.length === 0 ? (
        <p className="text-gray-400">記事を準備中です</p>
      ) : (
        <div className="space-y-5">
          {articles.map((article) => (
            <ArticleCard
              key={article.id}
              article={article}
              href={`/${article.slug}`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 7: 記事詳細ページを作成**

`apps/career-stories/app/[slug]/page.tsx`:

```tsx
import { notFound } from 'next/navigation'
import { createPublicClient, getArticleBySlug } from '@recruitment/db'
import type { Metadata } from 'next'

export const revalidate = 3600

type Props = { params: Promise<{ slug: string }> }

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const client = createPublicClient()
  const article = await getArticleBySlug(client, 'career-stories', slug)
  if (!article) return { title: '記事が見つかりません' }
  return {
    title: `${article.title} | 転職体験談`,
    description: article.excerpt ?? undefined,
  }
}

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params
  const client = createPublicClient()
  const article = await getArticleBySlug(client, 'career-stories', slug)
  if (!article) notFound()

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <a href="/" className="text-sm text-blue-700 hover:underline">
        ← 記事一覧
      </a>
      <article className="mt-8">
        <h1 className="text-2xl font-bold leading-snug">{article.title}</h1>
        <p className="mt-2 text-sm text-gray-400">
          {article.published_at
            ? new Date(article.published_at).toLocaleDateString('ja-JP')
            : ''}
        </p>
        <div className="mt-8 space-y-4">
          {article.content.split('\n\n').map((para, i) => (
            <p key={i} className="text-gray-700 leading-[1.8]">{para}</p>
          ))}
        </div>
        <div className="mt-12 p-6 bg-blue-50 rounded-2xl">
          <p className="font-semibold text-blue-900">転職を考えていますか？</p>
          <p className="mt-1 text-sm text-blue-700">
            まずは求人情報をチェックしてみましょう。
          </p>
          <a
            href="https://jobs.company.co.jp"
            className="mt-4 inline-block px-5 py-2.5 bg-blue-700 text-white text-sm font-semibold rounded-xl hover:bg-blue-800 transition-colors"
          >
            求人を見る
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
cd apps/career-stories && pnpm dev
```

Expected: http://localhost:3000 で記事一覧が表示される（Phase 2で記事生成済みの場合）

- [ ] **Step 9: コミット**

```bash
git add apps/career-stories/
git commit -m "feat: career-stories - 転職体験談メディア構築"
```

---

### Task 2: salary-data 構築

career-storiesとほぼ同じ。`site_id`と色とコピーのみ変える。

**Files:**
- Create: `apps/salary-data/package.json`
- Create: `apps/salary-data/next.config.ts`
- Create: `apps/salary-data/app/globals.css`
- Create: `apps/salary-data/app/layout.tsx`
- Create: `apps/salary-data/app/page.tsx`
- Create: `apps/salary-data/app/[slug]/page.tsx`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/salary-data
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

- [ ] **Step 2: package.json・next.config.tsをcareer-storiesと同じ内容で作成**

`apps/salary-data/package.json` の dependencies:

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

`apps/salary-data/next.config.ts`:

```typescript
import type { NextConfig } from 'next'
const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/ui', '@recruitment/db'],
}
export default nextConfig
```

- [ ] **Step 3: globals.cssを作成**

`apps/salary-data/app/globals.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 4: layout.tsxを作成（エメラルド系カラー）**

`apps/salary-data/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: '職種別年収データ - 平均年収・給与情報',
  description: '職種・業界別の平均年収データと年収アップの方法を解説しています。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={`${geist.className} bg-white text-gray-900`}>
        <header className="border-b border-gray-200">
          <div className="max-w-2xl mx-auto px-4 h-14 flex items-center justify-between">
            <a href="/" className="font-bold text-gray-900">年収データ</a>
            <a
              href="https://jobs.company.co.jp"
              className="text-sm text-emerald-700 font-medium hover:underline"
            >
              求人を見る
            </a>
          </div>
        </header>
        <main>{children}</main>
        <footer className="border-t border-gray-100 mt-20">
          <div className="max-w-2xl mx-auto px-4 py-8">
            <p className="text-sm text-gray-400">
              &copy; {new Date().getFullYear()} 職種別年収データ
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
```

- [ ] **Step 5: page.tsxを作成**

`apps/salary-data/app/page.tsx`:

```tsx
import { createPublicClient, getPublishedArticles } from '@recruitment/db'
import { ArticleCard } from '@recruitment/ui'

export const revalidate = 3600

export default async function HomePage() {
  const client = createPublicClient()
  const articles = await getPublishedArticles(client, 'salary-data', { limit: 30 })

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight">職種別 年収データ</h1>
        <p className="mt-2 text-gray-500">
          転職で年収アップするための給与情報
        </p>
      </div>
      {articles.length === 0 ? (
        <p className="text-gray-400">記事を準備中です</p>
      ) : (
        <div className="space-y-5">
          {articles.map((article) => (
            <ArticleCard
              key={article.id}
              article={article}
              href={`/${article.slug}`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 6: [slug]/page.tsxを作成（emeraldカラー）**

`apps/salary-data/app/[slug]/page.tsx`:

```tsx
import { notFound } from 'next/navigation'
import { createPublicClient, getArticleBySlug } from '@recruitment/db'
import type { Metadata } from 'next'

export const revalidate = 3600

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

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params
  const client = createPublicClient()
  const article = await getArticleBySlug(client, 'salary-data', slug)
  if (!article) notFound()

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <a href="/" className="text-sm text-emerald-700 hover:underline">← 記事一覧</a>
      <article className="mt-8">
        <h1 className="text-2xl font-bold leading-snug">{article.title}</h1>
        <p className="mt-2 text-sm text-gray-400">
          {article.published_at
            ? new Date(article.published_at).toLocaleDateString('ja-JP')
            : ''}
        </p>
        <div className="mt-8 space-y-4">
          {article.content.split('\n\n').map((para, i) => (
            <p key={i} className="text-gray-700 leading-[1.8]">{para}</p>
          ))}
        </div>
        <div className="mt-12 p-6 bg-emerald-50 rounded-2xl">
          <p className="font-semibold text-emerald-900">年収アップを狙いませんか？</p>
          <p className="mt-1 text-sm text-emerald-700">
            求人情報で給与条件を確認してみましょう。
          </p>
          <a
            href="https://jobs.company.co.jp"
            className="mt-4 inline-block px-5 py-2.5 bg-emerald-700 text-white text-sm font-semibold rounded-xl hover:bg-emerald-800 transition-colors"
          >
            求人を見る
          </a>
        </div>
      </article>
    </div>
  )
}
```

- [ ] **Step 7: コミット**

```bash
git add apps/salary-data/
git commit -m "feat: salary-data - 年収データサイト構築"
```

---

### Task 3: career-tips 構築

**Files:**
- Create: `apps/career-tips/package.json`
- Create: `apps/career-tips/next.config.ts`
- Create: `apps/career-tips/app/globals.css`
- Create: `apps/career-tips/app/layout.tsx`
- Create: `apps/career-tips/app/page.tsx`
- Create: `apps/career-tips/app/[slug]/page.tsx`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/career-tips
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

- [ ] **Step 2: package.json・next.config.tsを作成（career-storiesと同じ）**

`apps/career-tips/package.json` の dependencies:

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

`apps/career-tips/next.config.ts`:

```typescript
import type { NextConfig } from 'next'
const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/ui', '@recruitment/db'],
}
export default nextConfig
```

- [ ] **Step 3: globals.cssを作成**

`apps/career-tips/app/globals.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 4: layout.tsxを作成（バイオレット系カラー）**

`apps/career-tips/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: '転職ノウハウ - 転職活動の実践ガイド',
  description: '職務経歴書の書き方から面接対策まで、転職活動に役立つ実践的なノウハウを解説しています。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={`${geist.className} bg-white text-gray-900`}>
        <header className="border-b border-gray-200">
          <div className="max-w-2xl mx-auto px-4 h-14 flex items-center justify-between">
            <a href="/" className="font-bold text-gray-900">転職ノウハウ</a>
            <a
              href="https://jobs.company.co.jp"
              className="text-sm text-violet-700 font-medium hover:underline"
            >
              求人を見る
            </a>
          </div>
        </header>
        <main>{children}</main>
        <footer className="border-t border-gray-100 mt-20">
          <div className="max-w-2xl mx-auto px-4 py-8">
            <p className="text-sm text-gray-400">
              &copy; {new Date().getFullYear()} 転職ノウハウ
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
```

- [ ] **Step 5: page.tsxを作成**

`apps/career-tips/app/page.tsx`:

```tsx
import { createPublicClient, getPublishedArticles } from '@recruitment/db'
import { ArticleCard } from '@recruitment/ui'

export const revalidate = 3600

export default async function HomePage() {
  const client = createPublicClient()
  const articles = await getPublishedArticles(client, 'career-tips', { limit: 30 })

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight">転職ノウハウ</h1>
        <p className="mt-2 text-gray-500">
          転職活動を成功させる実践的なガイド
        </p>
      </div>
      {articles.length === 0 ? (
        <p className="text-gray-400">記事を準備中です</p>
      ) : (
        <div className="space-y-5">
          {articles.map((article) => (
            <ArticleCard
              key={article.id}
              article={article}
              href={`/${article.slug}`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 6: [slug]/page.tsxを作成（violetカラー）**

`apps/career-tips/app/[slug]/page.tsx`:

```tsx
import { notFound } from 'next/navigation'
import { createPublicClient, getArticleBySlug } from '@recruitment/db'
import type { Metadata } from 'next'

export const revalidate = 3600

type Props = { params: Promise<{ slug: string }> }

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const client = createPublicClient()
  const article = await getArticleBySlug(client, 'career-tips', slug)
  if (!article) return { title: '記事が見つかりません' }
  return {
    title: `${article.title} | 転職ノウハウ`,
    description: article.excerpt ?? undefined,
  }
}

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params
  const client = createPublicClient()
  const article = await getArticleBySlug(client, 'career-tips', slug)
  if (!article) notFound()

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <a href="/" className="text-sm text-violet-700 hover:underline">← 記事一覧</a>
      <article className="mt-8">
        <h1 className="text-2xl font-bold leading-snug">{article.title}</h1>
        <p className="mt-2 text-sm text-gray-400">
          {article.published_at
            ? new Date(article.published_at).toLocaleDateString('ja-JP')
            : ''}
        </p>
        <div className="mt-8 space-y-4">
          {article.content.split('\n\n').map((para, i) => (
            <p key={i} className="text-gray-700 leading-[1.8]">{para}</p>
          ))}
        </div>
        <div className="mt-12 p-6 bg-violet-50 rounded-2xl">
          <p className="font-semibold text-violet-900">転職活動を始めませんか？</p>
          <p className="mt-1 text-sm text-violet-700">
            求人情報を確認して、最初の一歩を踏み出しましょう。
          </p>
          <a
            href="https://jobs.company.co.jp"
            className="mt-4 inline-block px-5 py-2.5 bg-violet-700 text-white text-sm font-semibold rounded-xl hover:bg-violet-800 transition-colors"
          >
            求人を見る
          </a>
        </div>
      </article>
    </div>
  )
}
```

- [ ] **Step 7: 依存関係インストールと全サイト動作確認**

```bash
cd ../.. && pnpm install
```

3つのターミナルで並列起動:

```bash
# ターミナル1
cd apps/career-stories && pnpm dev -- --port 3001

# ターミナル2
cd apps/salary-data && pnpm dev -- --port 3002

# ターミナル3
cd apps/career-tips && pnpm dev -- --port 3003
```

Expected:
- http://localhost:3001: 転職体験談一覧が表示される
- http://localhost:3002: 年収データ一覧が表示される
- http://localhost:3003: 転職ノウハウ一覧が表示される

- [ ] **Step 8: コミット**

```bash
git add apps/career-tips/
git commit -m "feat: career-tips - 転職ノウハウサイト構築"
git push
```

---

### Task 4: Vercelへのデプロイ

- [ ] **Step 1: Vercelに4プロジェクトを作成**

Vercelダッシュボード → 「Add New Project」を4回:

| プロジェクト名 | Root Directory |
|---|---|
| recruitment-admin | apps/admin |
| recruitment-career-stories | apps/career-stories |
| recruitment-salary-data | apps/salary-data |
| recruitment-career-tips | apps/career-tips |

- [ ] **Step 2: 各プロジェクトに環境変数を設定**

4プロジェクト全てに以下を設定（Vercel → プロジェクト → Settings → Environment Variables）:

```
NEXT_PUBLIC_SUPABASE_URL      = （SupabaseダッシュボードのURL）
NEXT_PUBLIC_SUPABASE_ANON_KEY = （SupabaseダッシュボードのAnon Key）
SUPABASE_SERVICE_ROLE_KEY     = （SupabaseダッシュボードのService Role Key）
```

adminプロジェクトのみ追加で設定:

```
ANTHROPIC_API_KEY = （Anthropicコンソールのキー）
CRON_SECRET       = （Phase 2で生成した値）
```

- [ ] **Step 3: 各サイトにサブドメインを設定**

VercelダッシュボードでDomains設定:

| プロジェクト | ドメイン |
|---|---|
| recruitment-career-stories | stories.会社ドメイン |
| recruitment-salary-data | salary.会社ドメイン |
| recruitment-career-tips | tips.会社ドメイン |
| recruitment-admin | admin.会社ドメイン |

DNSプロバイダでCNAMEレコードを追加:

```
stories  CNAME  cname.vercel-dns.com
salary   CNAME  cname.vercel-dns.com
tips     CNAME  cname.vercel-dns.com
admin    CNAME  cname.vercel-dns.com
```

- [ ] **Step 4: デプロイ確認**

各サイトのVercelデプロイURLにアクセスして動作確認。

- [ ] **Step 5: GitHub Secretsの ADMIN_URL を本番URLに更新**

GitHubリポジトリ → Settings → Secrets → `ADMIN_URL` を本番の管理画面URLに更新。

---

## Phase 3 完了チェックリスト

- [ ] career-stories: 記事一覧・詳細ページが表示される
- [ ] salary-data: 記事一覧・詳細ページが表示される
- [ ] career-tips: 記事一覧・詳細ページが表示される
- [ ] 各記事詳細の末尾に求人サイトへのCTAがある
- [ ] 4プロジェクト全てがVercelにデプロイされている
- [ ] サブドメインでアクセスできる
- [ ] GitHub Actions cronを手動実行すると記事が追加される

完了。毎週月曜朝9時に記事が自動生成・投稿されます。
