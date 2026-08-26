# D1 Large-Text Compression and R2 Offload Pattern

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

D1 rows that store large text blobs — rich-text article bodies, LLM-generated summaries,
HTML email templates, serialized markdown documents — inflate the D1 database file, slow
down full-table scans, and push storage toward D1's 10 GB per-database limit. You need to
store large text efficiently while keeping metadata queryable in D1.

## Context

Cloudflare D1 does not perform column-level compression. SQLite stores `TEXT` and `BLOB`
columns inline in the B-tree leaf pages. Large values (>= ~8 KB in default SQLite page
size 4096) spill to overflow pages but are still stored within the database file. The
correct strategy is to:

1. Store text content in **Cloudflare R2** (object storage, gzip-compressed).
2. Store only a **content pointer** (R2 key + uncompressed size + content hash) in D1.
3. Compress in the Worker using the `CompressionStream` API (available in the Workers
   runtime without any imports).
4. Decompress on read in a streaming Worker response.

This pattern reduces D1 storage 3–8× for prose text and is transparent to the application.

---

## Schema Design

```sql
-- D1: store metadata and pointer only — no large text inline
CREATE TABLE articles (
  id              TEXT PRIMARY KEY,
  tenant_id       TEXT NOT NULL,
  title           TEXT NOT NULL,
  slug            TEXT NOT NULL,
  author_id       TEXT NOT NULL,
  -- Content pointer
  content_r2_key  TEXT,            -- NULL if content is small enough to inline
  content_inline  TEXT,            -- used only for short content (< 2 KB threshold)
  content_hash    TEXT NOT NULL,   -- SHA-256 hex for cache invalidation
  content_size    INTEGER NOT NULL, -- uncompressed byte length
  -- Full-text search metadata (indexed, fast)
  excerpt         TEXT,            -- first ~300 chars, stored inline for preview
  word_count      INTEGER,
  published_at    INTEGER,
  updated_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_articles_tenant_pub  ON articles(tenant_id, published_at DESC);
CREATE INDEX idx_articles_slug        ON articles(tenant_id, slug);
CREATE INDEX idx_articles_author      ON articles(tenant_id, author_id, published_at DESC);
```

---

## Compression Utilities (Workers Runtime)

```typescript
// src/lib/compress.ts
// CompressionStream and DecompressionStream are available in Workers runtime natively

export async function gzipText(text: string): Promise<Uint8Array> {
  const encoder = new TextEncoder();
  const input = encoder.encode(text);
  const cs = new CompressionStream('gzip');
  const writer = cs.writable.getWriter();
  writer.write(input);
  writer.close();
  return new Uint8Array(await new Response(cs.readable).arrayBuffer());
}

export async function gunzipBytes(compressed: Uint8Array): Promise<string> {
  const ds = new DecompressionStream('gzip');
  const writer = ds.writable.getWriter();
  writer.write(compressed);
  writer.close();
  const bytes = await new Response(ds.readable).arrayBuffer();
  return new TextDecoder().decode(bytes);
}

export async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Write Path: Compress and Offload to R2

```typescript
// src/services/article-service.ts
import { D1Database, R2Bucket } from '@cloudflare/workers-types';
import { gzipText, sha256Hex } from '../lib/compress';

interface Env { DB: D1Database; CONTENT_BUCKET: R2Bucket }

const INLINE_THRESHOLD = 2048; // bytes: store inline if shorter

export async function saveArticle(
  env: Env,
  article: {
    id: string;
    tenantId: string;
    title: string;
    slug: string;
    authorId: string;
    content: string;
  },
): Promise<void> {
  const { id, tenantId, title, slug, authorId, content } = article;
  const hash = await sha256Hex(content);
  const size = new TextEncoder().encode(content).byteLength;
  const excerpt = content.replace(/\s+/g, ' ').slice(0, 300);
  const wordCount = content.split(/\s+/).filter(Boolean).length;

  let contentR2Key: string | null = null;
  let contentInline: string | null = null;

  if (size <= INLINE_THRESHOLD) {
    contentInline = content;
  } else {
    // Compress and write to R2
    const compressed = await gzipText(content);
    contentR2Key = `articles/${tenantId}/${id}.gz`;
    await env.CONTENT_BUCKET.put(contentR2Key, compressed, {
      httpMetadata: { contentType: 'text/plain; charset=utf-8', contentEncoding: 'gzip' },
      customMetadata: { uncompressed_size: String(size), sha256: hash },
    });
  }

  await env.DB.prepare(
    `INSERT INTO articles
       (id, tenant_id, title, slug, author_id, content_r2_key, content_inline,
        content_hash, content_size, excerpt, word_count)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)
     ON CONFLICT (id) DO UPDATE SET
       title = excluded.title, slug = excluded.slug,
       content_r2_key = excluded.content_r2_key,
       content_inline = excluded.content_inline,
       content_hash = excluded.content_hash, content_size = excluded.content_size,
       excerpt = excluded.excerpt, word_count = excluded.word_count,
       updated_at = unixepoch()`,
  )
    .bind(id, tenantId, title, slug, authorId, contentR2Key, contentInline,
      hash, size, excerpt, wordCount)
    .run();
}
```

---

## Read Path: Fetch and Decompress

```typescript
// src/services/article-service.ts (continued)
import { gunzipBytes } from '../lib/compress';

