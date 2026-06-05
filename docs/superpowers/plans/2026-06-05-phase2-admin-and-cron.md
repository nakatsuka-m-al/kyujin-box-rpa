# Phase 2: 管理画面 + 記事自動生成cron Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 記事生成の状況確認ができる管理画面と、毎週自動で記事を生成・投稿するcronを構築する

**Architecture:** Next.js管理画面にPOSTエンドポイント（`/api/generate-articles`）を用意し、GitHub Actions cronから週次で呼び出す。CRON_SECRETでエンドポイントを保護する。管理画面では生成済み記事の一覧確認と手動生成トリガーができる。

**Tech Stack:** Next.js 15, Tailwind v4, @recruitment/db, @recruitment/ai, GitHub Actions

**前提:** Phase 1完了済み

---

## File Structure

```
apps/admin/
├── package.json
├── next.config.ts
├── app/
│   ├── layout.tsx
│   ├── page.tsx                    # 記事一覧（全サイト）
│   ├── globals.css
│   └── api/
│       └── generate-articles/
│           └── route.ts            # cron用エンドポイント
└── components/
    └── Nav.tsx

.github/
└── workflows/
    └── generate-articles.yml       # 毎週月曜朝9時
```

---

### Task 1: 管理画面 Next.js初期化

**Files:**
- Create: `apps/admin/package.json`
- Create: `apps/admin/next.config.ts`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/admin
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

プロンプトはすべてデフォルト（Enter）

- [ ] **Step 2: package.jsonの依存関係を更新**

`apps/admin/package.json` の `dependencies` に追加:

```json
{
  "dependencies": {
    "@recruitment/db": "workspace:*",
    "@recruitment/ai": "workspace:*",
    "@phosphor-icons/react": "^2.1.0",
    "clsx": "^2.1.0"
  }
}
```

- [ ] **Step 3: next.config.tsを設定**

`apps/admin/next.config.ts`:

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/db', '@recruitment/ai'],
}

export default nextConfig
```

- [ ] **Step 4: 依存関係インストール**

```bash
cd ../.. && pnpm install
```

- [ ] **Step 5: コミット**

```bash
git add apps/admin/
git commit -m "feat: admin - Next.jsアプリ初期化"
```

---

### Task 2: 管理画面レイアウト

**Files:**
- Create: `apps/admin/app/globals.css`
- Create: `apps/admin/components/Nav.tsx`
- Modify: `apps/admin/app/layout.tsx`

- [ ] **Step 1: globals.cssを作成**

`apps/admin/app/globals.css`:

```css
@import "tailwindcss";

body {
  background-color: #f8fafc;
}
```

- [ ] **Step 2: Navコンポーネントを作成**

`apps/admin/components/Nav.tsx`:

```tsx
'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { House, FileText, Lightning } from '@phosphor-icons/react'
import clsx from 'clsx'

const links = [
  { href: '/', label: 'ダッシュボード', icon: House },
  { href: '/articles', label: '記事一覧', icon: FileText },
]

