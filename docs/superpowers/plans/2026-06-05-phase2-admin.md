# Phase 2: 管理画面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CSVドラッグ&ドロップ → AI解析 → 求人プレビュー → 一括投稿ができる管理画面を構築する

**Architecture:** Next.js App RouterのServer Actionsを使ってファイルアップロードとAI解析を処理。フロントエンドはクライアントコンポーネントでドラッグ&ドロップUIを実装。解析結果をプレビューして「一括投稿」ボタンでDBに書き込む。

**Tech Stack:** Next.js 15, Tailwind v4, @phosphor-icons/react, motion/react, @recruitment/db, @recruitment/ai, @recruitment/ui

**前提:** Phase 1完了済み

---

## File Structure

```
apps/admin/
├── package.json
├── tsconfig.json
├── next.config.ts
├── app/
│   ├── layout.tsx
│   ├── page.tsx                    # ダッシュボード（概要）
│   ├── globals.css
│   ├── jobs/
│   │   ├── page.tsx                # 求人一覧
│   │   └── import/
│   │       ├── page.tsx            # CSVインポート画面
│   │       └── actions.ts          # Server Actions
│   └── articles/
│       └── page.tsx                # 記事一覧
└── components/
    ├── CsvDropzone.tsx             # ドラッグ&ドロップUI
    ├── JobPreviewTable.tsx         # インポート前プレビュー
    └── Nav.tsx                     # サイドナビ
```

---

### Task 1: Next.jsアプリ初期化

**Files:**
- Create: `apps/admin/package.json`
- Create: `apps/admin/next.config.ts`
- Create: `apps/admin/tsconfig.json`

- [ ] **Step 1: Next.jsアプリを作成**

```bash
cd apps/admin
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-import-alias
```

プロンプトはすべてデフォルト（Enter）

- [ ] **Step 2: package.jsonに内部パッケージを追加**

`apps/admin/package.json` の `dependencies` に追加:

```json
{
  "dependencies": {
    "@recruitment/db": "workspace:*",
    "@recruitment/ai": "workspace:*",
    "@recruitment/ui": "workspace:*",
    "@phosphor-icons/react": "^2.1.0",
    "motion": "^11.0.0",
    "clsx": "^2.1.0"
  }
}
```

- [ ] **Step 3: 依存関係インストール**

```bash
cd ../.. && pnpm install
```

- [ ] **Step 4: next.config.tsを更新**

`apps/admin/next.config.ts`:

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  transpilePackages: ['@recruitment/ui', '@recruitment/db', '@recruitment/ai'],
}

export default nextConfig
```

- [ ] **Step 5: 起動確認**

```bash
cd apps/admin && pnpm dev
```

Expected: http://localhost:3000 でNext.jsデフォルト画面が表示される

- [ ] **Step 6: コミット**

```bash
git add apps/admin/
git commit -m "feat: admin - Next.jsアプリ初期化"
```

---

### Task 2: レイアウトとナビゲーション

**Files:**
- Create: `apps/admin/components/Nav.tsx`
- Modify: `apps/admin/app/layout.tsx`
- Modify: `apps/admin/app/globals.css`

- [ ] **Step 1: グローバルCSSを設定**

`apps/admin/app/globals.css`:

```css
@import "tailwindcss";

:root {
  --navy-50: #f0f4ff;
  --navy-100: #e0e9ff;
  --navy-200: #c7d7fe;
  --navy-600: #3451b2;
  --navy-800: #1e3a8a;
  --navy-900: #1e3057;
}

body {
  font-family: 'Geist', system-ui, sans-serif;
  background-color: #f8fafc;
}
```

- [ ] **Step 2: Navコンポーネントを作成**

`apps/admin/components/Nav.tsx`:

```tsx
'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import {
  House,
  Briefcase,
  FileText,
  UploadSimple,
} from '@phosphor-icons/react'
import clsx from 'clsx'

const links = [
  { href: '/', label: 'ダッシュボード', icon: House },
  { href: '/jobs', label: '求人一覧', icon: Briefcase },
  { href: '/jobs/import', label: 'CSV投入', icon: UploadSimple },
  { href: '/articles', label: '記事一覧', icon: FileText },
]

