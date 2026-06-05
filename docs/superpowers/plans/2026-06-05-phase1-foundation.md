# Phase 1: 基盤構築 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pnpmモノレポ + Supabase DB + 共通パッケージ（ui/db/ai）を構築し、全サイトの土台を作る

**Architecture:** pnpm workspacesでモノレポを管理。`packages/db`がSupabaseクライアントと型定義を提供し、`packages/ai`がClaude APIラッパーを提供する。`packages/ui`が全サイト共通のコンポーネントを持つ。

**Tech Stack:** Next.js 15, pnpm workspaces, Tailwind v4, Supabase, Claude API (claude-sonnet-4-6), @phosphor-icons/react, motion/react, TypeScript

---

## File Structure

```
/
├── package.json                    # pnpm workspace root
├── pnpm-workspace.yaml
├── turbo.json                      # Turborepo設定
├── .env.example
├── apps/
│   ├── admin/                      # Phase 2で構築
│   ├── jobs-main/                  # Phase 3で構築
│   ├── jobs-region/                # Phase 3で構築
│   ├── media-career/               # Phase 4で構築
│   ├── salary-data/                # Phase 4で構築
│   └── agent-compare/              # Phase 4で構築
└── packages/
    ├── ui/
    │   ├── package.json
    │   ├── tsconfig.json
    │   └── src/
    │       ├── index.ts
    │       ├── components/
    │       │   ├── JobCard.tsx
    │       │   ├── Button.tsx
    │       │   └── Badge.tsx
    │       └── styles/
    │           └── globals.css
    ├── db/
    │   ├── package.json
    │   ├── tsconfig.json
    │   └── src/
    │       ├── index.ts
    │       ├── client.ts
    │       ├── types.ts           # DBの型定義
    │       └── queries/
    │           ├── jobs.ts
    │           └── articles.ts
    └── ai/
        ├── package.json
        ├── tsconfig.json
        └── src/
            ├── index.ts
            ├── client.ts
            └── parse-csv.ts       # CSV解析ロジック
```

---

### Task 1: モノレポ初期化

**Files:**
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `turbo.json`
- Create: `.env.example`

- [ ] **Step 1: pnpmがインストールされているか確認**

```bash
pnpm --version
```

Expected: バージョン番号（例: 9.x.x）。入っていなければ `npm install -g pnpm`

- [ ] **Step 2: ルートpackage.jsonを作成**

新規プロジェクト用ディレクトリを作成（このリポジトリとは別）:

```bash
mkdir ~/Desktop/recruitment-media
cd ~/Desktop/recruitment-media
git init
```

`package.json` を作成:

```json
{
  "name": "recruitment-media",
  "private": true,
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "lint": "turbo run lint",
    "typecheck": "turbo run typecheck"
  },
  "devDependencies": {
    "turbo": "^2.0.0",
    "typescript": "^5.5.0",
    "@types/node": "^20.0.0"
  }
}
```

- [ ] **Step 3: pnpm-workspace.yamlを作成**

```yaml
packages:
  - 'apps/*'
  - 'packages/*'
```

- [ ] **Step 4: turbo.jsonを作成**

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "!.next/cache/**", "dist/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "lint": {},
    "typecheck": {
      "dependsOn": ["^build"]
    }
  }
}
```

- [ ] **Step 5: .env.exampleを作成**

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Claude API
ANTHROPIC_API_KEY=

# Site識別
NEXT_PUBLIC_SITE_ID=
```

- [ ] **Step 6: ディレクトリ構造を作成**

```bash
mkdir -p apps/{admin,jobs-main,jobs-region,media-career,salary-data,agent-compare}
mkdir -p packages/{ui,db,ai}
```

- [ ] **Step 7: 依存関係インストール**

```bash
pnpm install
```

- [ ] **Step 8: コミット**

```bash
git add .
git commit -m "chore: モノレポ初期化"
```

---

### Task 2: Supabaseスキーマ定義

**Files:**
- Create: `supabase/migrations/001_initial_schema.sql`
- Create: `supabase/seed.sql`

