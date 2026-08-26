# Vectorize Per-User Private Search Isolation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project supports a "private posts" feature where anonymous users can create posts visible only to themselves (saved drafts, personal notes). These posts must be indexed for semantic search, but a user performing a search must never receive results from another user's private posts, even if the vectors are semantically similar. The challenge: Vectorize is a single shared index, and semantic similarity is calculated across the entire index unless access controls are enforced at the query layer.

---

## Context

Vectorize provides two mechanisms for per-user isolation:

1. **Metadata filtering**: attach a `userId` field to every vector's metadata. At query time, filter with `{ userId: { $eq: currentUserId } }`. This keeps all vectors in one index but restricts results to the requesting user.
2. **Namespace partitioning**: create a separate Vectorize index per user (or per user shard). Queries target only the user's index, providing hard isolation at the infrastructure level.

For example project, metadata filtering is the correct approach because the number of users is unbounded (a Vectorize index per user would quickly exhaust the 100-index account limit), and Vectorize metadata filters are evaluated before the ANN scan, not after, which preserves recall efficiency.

Namespace partitioning is reserved for multi-tenant enterprise scenarios with a bounded, known set of tenants (see `vectorize-multi-tenant-namespace-partitioning.md`).

---

## Vector Schema Design

```typescript
// src/lib/private-post-vector.ts
export interface PrivatePostMetadata {
  userId:      string;   // stable anonymous user identifier (hash)
  postId:      string;
  visibility:  'private' | 'public';
  createdAt:   number;   // unix epoch ms
  textSnippet: string;   // first 200 chars for result rendering
  tags:        string[]; // user-applied tags for faceted search
}

export function buildPrivateVector(
  postId:   string,
  userId:   string,
  text:     string,
  tags:     string[],
  embedding: number[]
): VectorizeVector {
  return {
    id:     `${userId}:${postId}`, // compound ID prevents cross-user ID collisions
    values: embedding,
    metadata: {
      userId,
      postId,
      visibility:  'private',
      createdAt:   Date.now(),
      textSnippet: text.slice(0, 200),
      tags,
    } satisfies PrivatePostMetadata,
  };
}
```

---

## Upsert with User Binding

```typescript
// src/lib/private-search-indexer.ts
import { buildPrivateVector } from './private-post-vector';

export async function indexPrivatePost(
  ai:        Ai,
  vectorize: VectorizeIndex,
  opts: {
    postId: string;
    userId: string;
    text:   string;
    tags:   string[];
  }
): Promise<void> {
  // Generate embedding
  const result = await ai.run(
    '@cf/baai/bge-large-en-v1.5' as any,
    { text: [opts.text] }
  ) as { data: number[][] };

  const embedding = result.data[0];
  if (!embedding) throw new Error('Empty embedding from Workers AI');

  const vector = buildPrivateVector(
    opts.postId,
    opts.userId,
    opts.text,
    opts.tags,
    embedding
  );

  await vectorize.upsert([vector]);
}

export async function deletePrivatePost(
  vectorize: VectorizeIndex,
  postId:    string,
  userId:    string
): Promise<void> {
  // The compound ID ensures only this user's vector is deleted
  await vectorize.deleteByIds([`${userId}:${postId}`]);
}
```

---

## Secure Search Query

```typescript
// src/lib/private-search.ts
export interface PrivateSearchOpts {
  query:   string;
  userId:  string;     // MUST come from authenticated session, never from user input
  topK:    number;
  tags?:   string[];   // optional facet filter
}

export interface PrivateSearchResult {
  postId:      string;
  score:       number;
  textSnippet: string;
  createdAt:   number;
  tags:        string[];
}

export async function searchPrivatePosts(
  ai:        Ai,
  vectorize: VectorizeIndex,
  opts:      PrivateSearchOpts
): Promise<PrivateSearchResult[]> {
  // 1. Embed the query
  const queryResult = await ai.run(
    '@cf/baai/bge-large-en-v1.5' as any,
    { text: [opts.query] }
  ) as { data: number[][] };

  const queryVector = queryResult.data[0];
  if (!queryVector) throw new Error('Empty query embedding');

  // 2. Build the filter — userId is the primary isolation key
  //    All other filters are additive (AND), never replace userId
  const filter: VectorizeVectorMetadataFilter = {
    userId:     { $eq: opts.userId },
    visibility: { $eq: 'private' },
  };

  // Optional: narrow by tag (stored as array, use $in for multi-tag)
  // Note: Vectorize metadata filter on array fields uses $in on the array value
  // For single-tag filter:
  if (opts.tags && opts.tags.length === 1) {
    // @ts-ignore — Vectorize metadata filter types vary by SDK version
    filter['tags'] = { $in: opts.tags };
  }

  // 3. Query with pre-filter (Vectorize evaluates metadata filter before ANN)
  const matches = await vectorize.query(queryVector, {
    topK:            opts.topK,
    filter,
    returnMetadata:  'all',
    returnValues:    false,
  });

  // 4. Map to safe return type — never return userId in the API response
  return matches.matches.map((m) => ({
    postId:      (m.metadata as any)?.postId ?? '',
    score:       m.score,
    textSnippet: (m.metadata as any)?.textSnippet ?? '',
    createdAt:   (m.metadata as any)?.createdAt ?? 0,
    tags:        (m.metadata as any)?.tags ?? [],
  }));
}
```