export function Nav() {
  const pathname = usePathname()

  return (
    <nav className="w-56 shrink-0 bg-white border-r border-gray-200 min-h-screen p-4">
      <div className="mb-8 px-2">
        <span className="text-lg font-bold text-navy-900">管理画面</span>
      </div>
      <ul className="space-y-1">
        {links.map(({ href, label, icon: Icon }) => (
          <li key={href}>
            <Link
              href={href}
              className={clsx(
                'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                pathname === href
                  ? 'bg-navy-50 text-navy-900'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              )}
            >
              <Icon size={18} weight={pathname === href ? 'bold' : 'regular'} />
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
  title: '採用メディア 管理画面',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja">
      <body className={geist.className}>
        <div className="flex">
          <Nav />
          <main className="flex-1 p-8 max-w-5xl">
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}
```

- [ ] **Step 4: ダッシュボードページを作成**

`apps/admin/app/page.tsx`:

```tsx
export default function DashboardPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">ダッシュボード</h1>
      <p className="mt-2 text-gray-500">
        左のナビから操作を選んでください。
      </p>
    </div>
  )
}
```

- [ ] **Step 5: 動作確認**

```bash
pnpm dev
```

Expected: サイドナビが表示され、各リンクでページ遷移できる

- [ ] **Step 6: コミット**

```bash
git add apps/admin/
git commit -m "feat: admin - レイアウトとナビゲーション"
```

---

### Task 3: CSVドロップゾーンUI

**Files:**
- Create: `apps/admin/components/CsvDropzone.tsx`

- [ ] **Step 1: CsvDropzoneコンポーネントを作成**

`apps/admin/components/CsvDropzone.tsx`:

```tsx
'use client'

import { useRef, useState } from 'react'
import { UploadSimple, FileCsv } from '@phosphor-icons/react'
import clsx from 'clsx'

type CsvDropzoneProps = {
  onFile: (file: File) => void
  isLoading?: boolean
}

export function CsvDropzone({ onFile, isLoading }: CsvDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file && file.name.endsWith('.csv')) {
      onFile(file)
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) onFile(file)
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => !isLoading && inputRef.current?.click()}
      className={clsx(
        'relative flex flex-col items-center justify-center gap-3 p-12',
        'border-2 border-dashed rounded-2xl cursor-pointer transition-all',
        isDragging
          ? 'border-navy-600 bg-navy-50'
          : 'border-gray-300 bg-white hover:border-gray-400',
        isLoading && 'opacity-50 cursor-not-allowed'
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={handleChange}
        disabled={isLoading}
      />

      {isLoading ? (
        <>
          <div className="w-10 h-10 border-2 border-navy-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-600">AIが解析中...</p>
        </>
      ) : (
        <>
          <FileCsv size={40} className="text-gray-400" weight="light" />
          <div className="text-center">
            <p className="text-sm font-medium text-gray-900">
              CSVファイルをドロップ
            </p>
            <p className="text-xs text-gray-500 mt-1">
              またはクリックして選択
            </p>
          </div>
          <UploadSimple size={16} className="text-gray-400" />
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 型チェック**

```bash
cd apps/admin && pnpm typecheck 2>/dev/null || npx tsc --noEmit
```

Expected: エラーなし

- [ ] **Step 3: コミット**

```bash
git add apps/admin/components/CsvDropzone.tsx
git commit -m "feat: admin - CsvDropzoneコンポーネント"
```

---

### Task 4: 求人プレビューテーブル

**Files:**
- Create: `apps/admin/components/JobPreviewTable.tsx`

- [ ] **Step 1: JobPreviewTableコンポーネントを作成**

`apps/admin/components/JobPreviewTable.tsx`:

```tsx
'use client'

import { useState } from 'react'
import { CheckCircle, XCircle } from '@phosphor-icons/react'
import type { CsvParseResult } from '@recruitment/ai'

type JobPreviewTableProps = {
  result: CsvParseResult
  onPublish: (selectedIndexes: number[]) => void
  isPublishing?: boolean
}

export function JobPreviewTable({
  result,
  onPublish,
  isPublishing,
}: JobPreviewTableProps) {
  const [selected, setSelected] = useState<Set<number>>(
    new Set(result.jobs.map((_, i) => i))
  )

  function toggleAll() {
    if (selected.size === result.jobs.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(result.jobs.map((_, i) => i)))
    }
  }

  function toggle(i: number) {
    const next = new Set(selected)
    if (next.has(i)) {
      next.delete(i)
    } else {
      next.add(i)
    }
    setSelected(next)
  }

  return (
    <div className="space-y-4">
      {result.errors.length > 0 && (
        <div className="p-4 bg-orange-50 border border-orange-200 rounded-xl">
          <p className="text-sm font-medium text-orange-800 mb-2">
            スキップされた行 ({result.errors.length}件)
          </p>
          <ul className="text-xs text-orange-700 space-y-1">
            {result.errors.map((e, i) => (
              <li key={i} className="flex items-center gap-1.5">
                <XCircle size={14} />
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={selected.size === result.jobs.length}
              onChange={toggleAll}
              className="rounded"
            />
            すべて選択 ({selected.size}/{result.jobs.length}件)
          </label>
          <button
            onClick={() => onPublish([...selected])}
            disabled={selected.size === 0 || isPublishing}
            className="flex items-center gap-2 px-4 py-2 bg-navy-900 text-white text-sm font-medium rounded-lg
              hover:bg-navy-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <CheckCircle size={16} />
            {isPublishing ? '投稿中...' : `${selected.size}件を一括投稿`}
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
              <tr>
                <th className="w-8 px-4 py-2" />
                <th className="px-4 py-2 text-left">職種名</th>
                <th className="px-4 py-2 text-left">勤務地</th>
                <th className="px-4 py-2 text-left">給与</th>
                <th className="px-4 py-2 text-left">雇用形態</th>
                <th className="px-4 py-2 text-left">応募URL</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {result.jobs.map((job, i) => (
                <tr
                  key={i}
                  className={`cursor-pointer transition-colors ${
                    selected.has(i) ? 'bg-navy-50' : 'hover:bg-gray-50'
                  }`}
                  onClick={() => toggle(i)}
                >
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.has(i)}
                      onChange={() => toggle(i)}
                      onClick={(e) => e.stopPropagation()}
                      className="rounded"
                    />
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {job.title}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {job.location ?? '-'}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {job.salary ?? '-'}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {job.employment_type ?? '-'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs max-w-[200px] truncate">
                    {job.apply_url}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 型チェック**

```bash
npx tsc --noEmit
```

Expected: エラーなし

- [ ] **Step 3: コミット**

```bash
git add apps/admin/components/JobPreviewTable.tsx
git commit -m "feat: admin - JobPreviewTableコンポーネント"
```

---

### Task 5: CSVインポートのServer Actions

**Files:**
- Create: `apps/admin/app/jobs/import/actions.ts`

- [ ] **Step 1: Server Actionsを作成**

`apps/admin/app/jobs/import/actions.ts`:

```typescript
'use server'

import { parseCsvWithAI } from '@recruitment/ai'
import { insertJobs, publishJobs, createServiceClient } from '@recruitment/db'
import type { CsvParseResult } from '@recruitment/ai'
import type { SiteId } from '@recruitment/db'

export async function analyzeCsv(formData: FormData): Promise<CsvParseResult> {
  const file = formData.get('file') as File | null
  if (!file) throw new Error('ファイルが選択されていません')

  const text = await file.text()
  if (!text.trim()) throw new Error('CSVが空です')

  // 全サイト共通の求人として登録（jobs-mainをデフォルト）
  const result = await parseCsvWithAI(text, 'jobs-main' as SiteId)
  return result
}

export async function publishParsedJobs(
  jobs: CsvParseResult['jobs'],
  selectedIndexes: number[]
): Promise<{ count: number }> {
  const client = createServiceClient()
  const selectedJobs = selectedIndexes.map((i) => ({
    ...jobs[i],
    site_id: 'jobs-main' as SiteId,
  }))

  const inserted = await insertJobs(client, selectedJobs)
  await publishJobs(client, inserted.map((j) => j.id))

  return { count: inserted.length }
}
```

- [ ] **Step 2: 型チェック**

```bash
npx tsc --noEmit
```

Expected: エラーなし

- [ ] **Step 3: コミット**

```bash
git add apps/admin/app/jobs/import/actions.ts
git commit -m "feat: admin - CSVインポートServer Actions"
```

---

### Task 6: CSVインポート画面を組み立て

**Files:**
- Create: `apps/admin/app/jobs/import/page.tsx`

- [ ] **Step 1: インポートページを作成**

`apps/admin/app/jobs/import/page.tsx`:

```tsx
'use client'

import { useState } from 'react'
import { CheckCircle } from '@phosphor-icons/react'
import { CsvDropzone } from '../../../components/CsvDropzone'
import { JobPreviewTable } from '../../../components/JobPreviewTable'
import { analyzeCsv, publishParsedJobs } from './actions'
import type { CsvParseResult } from '@recruitment/ai'

type State =
  | { phase: 'idle' }
  | { phase: 'analyzing' }
  | { phase: 'preview'; result: CsvParseResult }
  | { phase: 'publishing' }
  | { phase: 'done'; count: number }
  | { phase: 'error'; message: string }

export default function ImportPage() {
  const [state, setState] = useState<State>({ phase: 'idle' })

  async function handleFile(file: File) {
    setState({ phase: 'analyzing' })
    try {
      const formData = new FormData()
      formData.append('file', file)
      const result = await analyzeCsv(formData)
      setState({ phase: 'preview', result })
    } catch (e) {
      setState({ phase: 'error', message: String(e) })
    }
  }

  async function handlePublish(selectedIndexes: number[]) {
    if (state.phase !== 'preview') return
    setState({ phase: 'publishing' })
    try {
      const { count } = await publishParsedJobs(state.result.jobs, selectedIndexes)
      setState({ phase: 'done', count })
    } catch (e) {
      setState({ phase: 'error', message: String(e) })
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">CSV求人投入</h1>
        <p className="mt-1 text-sm text-gray-500">
          CSVをドロップするとAIが自動で求人票に変換します。確認後、一括投稿できます。
        </p>
      </div>

      {(state.phase === 'idle' ||
        state.phase === 'analyzing' ||
        state.phase === 'error') && (
        <CsvDropzone
          onFile={handleFile}
          isLoading={state.phase === 'analyzing'}
        />
      )}

      {state.phase === 'error' && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl">
          <p className="text-sm text-red-700">{state.message}</p>
          <button
            onClick={() => setState({ phase: 'idle' })}
            className="mt-2 text-xs text-red-600 underline"
          >
            やり直す
          </button>
        </div>
      )}

      {state.phase === 'preview' && (
        <JobPreviewTable
          result={state.result}
          onPublish={handlePublish}
        />
      )}

      {state.phase === 'publishing' && (
        <JobPreviewTable
          result={(state as any).result ?? { jobs: [], errors: [] }}
          onPublish={() => {}}
          isPublishing
        />
      )}

      {state.phase === 'done' && (
        <div className="flex flex-col items-center gap-3 py-16">
          <CheckCircle size={48} className="text-green-500" weight="fill" />
          <p className="text-lg font-semibold text-gray-900">
            {state.count}件の求人を投稿しました
          </p>
          <button
            onClick={() => setState({ phase: 'idle' })}
            className="mt-2 px-4 py-2 bg-navy-900 text-white text-sm rounded-lg hover:bg-navy-800"
          >
            さらに投入する
          </button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 動作確認**

```bash
pnpm dev
```

1. http://localhost:3000/jobs/import を開く
2. サンプルCSVを作成して試す:

```csv
職種名,勤務地,給与,雇用形態,会社名,応募URL
Webエンジニア,東京都渋谷区,月給35万〜50万,正社員,テスト株式会社,https://example.com/apply/1
営業職,大阪府大阪市,月給25万〜35万,正社員,サンプル合同会社,https://example.com/apply/2
```

3. CSVをドロップ → AIが解析 → プレビューが表示される
4. 「一括投稿」ボタンをクリック → 投稿完了メッセージが表示される
5. Supabaseダッシュボードで `jobs` テーブルにデータが入っていることを確認

- [ ] **Step 3: 求人一覧ページを作成**

`apps/admin/app/jobs/page.tsx`:

```tsx
import { createServiceClient, getPublishedJobs } from '@recruitment/db'

export default async function JobsPage() {
  const client = createServiceClient()
  const jobs = await getPublishedJobs(client, 'jobs-main', { limit: 50 })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">
        求人一覧 ({jobs.length}件)
      </h1>
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-4 py-2 text-left">職種名</th>
              <th className="px-4 py-2 text-left">勤務地</th>
              <th className="px-4 py-2 text-left">給与</th>
              <th className="px-4 py-2 text-left">投稿日</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {jobs.map((job) => (
              <tr key={job.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{job.title}</td>
                <td className="px-4 py-3 text-gray-600">{job.location ?? '-'}</td>
                <td className="px-4 py-3 text-gray-600">{job.salary ?? '-'}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {job.published_at ? new Date(job.published_at).toLocaleDateString('ja-JP') : '-'}
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

- [ ] **Step 4: コミット**

```bash
git add apps/admin/
git commit -m "feat: admin - CSVインポート画面完成"
git push
```

---

## Phase 2 完了チェックリスト

- [ ] http://localhost:3000/jobs/import でCSVをドロップできる
- [ ] AIが解析してプレビューが表示される
- [ ] 一括投稿でSupabaseにデータが入る
- [ ] http://localhost:3000/jobs で投稿済み求人が確認できる
- [ ] Vercelにデプロイされ、本番でも動作する

Phase 2完了後、Phase 3（求人サイト）に進む。
