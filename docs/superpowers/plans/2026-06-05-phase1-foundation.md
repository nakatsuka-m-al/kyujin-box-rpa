# Phase 1: 基盤構築 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pnpmモノレポ + Supabase DB + 共通パッケージ（ui/db/ai）を構築し、3サイトの土台を作る

**Architecture:** pnpm workspacesでモノレポを管理。`packages/db`がSupabaseクライアントと型定義を提供し、`packages/ai`がClaude API記事生成ラッパーを提供する。`packages/ui`が全サイト共通コンポーネントを持つ。

**Tech Stack:** Next.js 15, pnpm workspaces, Tailwind v4, Supabase, Claude API (claude-sonnet-4-6), @phosphor-icons/react, TypeScript

---

## File Structure

```
/
├── package.json
├── pnpm-workspace.yaml
├── turbo.json
├── .env.example
├── apps/
│   ├── admin/             # Phase 2で構築
│   ├── career-stories/    # Phase 3で構築
│   ├── salary-data/       # Phase 3で構築
│   └── career-tips/       # Phase 3で構築
└── packages/
    ├── ui/
    │   └── src/
    │       ├── index.ts
    │       ├── components/
    │       │   ├── Button.tsx
    │       │   └── ArticleCard.tsx
    │       └── styles/globals.css
    ├── db/
    │   └── src/
    │       ├── index.ts
    │       ├── client.ts
    │       ├── types.ts
    │       └── queries/articles.ts
    └── ai/
        └── src/
            ├── index.ts
            ├── client.ts
            └── generate-article.ts
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

Expected: バージョン番号（9.x.x等）。なければ `npm install -g pnpm`

- [ ] **Step 2: 新規ディレクトリを作成してgit初期化**

```bash
mkdir ~/Desktop/recruitment-media
cd ~/Desktop/recruitment-media
git init
```

- [ ] **Step 3: ルートpackage.jsonを作成**

```json
{
  "name": "recruitment-media",
  "private": true,
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "typecheck": "turbo run typecheck"
  },
  "devDependencies": {
    "turbo": "^2.0.0",
    "typescript": "^5.5.0",
    "@types/node": "^20.0.0"
  }
}
```

- [ ] **Step 4: pnpm-workspace.yamlを作成**

```yaml
packages:
  - 'apps/*'
  - 'packages/*'
```

- [ ] **Step 5: turbo.jsonを作成**

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
    "typecheck": {
      "dependsOn": ["^build"]
    }
  }
}
```

- [ ] **Step 6: .env.exampleを作成**

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Claude API
ANTHROPIC_API_KEY=

# cron認証
CRON_SECRET=
```

- [ ] **Step 7: ディレクトリ構造を作成**

```bash
mkdir -p apps/{admin,career-stories,salary-data,career-tips}
mkdir -p packages/{ui,db,ai}
```

- [ ] **Step 8: 依存関係インストール**

```bash
pnpm install
```

- [ ] **Step 9: コミット**

```bash
git add .
git commit -m "chore: モノレポ初期化"
```

---

### Task 2: Supabaseスキーマ定義

**Files:**
- Create: `supabase/migrations/001_initial_schema.sql`

- [ ] **Step 1: supabaseディレクトリを作成**

```bash
mkdir -p supabase/migrations
```

- [ ] **Step 2: マイグレーションSQLを作成**

`supabase/migrations/001_initial_schema.sql`:

```sql
CREATE TYPE site_id AS ENUM (
  'career-stories',
  'salary-data',
  'career-tips'
);

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

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER articles_updated_at
  BEFORE UPDATE ON articles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE INDEX articles_site_id_published ON articles (site_id, is_published, published_at DESC);

ALTER TABLE articles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "articles_public_read" ON articles
  FOR SELECT USING (is_published = true);

CREATE POLICY "articles_service_all" ON articles
  FOR ALL USING (auth.role() = 'service_role');
```

- [ ] **Step 3: SupabaseダッシュボードでSQLを実行**

Supabase → SQL Editor → 上記SQLを貼り付けて実行

- [ ] **Step 4: テーブルが作成されたことを確認**

Supabase → Table Editor → `articles` テーブルが存在することを確認

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
- Create: `packages/db/src/types.ts`
- Create: `packages/db/src/client.ts`
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
export type SiteId = 'career-stories' | 'salary-data' | 'career-tips'

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

- [ ] **Step 5: 記事クエリを作成**

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
    query = query.range(
      options.offset,
      options.offset + (options.limit ?? 20) - 1
    )
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

- [ ] **Step 6: index.tsを作成**

`packages/db/src/index.ts`:

```typescript
export * from './client'
export * from './types'
export * from './queries/articles'
```

- [ ] **Step 7: 型チェック**

```bash
cd packages/db && pnpm install && pnpm typecheck
```

Expected: エラーなし

- [ ] **Step 8: コミット**

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
- Create: `packages/ai/src/generate-article.ts`
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

- [ ] **Step 4: 記事生成ロジックを作成**

`packages/ai/src/generate-article.ts`:

```typescript
import type { SiteId } from '@recruitment/db'
import { getAnthropicClient } from './client'