- [ ] **Step 1: supabaseディレクトリ作成**

```bash
mkdir -p supabase/migrations
```

- [ ] **Step 2: 初期マイグレーションを作成**

`supabase/migrations/001_initial_schema.sql`:

```sql
-- site_idの列挙型
CREATE TYPE site_id AS ENUM (
  'jobs-main',
  'jobs-region',
  'media-career',
  'salary-data',
  'agent-compare'
);

-- 求人テーブル
CREATE TABLE jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id site_id NOT NULL DEFAULT 'jobs-main',
  title TEXT NOT NULL,
  description TEXT,
  salary TEXT,
  salary_min INTEGER,
  salary_max INTEGER,
  location TEXT,
  prefecture TEXT,
  employment_type TEXT,
  company_name TEXT,
  apply_url TEXT NOT NULL,
  is_published BOOLEAN NOT NULL DEFAULT false,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 記事テーブル
CREATE TABLE articles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id site_id NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  excerpt TEXT,
  slug TEXT NOT NULL,
  is_published BOOLEAN NOT NULL DEFAULT false,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (site_id, slug)
);

-- CSVインポート履歴
CREATE TABLE csv_imports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  filename TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- updated_atの自動更新トリガー
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER jobs_updated_at
  BEFORE UPDATE ON jobs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER articles_updated_at
  BEFORE UPDATE ON articles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- インデックス
CREATE INDEX jobs_site_id_published ON jobs (site_id, is_published);
CREATE INDEX jobs_prefecture ON jobs (prefecture);
CREATE INDEX articles_site_id_slug ON articles (site_id, slug);

-- RLS有効化
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE csv_imports ENABLE ROW LEVEL SECURITY;

-- 公開データは誰でも読める
CREATE POLICY "jobs_public_read" ON jobs
  FOR SELECT USING (is_published = true);

CREATE POLICY "articles_public_read" ON articles
  FOR SELECT USING (is_published = true);

-- service_roleは全操作可能（管理画面用）
CREATE POLICY "jobs_service_all" ON jobs
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "articles_service_all" ON articles
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "csv_imports_service_all" ON csv_imports
  FOR ALL USING (auth.role() = 'service_role');
```

- [ ] **Step 3: SupabaseダッシュボードでSQLを実行**

Supabaseダッシュボード → SQL Editor → 上記SQLを貼り付けて実行

- [ ] **Step 4: 実行結果を確認**

Supabase → Table Editor で `jobs`, `articles`, `csv_imports` テーブルが作成されていることを確認

- [ ] **Step 5: コミット**

```bash
git add supabase/
git commit -m "feat: Supabaseスキーマ定義"
```

---

### Task 3: packages/db 構築

**Files:**
- Create: `packages/db/package.json`
- Create: `packages/db/tsconfig.json`
- Create: `packages/db/src/client.ts`
- Create: `packages/db/src/types.ts`
- Create: `packages/db/src/queries/jobs.ts`
- Create: `packages/db/src/queries/articles.ts`
- Create: `packages/db/src/index.ts`

- [ ] **Step 1: package.jsonを作成**

`packages/db/package.json`:

```json
{
  "name": "@recruitment/db",
  "version": "0.0.1",
  "private": true,
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "scripts": {
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@supabase/supabase-js": "^2.45.0"
  },
  "devDependencies": {
    "typescript": "^5.5.0"
  }
}
```

- [ ] **Step 2: tsconfig.jsonを作成**

`packages/db/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "skipLibCheck": true
  }
}
```

- [ ] **Step 3: 型定義を作成**

`packages/db/src/types.ts`:

```typescript
export type SiteId =
  | 'jobs-main'
  | 'jobs-region'
  | 'media-career'
  | 'salary-data'
  | 'agent-compare'

export type Job = {
  id: string
  site_id: SiteId
  title: string
  description: string | null
  salary: string | null
  salary_min: number | null
  salary_max: number | null
  location: string | null
  prefecture: string | null
  employment_type: string | null
  company_name: string | null
  apply_url: string
  is_published: boolean
  published_at: string | null
  created_at: string
  updated_at: string
}

export type Article = {
  id: string
  site_id: SiteId
  title: string
  content: string
  excerpt: string | null
  slug: string
  is_published: boolean
  published_at: string | null
  created_at: string
  updated_at: string
}

export type CsvImport = {
  id: string
  filename: string
  row_count: number
  success_count: number
  error_count: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
}

export type JobInsert = Omit<Job, 'id' | 'created_at' | 'updated_at'>
export type ArticleInsert = Omit<Article, 'id' | 'created_at' | 'updated_at'>
```

- [ ] **Step 4: Supabaseクライアントを作成**

`packages/db/src/client.ts`:

```typescript
import { createClient } from '@supabase/supabase-js'

export function createPublicClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!url || !key) throw new Error('Supabase env vars not set')
  return createClient(url, key)
}

export function createServiceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!url || !key) throw new Error('Supabase service role env vars not set')
  return createClient(url, key)
}
```

- [ ] **Step 5: 求人クエリを作成**

`packages/db/src/queries/jobs.ts`:

```typescript
import type { SupabaseClient } from '@supabase/supabase-js'
import type { Job, JobInsert, SiteId } from '../types'

export async function getPublishedJobs(
  client: SupabaseClient,
  siteId: SiteId,
  options?: { prefecture?: string; limit?: number; offset?: number }
): Promise<Job[]> {
  let query = client
    .from('jobs')
    .select('*')
    .eq('site_id', siteId)
    .eq('is_published', true)
    .order('published_at', { ascending: false })

  if (options?.prefecture) {
    query = query.eq('prefecture', options.prefecture)
  }
  if (options?.limit) {
    query = query.limit(options.limit)
  }
  if (options?.offset) {
    query = query.range(options.offset, options.offset + (options.limit ?? 20) - 1)
  }

  const { data, error } = await query
  if (error) throw error
  return data ?? []
}

export async function getJobById(
  client: SupabaseClient,
  id: string
): Promise<Job | null> {
  const { data, error } = await client
    .from('jobs')
    .select('*')
    .eq('id', id)
    .single()
  if (error) return null
  return data
}

export async function insertJobs(
  client: SupabaseClient,
  jobs: JobInsert[]
): Promise<Job[]> {
  const { data, error } = await client
    .from('jobs')
    .insert(jobs)
    .select()
  if (error) throw error
  return data ?? []
}

export async function publishJobs(
  client: SupabaseClient,
  ids: string[]
): Promise<void> {
  const { error } = await client
    .from('jobs')
    .update({ is_published: true, published_at: new Date().toISOString() })
    .in('id', ids)
  if (error) throw error
}
```

- [ ] **Step 6: 記事クエリを作成**

`packages/db/src/queries/articles.ts`:

```typescript
import type { SupabaseClient } from '@supabase/supabase-js'
import type { Article, ArticleInsert, SiteId } from '../types'

export async function getPublishedArticles(
  client: SupabaseClient,
  siteId: SiteId,
  options?: { limit?: number; offset?: number }
): Promise<Article[]> {
  let query = client
    .from('articles')
    .select('*')
    .eq('site_id', siteId)
    .eq('is_published', true)
    .order('published_at', { ascending: false })

  if (options?.limit) query = query.limit(options.limit)
  if (options?.offset) {
    query = query.range(options.offset, options.offset + (options.limit ?? 20) - 1)
  }

  const { data, error } = await query
  if (error) throw error
  return data ?? []
}

export async function getArticleBySlug(
  client: SupabaseClient,
  siteId: SiteId,
  slug: string
): Promise<Article | null> {
  const { data, error } = await client
    .from('articles')
    .select('*')
    .eq('site_id', siteId)
    .eq('slug', slug)
    .single()
  if (error) return null
  return data
}

export async function insertArticle(
  client: SupabaseClient,
  article: ArticleInsert
): Promise<Article> {
  const { data, error } = await client
    .from('articles')
    .insert(article)
    .select()
    .single()
  if (error) throw error
  return data
}
```