---

## Session-Bound User Identity

```typescript
// src/workers/search-handler.ts
// The critical security invariant: userId is ALWAYS derived from the
// session/auth token, NEVER from the request body or query params.

import { searchPrivatePosts } from '../lib/private-search';

export interface Env {
  AI:        Ai;
  VECTORIZE: VectorizeIndex;
  KV:        KVNamespace; // session store
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // 1. Resolve userId from session token in Authorization header
    const sessionToken = req.headers.get('Authorization')?.replace('Bearer ', '');
    if (!sessionToken) {
      return Response.json({ error: 'Unauthenticated' }, { status: 401 });
    }

    const session = await env.KV.get<{ userId: string }>(
      `session:${sessionToken}`,
      'json'
    );
    if (!session?.userId) {
      return Response.json({ error: 'Invalid session' }, { status: 401 });
    }

    // userId is now server-authoritative — cannot be spoofed by the client
    const { userId } = session;

    // 2. Parse query from request body
    const body = await req.json<{ query: string; tags?: string[] }>();
    if (!body.query || body.query.length > 1000) {
      return Response.json({ error: 'Invalid query' }, { status: 400 });
    }

    // 3. Search — userId is injected by the server, not the client
    const results = await searchPrivatePosts(env.AI, env.VECTORIZE, {
      query:  body.query,
      userId, // server-derived, tamper-proof
      topK:   20,
      tags:   body.tags,
    });

    return Response.json({ results });
  },
};
```

---

## Bulk Delete on Account Deletion

```typescript
// src/lib/private-search-cleanup.ts
// When a example project user deletes their account, all their private vectors must be removed.
// Vectorize does not support "delete by metadata filter" — only by vector ID.
// Strategy: look up all private post IDs from D1, build compound IDs, delete in batches.

export async function deleteAllUserVectors(
  db:        D1Database,
  vectorize: VectorizeIndex,
  userId:    string
): Promise<{ deleted: number }> {
  let deleted = 0;
  let cursor = 0;
  const PAGE = 500; // Vectorize deleteByIds limit per call

  while (true) {
    const rows = await db.prepare(
      `SELECT id FROM posts
       WHERE author_key = ? AND visibility = 'private'
       ORDER BY ts ASC LIMIT ? OFFSET ?`
    ).bind(userId, PAGE, cursor).all<{ id: string }>();

    if (!rows.results.length) break;

    const vectorIds = rows.results.map((r) => `${userId}:${r.id}`);
    await vectorize.deleteByIds(vectorIds);
    deleted += vectorIds.length;

    cursor += PAGE;
    if (rows.results.length < PAGE) break;
  }

  return { deleted };
}
```

---

## Audit Trail for Access Verification