export type GenerateArticleInput = {
  siteId: SiteId
  title: string
  keywords: string[]
}

export type GeneratedArticle = {
  title: string
  content: string
  excerpt: string
  slug: string
}

const SITE_PROMPTS: Record<SiteId, string> = {
  'career-stories': `あなたは転職体験談を書く専門ライターです。
20代・30代のリアルな転職体験談・エピソードを一人称で書いてください。
実際に経験した人が書いたような具体的なエピソードを含め、800〜1200文字で書いてください。
段落は空行で区切り、タイトルや見出し記号は使わず本文のみ出力してください。`,

  'salary-data': `あなたは転職・キャリアの給与データを解説する専門ライターです。
職種・業界の年収相場、年収アップの方法について、具体的なデータや数字を交えながら
わかりやすく800〜1200文字で解説してください。
段落は空行で区切り、タイトルや見出し記号は使わず本文のみ出力してください。`,

  'career-tips': `あなたは転職ノウハウを解説する専門ライターです。
転職活動の実践的なテクニック・ノウハウを、具体的なステップや例を交えながら
800〜1200文字で解説してください。
段落は空行で区切り、タイトルや見出し記号は使わず本文のみ出力してください。`,
}

function toSlug(title: string, siteId: SiteId): string {
  const timestamp = Date.now()
  const random = Math.random().toString(36).slice(2, 6)
  return `${siteId}-${timestamp}-${random}`
}

export async function generateArticle(
  input: GenerateArticleInput
): Promise<GeneratedArticle> {
  const client = getAnthropicClient()

  const message = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 2048,
    system: SITE_PROMPTS[input.siteId],
    messages: [
      {
        role: 'user',
        content: `次のタイトルで記事を書いてください: ${input.title}\nキーワード: ${input.keywords.join(', ')}`,
      },
    ],
  })

  const content = message.content[0]
  if (content.type !== 'text') throw new Error('AI応答が不正です')

  const excerpt = content.text.slice(0, 120).replace(/\n/g, '') + '...'
  const slug = toSlug(input.title, input.siteId)

  return {
    title: input.title,
    content: content.text,
    excerpt,
    slug,
  }
}
```

- [ ] **Step 5: index.tsを作成**

`packages/ai/src/index.ts`:

```typescript
export * from './client'
export * from './generate-article'
```

- [ ] **Step 6: 型チェック**

```bash
cd packages/ai && pnpm install && pnpm typecheck
```

Expected: エラーなし

- [ ] **Step 7: コミット**

```bash
git add packages/ai/
git commit -m "feat: packages/ai - 記事生成AIラッパー"
```

---

### Task 5: packages/ui 構築

**Files:**
- Create: `packages/ui/package.json`
- Create: `packages/ui/tsconfig.json`
- Create: `packages/ui/src/components/ArticleCard.tsx`
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
    "react": "^19.0.0"
  },
  "dependencies": {
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

- [ ] **Step 3: ArticleCardコンポーネントを作成**

`packages/ui/src/components/ArticleCard.tsx`:

```tsx
import type { Article } from '@recruitment/db'

type ArticleCardProps = {
  article: Article
  href: string
  accentColor?: string
}

export function ArticleCard({ article, href, accentColor = '#1d4ed8' }: ArticleCardProps) {
  return (
    <a href={href} className="block group">
      <article className="border-b border-gray-100 pb-5">
        <h2 className="text-base font-semibold text-gray-900 leading-snug group-hover:underline">
          {article.title}
        </h2>
        {article.excerpt && (
          <p className="mt-1 text-sm text-gray-500 leading-relaxed line-clamp-2">
            {article.excerpt}
          </p>
        )}
        <p className="mt-1.5 text-xs text-gray-400">
          {article.published_at
            ? new Date(article.published_at).toLocaleDateString('ja-JP')
            : ''}
        </p>
      </article>
    </a>
  )
}
```

- [ ] **Step 4: index.tsを作成**

`packages/ui/src/index.ts`:

```typescript
export { ArticleCard } from './components/ArticleCard'
```

- [ ] **Step 5: 型チェック**

```bash
cd packages/ui && pnpm install && pnpm typecheck
```

Expected: エラーなし

- [ ] **Step 6: コミット**

```bash
git add packages/ui/
git commit -m "feat: packages/ui - ArticleCard共通コンポーネント"
git push
```

---

## Phase 1 完了チェックリスト

- [ ] pnpmモノレポが正常に動作する（`pnpm install` がエラーなし）
- [ ] Supabaseに `articles` テーブルが作成されている
- [ ] `packages/db` の型チェックが通る
- [ ] `packages/ai` の型チェックが通る
- [ ] `packages/ui` の型チェックが通る
- [ ] GitHubリポジトリにpush済み

Phase 1完了後、Phase 2（管理画面 + 記事生成API + cron）に進む。