- [ ] **Step 7: index.tsでエクスポート**

`packages/db/src/index.ts`:

```typescript
export * from './client'
export * from './types'
export * from './queries/jobs'
export * from './queries/articles'
```

- [ ] **Step 8: 依存関係インストール**

```bash
pnpm install
```

- [ ] **Step 9: 型チェック**

```bash
cd packages/db && pnpm typecheck
```

Expected: エラーなし

- [ ] **Step 10: コミット**

```bash
git add packages/db/
git commit -m "feat: packages/db - Supabaseクライアントと型定義"
```

---

### Task 4: packages/ai 構築

**Files:**
- Create: `packages/ai/package.json`
- Create: `packages/ai/tsconfig.json`
- Create: `packages/ai/src/client.ts`
- Create: `packages/ai/src/parse-csv.ts`
- Create: `packages/ai/src/index.ts`

- [ ] **Step 1: package.jsonを作成**

`packages/ai/package.json`:

```json
{
  "name": "@recruitment/ai",
  "version": "0.0.1",
  "private": true,
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "scripts": {
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@anthropic-ai/sdk": "^0.30.0"
  },
  "devDependencies": {
    "typescript": "^5.5.0"
  }
}
```

- [ ] **Step 2: tsconfig.jsonを作成**

`packages/ai/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "skipLibCheck": true
  }
}
```

- [ ] **Step 3: Claudeクライアントを作成**

`packages/ai/src/client.ts`:

```typescript
import Anthropic from '@anthropic-ai/sdk'

let _client: Anthropic | null = null

export function getAnthropicClient(): Anthropic {
  if (!_client) {
    const apiKey = process.env.ANTHROPIC_API_KEY
    if (!apiKey) throw new Error('ANTHROPIC_API_KEY not set')
    _client = new Anthropic({ apiKey })
  }
  return _client
}
```

- [ ] **Step 4: CSV解析ロジックを作成**

`packages/ai/src/parse-csv.ts`:

```typescript
import type { JobInsert, SiteId } from '@recruitment/db'
import { getAnthropicClient } from './client'

export type CsvParseResult = {
  jobs: Omit<JobInsert, 'site_id'>[]
  errors: string[]
}

export async function parseCsvWithAI(
  csvText: string,
  siteId: SiteId
): Promise<CsvParseResult> {
  const client = getAnthropicClient()

  const message = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 4096,
    system: `あなたはCSVデータを求人情報に変換するエキスパートです。
CSVのヘッダーと内容を解析し、各行を求人情報のJSONに変換してください。

出力形式（JSON配列）:
[
  {
    "title": "職種名",
    "description": "仕事内容",
    "salary": "給与の文字列表現（例: 月給25万〜35万円）",
    "salary_min": 250000,
    "salary_max": 350000,
    "location": "勤務地の完全な住所または地域名",
    "prefecture": "都道府県名のみ（例: 東京都）",
    "employment_type": "雇用形態（正社員/契約社員/パート/アルバイト/派遣）",
    "company_name": "会社名",
    "apply_url": "応募URL",
    "is_published": false
  }
]

ルール:
- apply_urlが見つからない行はエラーとしてスキップ
- salary_minとsalary_maxは月額円換算の整数（不明な場合はnull）
- prefectureは「東京都」「大阪府」「神奈川県」など標準的な表記
- JSONのみ返す（説明文は不要）`,
    messages: [
      {
        role: 'user',
        content: `以下のCSVを求人情報に変換してください:\n\n${csvText}`,
      },
    ],
  })

  const content = message.content[0]
  if (content.type !== 'text') {
    return { jobs: [], errors: ['AI応答が不正です'] }
  }

  try {
    const parsed = JSON.parse(content.text)
    if (!Array.isArray(parsed)) {
      return { jobs: [], errors: ['AI応答がJSON配列ではありません'] }
    }

    const jobs: Omit<JobInsert, 'site_id'>[] = []
    const errors: string[] = []

    for (const item of parsed) {
      if (!item.apply_url) {
        errors.push(`スキップ: apply_urlなし - ${item.title ?? '不明'}`)
        continue
      }
      jobs.push({
        title: item.title ?? '(タイトルなし)',
        description: item.description ?? null,
        salary: item.salary ?? null,
        salary_min: item.salary_min ?? null,
        salary_max: item.salary_max ?? null,
        location: item.location ?? null,
        prefecture: item.prefecture ?? null,
        employment_type: item.employment_type ?? null,
        company_name: item.company_name ?? null,
        apply_url: item.apply_url,
        is_published: false,
        published_at: null,
      })
    }

    return { jobs, errors }
  } catch {
    return { jobs: [], errors: [`JSONパースエラー: ${content.text.slice(0, 200)}`] }
  }
}
```