```typescript
// src/lib/search-audit.ts
// Log every private search query to D1 for security audit.
// example project is an anonymous platform but must demonstrate that cross-user
// data access never occurred.

export async function logSearchQuery(
  db:     D1Database,
  opts: {
    userId:       string;
    queryHash:    string;   // SHA-256 of query text — never store raw queries
    resultCount:  number;
    latencyMs:    number;
    filterUserId: string;   // should always equal userId — log mismatch as alert
  }
): Promise<void> {
  const isoViolation = opts.userId !== opts.filterUserId;

  await db.prepare(
    `INSERT INTO search_audit_log
       (ts, user_id, query_hash, result_count, latency_ms, isolation_violation)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    Date.now(),
    opts.userId,
    opts.queryHash,
    opts.resultCount,
    opts.latencyMs,
    isoViolation ? 1 : 0
  ).run();

  if (isoViolation) {
    // This should never happen — alert immediately
    console.error('[SECURITY] Search isolation violation detected', opts);
  }
}
```

---

## Anti-patterns

- **Trusting userId from the request body**: Never let the client specify their own `userId` in the search request. Clients can craft any userId value. Always derive it server-side from an authenticated session.
- **Post-filtering ANN results**: Retrieving topK results from the full index and then filtering by userId in application code. At scale, this returns zero or few results for a user (most results will be other users') while still performing a full-index ANN scan. Vectorize pre-filters before ANN; use the `filter` parameter.
- **Separate index per user**: Vectorize accounts have a 100-index limit. Creating one index per user breaks at 101 users. Use metadata filtering on a shared index instead.
- **Compound ID without separator**: Using `userId + postId` without a separator can cause collisions if `userA = "abc"`, `postB = "123"` and `userC = "ab"`, `postD = "c123"`. Use a `:` separator and enforce postId format to prevent this.
- **Storing raw query text in audit logs**: Semantic search queries over private posts may themselves be private. Store SHA-256 hashes of query text, never the raw text, to protect user privacy in audit logs.

---

## Gotchas

- Vectorize metadata filters use an exact-match comparison for string fields. If `userId` is stored as a trimmed lowercase hash, the filter value must match exactly. Inconsistent casing between insert and query silently returns zero results.
- Vectorize does not enforce unique IDs at upsert time — upserting the same compound ID twice updates the vector in place, which is the desired idempotency behavior. Do not add uniqueness checks in application code.
- The `$in` operator for array metadata fields (e.g., filtering on `tags`) is not supported in all Vectorize SDK versions. Test with the current `@cloudflare/workers-types` version and fall back to post-filter in application code if not supported.
- Deleting vectors by ID in Vectorize is eventually consistent. After `deleteByIds`, a query issued within a few seconds may still return the deleted vector. For account-deletion flows, mark the post as deleted in D1 immediately and let the Vectorize deletion propagate asynchronously.
- A user with zero indexed posts will return an empty results array, not an error. Ensure the client handles empty results gracefully rather than treating them as an error state.

---

## Verification

```typescript
// Integration test: cross-user isolation
async function testCrossUserIsolation(
  ai: Ai,
  vectorize: VectorizeIndex
) {
  const userA = 'user-a-hash-001';
  const userB = 'user-b-hash-002';

  // Index a private post for user A
  await indexPrivatePost(ai, vectorize, {
    postId: 'post-a-1',
    userId: userA,
    text:   'Secret note about the project deadline',
    tags:   [],
  });

  // Search as user B with the same semantic query
  const resultsAsB = await searchPrivatePosts(ai, vectorize, {
    query:  'project deadline',
    userId: userB,
    topK:   10,
  });

  // User B must receive zero results
  console.assert(
    resultsAsB.length === 0,
    `SECURITY VIOLATION: User B received ${resultsAsB.length} results from User A's private posts`
  );

  // Search as user A — must receive their own post
  const resultsAsA = await searchPrivatePosts(ai, vectorize, {
    query:  'project deadline',
    userId: userA,
    topK:   10,
  });

  console.assert(
    resultsAsA.some((r) => r.postId === 'post-a-1'),
    'User A should find their own private post'
  );

  console.log('Cross-user isolation test passed');
}
```

---

## Related

- `vectorize-multi-tenant-namespace-partitioning.md` — index-level partitioning for bounded tenant sets
- `vectorize-metadata-filtering-complex-predicates.md` — advanced metadata filter operators
- `vectorize-pre-post-filter-ann-metadata.md` — pre-filter vs post-filter ANN performance tradeoffs
- `vectorize-batch-upsert-incremental-sync.md` — batch upsert for private post indexing at scale
- `workers-ai-batch-embedding-queues-pipeline.md` — async embedding pipeline these posts feed into
- `rag-vector-search.md` — vector search fundamentals

---

## Sources

- Vectorize metadata filtering: https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
- Vectorize query options: https://developers.cloudflare.com/vectorize/reference/client-api/
- Vectorize limits: https://developers.cloudflare.com/vectorize/platform/limits/
- Vectorize index management: https://developers.cloudflare.com/vectorize/get-started/
- OWASP Broken Object Level Authorization (BOLA) — isolation pattern: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