interface ArticleRow {
  id: string; title: string; slug: string; content_r2_key: string | null;
  content_inline: string | null; content_hash: string; content_size: number;
  excerpt: string; word_count: number;
}

export async function getArticleContent(
  env: Env,
  articleId: string,
): Promise<{ meta: ArticleRow; content: string } | null> {
  const row = await env.DB
    .prepare(`SELECT * FROM articles WHERE id = ?`)
    .bind(articleId)
    .first<ArticleRow>();

  if (!row) return null;

  let content: string;

  if (row.content_inline !== null) {
    content = row.content_inline;
  } else if (row.content_r2_key) {
    const obj = await env.CONTENT_BUCKET.get(row.content_r2_key);
    if (!obj) throw new Error(`R2 object missing: ${row.content_r2_key}`);
    const bytes = new Uint8Array(await obj.arrayBuffer());
    content = await gunzipBytes(bytes);
  } else {
    throw new Error(`Article ${articleId} has no content pointer`);
  }

  return { meta: row, content };
}

// Streaming response for large articles
export async function streamArticleContent(
  env: Env,
  r2Key: string,
): Promise<Response> {
  const obj = await env.CONTENT_BUCKET.get(r2Key);
  if (!obj) return new Response('Not found', { status: 404 });
  // R2 returns the compressed bytes; decompress via DecompressionStream
  const ds = new DecompressionStream('gzip');
  obj.body.pipeTo(ds.writable);
  return new Response(ds.readable, {
    headers: { 'content-type': 'text/plain; charset=utf-8' },
  });
}
```

---

## Anti-patterns

- **Storing large text in D1 with no size guard**: Without a threshold check, a single 5 MB
  article body inflates the D1 database file significantly and causes slow full-table scans
  on the articles table.
- **Reading R2 objects synchronously for list/search endpoints**: List endpoints should query
  D1 metadata (title, excerpt, word_count) only. Fetching R2 content for every row in a
  list query multiplies latency by N.
- **Storing the uncompressed hash inside R2 metadata only**: Always store `content_hash` in
  D1 as well. If the R2 object is accidentally deleted and needs re-upload, the D1 hash is
  the integrity reference.
- **Not handling the inline path after a threshold change**: If you later lower the inline
  threshold, existing large rows still have `content_r2_key` set. The read path must check
  `content_r2_key IS NOT NULL` before attempting inline read.

## Gotchas

- `CompressionStream('gzip')` is available in Cloudflare Workers runtime (V8) without any
  npm import. It is not available in Node.js < 18 — local tests using Miniflare or
  `wrangler dev` work correctly; Jest/Node tests need the `stream/web` polyfill or Vitest
  with Workers pool.
- R2 `put()` accepts a `ReadableStream`, `ArrayBuffer`, or `string`. Pass a `Uint8Array`
  from `gzipText()` — it is accepted as `ArrayBuffer`-like.
- D1 `content_r2_key` should be a stable, deterministic path (e.g., `articles/{tenantId}/{id}.gz`)
  so that an update overwrites the same R2 key rather than accumulating orphaned objects.
- R2 does not charge per-request for reads within Workers (egress to Workers is free). The
  cost is storage + per-class-A/B operation counts. Compress to minimize stored bytes.

## Verification

```typescript
// Verify round-trip integrity
async function verifyArticleIntegrity(env: Env, articleId: string): Promise<boolean> {
  const result = await getArticleContent(env, articleId);
  if (!result) return false;
  const { meta, content } = result;
  const actualHash = await sha256Hex(content);
  const ok = actualHash === meta.content_hash;
  console.log(`Article ${articleId}: hash match=${ok}, size=${content.length} vs ${meta.content_size}`);
  return ok;
}
```

```sql
-- D1: Find articles whose R2 content has not been fetched yet (missing pointer)
SELECT id, title, content_size
FROM   articles
WHERE  content_r2_key IS NULL AND content_inline IS NULL;

-- Storage savings estimate per tenant
SELECT tenant_id,
       COUNT(*) AS article_count,
       SUM(content_size) AS total_uncompressed_bytes,
       ROUND(AVG(content_size) / 1024.0, 1) AS avg_kb
FROM   articles
GROUP  BY tenant_id
ORDER  BY total_uncompressed_bytes DESC;
```

## Related

- `d1-hot-cold-data-tiering.md` — offloading rows to R2 for bulk archival
- `d1-json-column-patterns.md` — inline JSON vs. external storage trade-offs
- `d1-streaming-export-analytics-pipeline.md` — streaming D1 data to R2 for analytics
- `database-encryption-at-rest.md` — encrypting R2 objects server-side

## Sources

- Cloudflare Workers CompressionStream: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
- Cloudflare R2 Workers API: https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- SQLite BLOB storage internals: https://www.sqlite.org/fileformat.html
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