- [ ] **Step 5: index.tsでエクスポート**

`packages/ai/src/index.ts`:

```typescript
export * from './client'
export * from './parse-csv'
```

- [ ] **Step 6: 依存関係インストール**

```bash
pnpm install
```

- [ ] **Step 7: 型チェック**

```bash
cd packages/ai && pnpm typecheck
```

Expected: エラーなし

- [ ] **Step 8: コミット**

```bash
git add packages/ai/
git commit -m "feat: packages/ai - CSV解析AIラッパー"
```

---

### Task 5: packages/ui 構築

**Files:**
- Create: `packages/ui/package.json`
- Create: `packages/ui/tsconfig.json`
- Create: `packages/ui/src/components/Button.tsx`
- Create: `packages/ui/src/components/Badge.tsx`
- Create: `packages/ui/src/components/JobCard.tsx`
- Create: `packages/ui/src/index.ts`

- [ ] **Step 1: package.jsonを作成**

`packages/ui/package.json`:

```json
{
  "name": "@recruitment/ui",
  "version": "0.0.1",
  "private": true,
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "scripts": {
    "typecheck": "tsc --noEmit"
  },
  "peerDependencies": {
    "react": "^19.0.0",
    "next": "^15.0.0"
  },
  "dependencies": {
    "@phosphor-icons/react": "^2.1.0",
    "motion": "^11.0.0",
    "clsx": "^2.1.0"
  },
  "devDependencies": {
    "typescript": "^5.5.0",
    "@types/react": "^19.0.0"
  }
}
```

- [ ] **Step 2: tsconfig.jsonを作成**

`packages/ui/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true
  }
}
```

- [ ] **Step 3: Buttonコンポーネントを作成**

`packages/ui/src/components/Button.tsx`:

```tsx
import clsx from 'clsx'
import type { ButtonHTMLAttributes } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
}

export function Button({
  variant = 'primary',
  size = 'md',
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center font-medium rounded-lg transition-all active:scale-[0.98]',
        {
          'bg-navy-900 text-white hover:bg-navy-800': variant === 'primary',
          'border border-navy-200 text-navy-900 hover:bg-navy-50': variant === 'secondary',
          'text-navy-600 hover:text-navy-900 hover:bg-navy-50': variant === 'ghost',
        },
        {
          'text-sm px-3 py-1.5': size === 'sm',
          'text-sm px-4 py-2': size === 'md',
          'text-base px-6 py-3': size === 'lg',
        },
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
}
```

- [ ] **Step 4: Badgeコンポーネントを作成**

`packages/ui/src/components/Badge.tsx`:

```tsx
import clsx from 'clsx'

type BadgeProps = {
  children: React.ReactNode
  variant?: 'default' | 'green' | 'blue' | 'orange'
  className?: string
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full',
        {
          'bg-gray-100 text-gray-700': variant === 'default',
          'bg-green-100 text-green-700': variant === 'green',
          'bg-blue-100 text-blue-700': variant === 'blue',
          'bg-orange-100 text-orange-700': variant === 'orange',
        },
        className
      )}
    >
      {children}
    </span>
  )
}
```

- [ ] **Step 5: JobCardコンポーネントを作成**

