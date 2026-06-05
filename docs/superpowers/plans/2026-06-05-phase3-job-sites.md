# Phase 3: 求人サイト Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** jobs-main（求人総合）とjobs-region（地域特化）の2サイトを構築する。同じDBから求人を表示し、外部応募URLへ誘導する。

**Architecture:** 2つのNext.jsアプリがSupabaseの同じjobsテーブルを参照する。jobs-regionはprefectureカラムでフィルタするだけ。デザインは共通のpackages/uiを使い、アクセントカラーのみ変える。

**Tech Stack:** Next.js 15, Tailwind v4, @recruitment/db, @recruitment/ui, @phosphor-icons/react

**前提:** Phase 1、Phase 2完了済み。Supabaseにテストデータが入っている。

---

## File Structure

```
apps/jobs-main/
├── package.json
├── next.config.ts
├── app/
│   ├── layout.tsx
│   ├── page.tsx              # 求人一覧（トップ）
│   ├── jobs/
│   │   └── [id]/
│   │       └── page.tsx      # 求人詳細
│   └── globals.css
└── components/
    ├── Header.tsx
    ├── Footer.tsx
    ├── SearchFilter.tsx      # 絞り込みUI
    └── JobList.tsx

apps/jobs-region/
├── package.json
├── next.config.ts
├── app/
│   ├── layout.tsx
│   ├── page.tsx              # 都道府県一覧
│   ├── [prefecture]/
│   │   └── page.tsx          # 都道府県別求人一覧
│   └── globals.css
└── components/
    ├── Header.tsx
    └── PrefectureGrid.tsx
```

---

### Task 1: jobs-main 初期化

**Files:**
- Create: `apps/jobs-main/package.json`
- Create: `apps/jobs-main/next.config.ts`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/jobs-main
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

- [ ] **Step 2: package.jsonに内部パッケージを追加**

`apps/jobs-main/package.json` の `dependencies` に追加:

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

`apps/jobs-main/next.config.ts`:

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/ui', '@recruitment/db'],
}

export default nextConfig
```

- [ ] **Step 4: 依存関係インストール**

```bash
cd ../.. && pnpm install
```

- [ ] **Step 5: コミット**

```bash
git add apps/jobs-main/
git commit -m "feat: jobs-main - Next.jsアプリ初期化"
```

---

### Task 2: jobs-main レイアウト

**Files:**
- Create: `apps/jobs-main/app/globals.css`
- Create: `apps/jobs-main/components/Header.tsx`
- Create: `apps/jobs-main/components/Footer.tsx`
- Modify: `apps/jobs-main/app/layout.tsx`

- [ ] **Step 1: globals.cssを作成**

`apps/jobs-main/app/globals.css`:

```css
@import "tailwindcss";

:root {
  --accent: #1d4ed8;
  --accent-light: #eff6ff;
}
```

- [ ] **Step 2: Headerを作成**

`apps/jobs-main/components/Header.tsx`:

```tsx
import Link from 'next/link'
import { Briefcase } from '@phosphor-icons/react/dist/ssr'

export function Header() {
  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-bold text-gray-900">
          <Briefcase size={22} weight="fill" className="text-blue-700" />
          求人総合
        </Link>
        <a
          href="/jobs/import"
          className="text-sm text-blue-700 hover:text-blue-800 font-medium"
        >
          採用担当者の方へ
        </a>
      </div>
    </header>
  )
}
```

- [ ] **Step 3: Footerを作成**

`apps/jobs-main/components/Footer.tsx`:

```tsx
export function Footer() {
  return (
    <footer className="border-t border-gray-200 bg-white mt-16">
      <div className="max-w-5xl mx-auto px-4 py-8">
        <p className="text-sm text-gray-500">
          &copy; {new Date().getFullYear()} 求人総合
        </p>
      </div>
    </footer>
  )
}
```

- [ ] **Step 4: layout.tsxを更新**

`apps/jobs-main/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import { Header } from '../components/Header'
import { Footer } from '../components/Footer'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: '求人総合 - 転職・求人情報',
  description: '20代・30代の転職に役立つ求人情報を掲載しています。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={`${geist.className} bg-gray-50`}>
        <Header />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  )
}
```

- [ ] **Step 5: コミット**

```bash
git add apps/jobs-main/
git commit -m "feat: jobs-main - レイアウト"
```

---

### Task 3: jobs-main トップページ（求人一覧）

**Files:**
- Create: `apps/jobs-main/app/page.tsx`

- [ ] **Step 1: トップページを作成**

`apps/jobs-main/app/page.tsx`:

```tsx
import { createPublicClient, getPublishedJobs } from '@recruitment/db'
import { JobCard } from '@recruitment/ui'
import { MapPin } from '@phosphor-icons/react/dist/ssr'

const PREFECTURES = [
  '東京都', '大阪府', '神奈川県', '愛知県', '福岡県',
  '埼玉県', '千葉県', '北海道', '宮城県', '広島県',
]