export function Nav() {
  const pathname = usePathname()
  return (
    <nav className="w-52 shrink-0 bg-white border-r border-gray-200 min-h-screen p-4">
      <div className="mb-6 px-2">
        <span className="text-base font-bold text-gray-900">管理画面</span>
      </div>
      <ul className="space-y-1">
        {links.map(({ href, label, icon: Icon }) => (
          <li key={href}>
            <Link
              href={href}
              className={clsx(
                'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                pathname === href
                  ? 'bg-slate-100 text-slate-900'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              )}
            >
              <Icon size={16} weight={pathname === href ? 'bold' : 'regular'} />
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
```

- [ ] **Step 3: layout.tsxを更新**

`apps/admin/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import { Nav } from '../components/Nav'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: '管理画面',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={geist.className}>
        <div className="flex">
          <Nav />
          <main className="flex-1 p-8 max-w-4xl">{children}</main>
        </div>
      </body>
    </html>
  )
}
```

- [ ] **Step 4: ダッシュボードページを作成**

`apps/admin/app/page.tsx`:

```tsx
import { createServiceClient } from '@recruitment/db'

async function getCounts() {
  const client = createServiceClient()
  const sites = ['career-stories', 'salary-data', 'career-tips'] as const
  const counts = await Promise.all(
    sites.map(async (siteId) => {
      const { count } = await client
        .from('articles')
        .select('*', { count: 'exact', head: true })
        .eq('site_id', siteId)
        .eq('is_published', true)
      return { siteId, count: count ?? 0 }
    })
  )
  return counts
}

const SITE_LABELS: Record<string, string> = {
  'career-stories': '転職体験談',
  'salary-data': '年収データ',
  'career-tips': '転職ノウハウ',
}

export default async function DashboardPage() {
  const counts = await getCounts()

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">ダッシュボード</h1>
      <div className="grid grid-cols-3 gap-4">
        {counts.map(({ siteId, count }) => (
          <div key={siteId} className="bg-white border border-gray-200 rounded-xl p-5">
            <p className="text-sm text-gray-500">{SITE_LABELS[siteId]}</p>
            <p className="mt-1 text-3xl font-bold text-gray-900">{count}</p>
            <p className="text-xs text-gray-400">公開記事数</p>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: 動作確認**

```bash
cd apps/admin && pnpm dev
```

Expected: http://localhost:3000 でダッシュボードが表示される

- [ ] **Step 6: コミット**

```bash
git add apps/admin/
git commit -m "feat: admin - レイアウトとダッシュボード"
```

---

### Task 3: 記事一覧ページ

**Files:**
- Create: `apps/admin/app/articles/page.tsx`

- [ ] **Step 1: 記事一覧ページを作成**

`apps/admin/app/articles/page.tsx`:

```tsx
import { createServiceClient } from '@recruitment/db'

const SITE_LABELS: Record<string, string> = {
  'career-stories': '転職体験談',
  'salary-data': '年収データ',
  'career-tips': '転職ノウハウ',
}

export default async function ArticlesPage() {
  const client = createServiceClient()
  const { data: articles, error } = await client
    .from('articles')
    .select('id, site_id, title, published_at, is_published')
    .order('created_at', { ascending: false })
    .limit(100)

  if (error) return <p className="text-red-500">エラー: {error.message}</p>

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">
        記事一覧 ({articles?.length ?? 0}件)
      </h1>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-4 py-2.5 text-left">サイト</th>
              <th className="px-4 py-2.5 text-left">タイトル</th>
              <th className="px-4 py-2.5 text-left">投稿日</th>
              <th className="px-4 py-2.5 text-left">状態</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {(articles ?? []).map((article) => (
              <tr key={article.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-xs text-gray-500">
                  {SITE_LABELS[article.site_id] ?? article.site_id}
                </td>
                <td className="px-4 py-3 font-medium text-gray-900 max-w-sm truncate">
                  {article.title}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {article.published_at
                    ? new Date(article.published_at).toLocaleDateString('ja-JP')
                    : '-'}
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    article.is_published
                      ? 'bg-green-100 text-green-700'
                      : 'bg-gray-100 text-gray-500'
                  }`}>
                    {article.is_published ? '公開' : '下書き'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: コミット**

```bash
git add apps/admin/app/articles/
git commit -m "feat: admin - 記事一覧ページ"
```

---

### Task 4: 記事自動生成APIエンドポイント

**Files:**
- Create: `apps/admin/app/api/generate-articles/route.ts`

- [ ] **Step 1: 生成するトピックリストと定義**

サイトごとに毎週1本ずつ生成する（週4本 × 年52週 = 年間208本）。トピックはループして使い回す。

- [ ] **Step 2: APIルートを作成**

`apps/admin/app/api/generate-articles/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { generateArticle } from '@recruitment/ai'
import { insertArticle, createServiceClient } from '@recruitment/db'
import type { SiteId } from '@recruitment/db'

type Topic = {
  siteId: SiteId
  title: string
  keywords: string[]
}

// 各サイトのトピックリスト（順番にローテーション）
const TOPICS: Topic[] = [
  // career-stories
  { siteId: 'career-stories', title: '20代でIT業界に転職した話', keywords: ['IT 転職 20代', '未経験 エンジニア'] },
  { siteId: 'career-stories', title: '営業から事務職に転職して気づいたこと', keywords: ['営業 転職', '事務職 転職体験'] },
  { siteId: 'career-stories', title: '30代で初めての転職を経験して', keywords: ['30代 転職 初めて', '転職活動 体験談'] },
  { siteId: 'career-stories', title: '大手から中小企業に転職して変わったこと', keywords: ['大手 中小 転職', '転職 後悔 しない'] },

  // salary-data
  { siteId: 'salary-data', title: '営業職の平均年収と年収アップの方法', keywords: ['営業 平均年収', '営業 年収 上げる'] },
  { siteId: 'salary-data', title: 'Webエンジニアの年収相場を徹底解説', keywords: ['Webエンジニア 年収', 'エンジニア 給料'] },
  { siteId: 'salary-data', title: '事務職の年収は低い？現実と改善策', keywords: ['事務職 年収', '事務 給料 上げる'] },
  { siteId: 'salary-data', title: '転職で年収を上げるための交渉術', keywords: ['転職 年収交渉', '年収アップ 転職'] },

  // career-tips
  { siteId: 'career-tips', title: '職務経歴書の書き方【20代向け完全ガイド】', keywords: ['職務経歴書 書き方', '転職 書類'] },
  { siteId: 'career-tips', title: '転職面接でよく聞かれる質問と答え方', keywords: ['転職面接 質問', '面接 回答例'] },
  { siteId: 'career-tips', title: '転職活動の進め方ステップガイド', keywords: ['転職活動 進め方', '転職 手順'] },
  { siteId: 'career-tips', title: '転職タイミングの見極め方', keywords: ['転職 タイミング', '転職 いつ'] },
]

// 今週のインデックスを算出（週番号をトピック数で割った余り）
function getThisWeekTopics(): Topic[] {
  const weekNumber = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000))
  const topicsPerSite = 1
  const sites: SiteId[] = ['career-stories', 'salary-data', 'career-tips']

  return sites.map((siteId) => {
    const siteTopics = TOPICS.filter((t) => t.siteId === siteId)
    const index = weekNumber % siteTopics.length
    return siteTopics[index]
  })
}

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get('authorization')
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const db = createServiceClient()
  const topics = getThisWeekTopics()
  const results: { title: string; status: string }[] = []

  for (const topic of topics) {
    try {
      const generated = await generateArticle({
        siteId: topic.siteId,
        title: topic.title,
        keywords: topic.keywords,
      })

      await insertArticle(db, {
        site_id: topic.siteId,
        title: generated.title,
        content: generated.content,
        excerpt: generated.excerpt,
        slug: generated.slug,
        is_published: true,
        published_at: new Date().toISOString(),
      })

      results.push({ title: topic.title, status: 'ok' })
    } catch (e) {
      results.push({ title: topic.title, status: `error: ${String(e)}` })
    }
  }

  return NextResponse.json({ results, generatedAt: new Date().toISOString() })
}
```

- [ ] **Step 3: CRON_SECRETを生成してVercelに設定**

```bash
openssl rand -hex 32
```

出力された値をコピーして:
- Vercel → admin プロジェクト → Settings → Environment Variables → `CRON_SECRET` として追加
- GitHub → リポジトリ → Settings → Secrets → `CRON_SECRET` として追加（同じ値）

- [ ] **Step 4: ローカルで動作確認**

`.env.local` を作成（gitignoreされている）:

```bash
NEXT_PUBLIC_SUPABASE_URL=（Supabaseの値）
NEXT_PUBLIC_SUPABASE_ANON_KEY=（Supabaseの値）
SUPABASE_SERVICE_ROLE_KEY=（Supabaseの値）
ANTHROPIC_API_KEY=（Anthropicの値）
CRON_SECRET=test-secret-local
```

```bash
curl -X POST http://localhost:3000/api/generate-articles \
  -H "Authorization: Bearer test-secret-local"
```

Expected: `{"results":[{"title":"...","status":"ok"},...]}`

Supabaseで記事が3件生成されていることを確認。

- [ ] **Step 5: コミット**

```bash
git add apps/admin/app/api/
git commit -m "feat: admin - 記事自動生成APIエンドポイント"
```

---

### Task 5: GitHub Actions cron設定

**Files:**
- Create: `.github/workflows/generate-articles.yml`

- [ ] **Step 1: ワークフローファイルを作成**

`.github/workflows/generate-articles.yml`:

```yaml
name: 記事自動生成

on:
  schedule:
    # 毎週月曜 日本時間 午前9時（UTC 00:00）
    - cron: '0 0 * * 1'
  workflow_dispatch:

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - name: 記事生成APIを呼び出す
        run: |
          response=$(curl -s -w "\n%{http_code}" -X POST \
            -H "Authorization: Bearer ${{ secrets.CRON_SECRET }}" \
            -H "Content-Type: application/json" \
            "${{ secrets.ADMIN_URL }}/api/generate-articles")

          body=$(echo "$response" | head -n -1)
          status=$(echo "$response" | tail -n 1)

          echo "Status: $status"
          echo "Response: $body"

          if [ "$status" != "200" ]; then
            echo "Error: API returned status $status"
            exit 1
          fi
```

- [ ] **Step 2: GitHub Secretsに ADMIN_URL を追加**

GitHubリポジトリ → Settings → Secrets and variables → Actions:

| Secret名 | 値 |
|---|---|
| `CRON_SECRET` | Vercelに設定したものと同じ値 |
| `ADMIN_URL` | Vercelにデプロイした管理画面のURL（例: `https://admin-xxx.vercel.app`） |

- [ ] **Step 3: 手動実行でテスト**

GitHub → Actions タブ → 「記事自動生成」→ 「Run workflow」→ 「Run workflow」ボタン

Expected: ワークフローが緑チェックで完了する

- [ ] **Step 4: Supabaseで記事が追加されたことを確認**

Supabase → Table Editor → articles テーブルに3件追加されていることを確認

- [ ] **Step 5: コミット**

```bash
git add .github/
git commit -m "feat: GitHub Actions - 毎週記事自動生成cron"
git push
```

---

## Phase 2 完了チェックリスト

- [ ] http://localhost:3000 で管理画面が表示される
- [ ] ダッシュボードにサイト別記事数が表示される
- [ ] `/api/generate-articles` にPOSTすると3サイト分の記事が生成される
- [ ] GitHub Actions手動実行で記事が自動生成される
- [ ] 毎週月曜朝9時に自動実行される設定が入っている

Phase 2完了後、Phase 3（3サイトのフロントエンド構築）に進む。