`packages/ui/src/components/JobCard.tsx`:

```tsx
import { MapPin, CurrencyJpy, Briefcase } from '@phosphor-icons/react'
import { Badge } from './Badge'
import type { Job } from '@recruitment/db'

type JobCardProps = {
  job: Job
  href: string
}

export function JobCard({ job, href }: JobCardProps) {
  return (
    <a
      href={href}
      className="block p-5 bg-white border border-gray-200 rounded-xl hover:border-navy-300 hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-semibold text-gray-900 leading-snug">
          {job.title}
        </h3>
        {job.employment_type && (
          <Badge variant="blue" className="shrink-0">
            {job.employment_type}
          </Badge>
        )}
      </div>

      {job.company_name && (
        <p className="mt-1 text-sm text-gray-500">{job.company_name}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-3 text-sm text-gray-600">
        {job.location && (
          <span className="flex items-center gap-1">
            <MapPin size={14} weight="bold" />
            {job.location}
          </span>
        )}
        {job.salary && (
          <span className="flex items-center gap-1">
            <CurrencyJpy size={14} weight="bold" />
            {job.salary}
          </span>
        )}
      </div>
    </a>
  )
}
```

- [ ] **Step 6: index.tsでエクスポート**

`packages/ui/src/index.ts`:

```typescript
export { Button } from './components/Button'
export { Badge } from './components/Badge'
export { JobCard } from './components/JobCard'
```

- [ ] **Step 7: 型チェック**

```bash
cd packages/ui && pnpm typecheck
```

Expected: エラーなし

- [ ] **Step 8: コミット**

```bash
git add packages/ui/
git commit -m "feat: packages/ui - 共通UIコンポーネント"
```

---

### Task 6: Vercel設定

**Files:**
- Create: `vercel.json`（ルート）
- Create: `apps/jobs-main/vercel.json`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: ルートのvercel.jsonを作成**

```json
{
  "git": {
    "deploymentEnabled": {
      "main": true
    }
  }
}
```

- [ ] **Step 2: Vercel CLIでプロジェクトをリンク（jobs-mainを例に）**

```bash
cd apps/jobs-main
npx vercel link
```

各appをVercelダッシュボードで別プロジェクトとして作成し、それぞれ `apps/<appname>` をRoot Directoryに設定する。

- [ ] **Step 3: 環境変数をVercelに設定**

Vercelダッシュボード → 各プロジェクト → Settings → Environment Variables で以下を設定:

```
NEXT_PUBLIC_SUPABASE_URL      = （SupabaseダッシュボードのURL）
NEXT_PUBLIC_SUPABASE_ANON_KEY = （SupabaseダッシュボードのAnon Key）
SUPABASE_SERVICE_ROLE_KEY     = （SupabaseダッシュボードのService Role Key）
ANTHROPIC_API_KEY             = （Anthropicコンソールのキー）
NEXT_PUBLIC_SITE_ID           = （各サイトに対応する値）
```

NEXT_PUBLIC_SITE_IDの値:
- jobs-main → `jobs-main`
- jobs-region → `jobs-region`
- media-career → `media-career`
- salary-data → `salary-data`
- agent-compare → `agent-compare`
- admin → （設定不要）

- [ ] **Step 4: GitHubリポジトリを作成してpush**

```bash
gh repo create recruitment-media --private
git remote add origin git@github.com:<username>/recruitment-media.git
git push -u origin main
```

- [ ] **Step 5: コミット**

```bash
git add vercel.json
git commit -m "chore: Vercel設定追加"
git push
```

---

## Phase 1 完了チェックリスト

- [ ] pnpmモノレポが正常に動作する
- [ ] Supabaseに `jobs`, `articles`, `csv_imports` テーブルが作成されている
- [ ] `packages/db` の型チェックが通る
- [ ] `packages/ai` の型チェックが通る
- [ ] `packages/ui` の型チェックが通る
- [ ] GitHubリポジトリにpush済み
- [ ] Vercel環境変数が設定済み

Phase 1完了後、Phase 2（管理画面）に進む。