type SearchParams = { prefecture?: string; page?: string }

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const params = await searchParams
  const page = Number(params.page ?? 1)
  const limit = 20
  const offset = (page - 1) * limit

  const client = createPublicClient()
  const jobs = await getPublishedJobs(client, 'jobs-main', {
    prefecture: params.prefecture,
    limit,
    offset,
  })

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 tracking-tight">
          求人情報
        </h1>
        <p className="mt-2 text-gray-500">
          20代・30代の転職に役立つ求人を掲載しています
        </p>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        <a
          href="/"
          className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-sm border transition-colors ${
            !params.prefecture
              ? 'bg-blue-700 text-white border-blue-700'
              : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
          }`}
        >
          すべて
        </a>
        {PREFECTURES.map((pref) => (
          <a
            key={pref}
            href={`/?prefecture=${encodeURIComponent(pref)}`}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-sm border transition-colors ${
              params.prefecture === pref
                ? 'bg-blue-700 text-white border-blue-700'
                : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
            }`}
          >
            <MapPin size={12} />
            {pref}
          </a>
        ))}
      </div>

      {jobs.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg">求人情報がありません</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} href={`/jobs/${job.id}`} />
          ))}
        </div>
      )}

      <div className="flex justify-between mt-8">
        {page > 1 && (
          <a
            href={`/?page=${page - 1}${params.prefecture ? `&prefecture=${params.prefecture}` : ''}`}
            className="px-4 py-2 border border-gray-200 rounded-lg text-sm bg-white hover:bg-gray-50"
          >
            前へ
          </a>
        )}
        {jobs.length === limit && (
          <a
            href={`/?page=${page + 1}${params.prefecture ? `&prefecture=${params.prefecture}` : ''}`}
            className="ml-auto px-4 py-2 border border-gray-200 rounded-lg text-sm bg-white hover:bg-gray-50"
          >
            次へ
          </a>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 動作確認**

```bash
cd apps/jobs-main && pnpm dev
```

Expected: http://localhost:3000 で求人一覧が表示される（Phase 2でデータを投入済みの場合）

- [ ] **Step 3: コミット**

```bash
git add apps/jobs-main/app/page.tsx
git commit -m "feat: jobs-main - 求人一覧トップページ"
```

---

### Task 4: jobs-main 求人詳細ページ

**Files:**
- Create: `apps/jobs-main/app/jobs/[id]/page.tsx`

- [ ] **Step 1: 詳細ページを作成**

`apps/jobs-main/app/jobs/[id]/page.tsx`:

```tsx
import { notFound } from 'next/navigation'
import { createPublicClient, getJobById } from '@recruitment/db'
import { MapPin, CurrencyJpy, Briefcase, ArrowSquareOut } from '@phosphor-icons/react/dist/ssr'
import type { Metadata } from 'next'

type Props = { params: Promise<{ id: string }> }

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params
  const client = createPublicClient()
  const job = await getJobById(client, id)
  if (!job) return { title: '求人が見つかりません' }
  return {
    title: `${job.title} | 求人総合`,
    description: job.description?.slice(0, 120) ?? undefined,
  }
}

export default async function JobDetailPage({ params }: Props) {
  const { id } = await params
  const client = createPublicClient()
  const job = await getJobById(client, id)
  if (!job) notFound()

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <a href="/" className="text-sm text-blue-700 hover:underline">
        ← 求人一覧に戻る
      </a>

      <div className="mt-6 bg-white border border-gray-200 rounded-2xl p-8">
        <h1 className="text-2xl font-bold text-gray-900">{job.title}</h1>

        {job.company_name && (
          <p className="mt-1 text-gray-500">{job.company_name}</p>
        )}

        <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-600">
          {job.location && (
            <span className="flex items-center gap-1.5">
              <MapPin size={15} weight="bold" />
              {job.location}
            </span>
          )}
          {job.salary && (
            <span className="flex items-center gap-1.5">
              <CurrencyJpy size={15} weight="bold" />
              {job.salary}
            </span>
          )}
          {job.employment_type && (
            <span className="flex items-center gap-1.5">
              <Briefcase size={15} weight="bold" />
              {job.employment_type}
            </span>
          )}
        </div>

        {job.description && (
          <div className="mt-6 pt-6 border-t border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">仕事内容</h2>
            <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
              {job.description}
            </p>
          </div>
        )}

        <div className="mt-8">
          <a
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-8 py-3 bg-blue-700 text-white font-semibold rounded-xl hover:bg-blue-800 transition-colors"
          >
            この求人に応募する
            <ArrowSquareOut size={18} />
          </a>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 動作確認**

http://localhost:3000 の求人カードをクリックして詳細ページが表示されることを確認

- [ ] **Step 3: コミット**

```bash
git add apps/jobs-main/app/jobs/
git commit -m "feat: jobs-main - 求人詳細ページ"
```

---

### Task 5: jobs-region 構築

**Files:**
- Create: `apps/jobs-region/package.json`
- Create: `apps/jobs-region/next.config.ts`
- Create: `apps/jobs-region/app/layout.tsx`
- Create: `apps/jobs-region/app/globals.css`
- Create: `apps/jobs-region/app/page.tsx`
- Create: `apps/jobs-region/app/[prefecture]/page.tsx`
- Create: `apps/jobs-region/components/PrefectureGrid.tsx`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/jobs-region
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

- [ ] **Step 2: package.jsonを更新（jobs-mainと同じ）**

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

`apps/jobs-region/next.config.ts`:

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/ui', '@recruitment/db'],
}

export default nextConfig
```

- [ ] **Step 4: globals.cssを作成**

`apps/jobs-region/app/globals.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 5: layout.tsxを作成**

`apps/jobs-region/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: '地域別求人 - 転職・求人情報',
  description: '都道府県別の求人情報を掲載しています。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={`${geist.className} bg-gray-50 min-h-screen`}>
        <header className="bg-white border-b border-gray-200">
          <div className="max-w-5xl mx-auto px-4 h-14 flex items-center">
            <a href="/" className="font-bold text-gray-900">
              地域別求人
            </a>
          </div>
        </header>
        <main>{children}</main>
        <footer className="border-t border-gray-200 bg-white mt-16">
          <div className="max-w-5xl mx-auto px-4 py-6">
            <p className="text-sm text-gray-500">
              &copy; {new Date().getFullYear()} 地域別求人
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
```

- [ ] **Step 6: トップページ（都道府県一覧）を作成**

`apps/jobs-region/app/page.tsx`:

```tsx
import { createPublicClient } from '@recruitment/db'
import { MapPin } from '@phosphor-icons/react/dist/ssr'

const PREFECTURES = [
  '北海道', '青森県', '岩手県', '宮城県', '秋田県',
  '山形県', '福島県', '茨城県', '栃木県', '群馬県',
  '埼玉県', '千葉県', '東京都', '神奈川県', '新潟県',
  '富山県', '石川県', '福井県', '山梨県', '長野県',
  '岐阜県', '静岡県', '愛知県', '三重県', '滋賀県',
  '京都府', '大阪府', '兵庫県', '奈良県', '和歌山県',
  '鳥取県', '島根県', '岡山県', '広島県', '山口県',
  '徳島県', '香川県', '愛媛県', '高知県', '福岡県',
  '佐賀県', '長崎県', '熊本県', '大分県', '宮崎県',
  '鹿児島県', '沖縄県',
]

export default function RegionTopPage() {
  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 tracking-tight">
          都道府県から求人を探す
        </h1>
        <p className="mt-2 text-gray-500">
          お住まいの地域や希望の勤務地で絞り込めます
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
        {PREFECTURES.map((pref) => (
          <a
            key={pref}
            href={`/${encodeURIComponent(pref)}`}
            className="flex items-center gap-2 px-4 py-3 bg-white border border-gray-200 rounded-xl
              text-sm font-medium text-gray-700 hover:border-blue-300 hover:text-blue-700 transition-all"
          >
            <MapPin size={14} />
            {pref}
          </a>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 7: 都道府県別求人ページを作成**

`apps/jobs-region/app/[prefecture]/page.tsx`:

```tsx
import { createPublicClient, getPublishedJobs } from '@recruitment/db'
import { JobCard } from '@recruitment/ui'
import type { Metadata } from 'next'

type Props = { params: Promise<{ prefecture: string }> }

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { prefecture } = await params
  const name = decodeURIComponent(prefecture)
  return {
    title: `${name}の求人 | 地域別求人`,
    description: `${name}の転職・求人情報を掲載しています。`,
  }
}

export default async function PrefecturePage({ params }: Props) {
  const { prefecture } = await params
  const name = decodeURIComponent(prefecture)
  const client = createPublicClient()
  const jobs = await getPublishedJobs(client, 'jobs-main', {
    prefecture: name,
    limit: 30,
  })

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <a href="/" className="text-sm text-blue-700 hover:underline">
        ← 都道府県一覧に戻る
      </a>

      <div className="mt-6 mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          {name}の求人 ({jobs.length}件)
        </h1>
      </div>

      {jobs.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p>{name}の求人は現在ありません</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} href={job.apply_url} />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 8: 依存関係インストールと動作確認**

```bash
cd ../.. && pnpm install
cd apps/jobs-region && pnpm dev
```

Expected: http://localhost:3001 で都道府県一覧が表示される

- [ ] **Step 9: コミット**

```bash
git add apps/jobs-region/
git commit -m "feat: jobs-region - 地域特化求人サイト構築"
git push
```

---

## Phase 3 完了チェックリスト

- [ ] jobs-main: http://localhost:3000 で求人一覧が表示される
- [ ] jobs-main: 都道府県フィルタが動作する
- [ ] jobs-main: 求人詳細ページから外部応募URLに遷移できる
- [ ] jobs-region: http://localhost:3001 で都道府県一覧が表示される
- [ ] jobs-region: 都道府県クリックで絞り込み一覧が表示される
- [ ] 両サイトがVercelにデプロイされている

Phase 3完了後、Phase 4（コンテンツサイト）に進む。
