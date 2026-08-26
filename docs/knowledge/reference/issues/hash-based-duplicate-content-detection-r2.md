# Hash-Based Duplicate Content Detection at Upload (R2 Pipeline)
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project users frequently attempt to re-upload content that has already been moderated and removed.
On an anonymous platform, there are no account-level upload histories to query. The same violating
image or video clip gets submitted with different filenames, slightly modified EXIF metadata, or
trivial pixel edits (JPEG re-save, brightness +1, single-pixel border) that defeat exact SHA-256
matching. Without a perceptual hash layer, the same prohibited content can be re-uploaded thousands
of times across anonymous sessions, bypassing moderation queues.

The goal: intercept duplicate or near-duplicate violating content at upload time (before it reaches
the moderation queue or becomes publicly accessible), add zero false positives for legitimate content,
and keep the pipeline under 150ms added latency on the upload hot path.

---

## Context

example project media uploads flow through a Cloudflare Worker that:
1. Validates the Turnstile session token.
2. Streams the upload body to R2.
3. Queues a moderation job in D1 / Cloudflare Queues.

The duplicate detection layer must intercept between steps 2 and 3. Content that is confirmed-removed
(moderator-actioned) is added to a hash blocklist in D1. New uploads are checked against that blocklist
before the moderation queue is written.

Two hash families are needed:

| Hash type        | Defeats                      | Compute location  | Latency   |
|------------------|------------------------------|-------------------|-----------|
| SHA-256 (exact)  | Identical bytes               | Worker (stream)   | ~5ms      |
| pHash (perceptual)| JPEG resave, minor edits     | Worker or AI      | ~80ms     |
| VideoHash (TMK+PDQF)| Video re-encode, trim     | Post-upload async | N/A hot path |

SHA-256 runs on the upload stream inside the Worker. Perceptual hash (pHash for images) runs via
Workers AI (`workers-ai/@cf/img2vec-artist` embedding or a lightweight DCT implementation). Video
hashing runs as an asynchronous Cloudflare Queue consumer.

---

## Section 1 — D1 Schema

```sql
-- content_hash_blocklist: confirmed-removed content hashes
CREATE TABLE IF NOT EXISTS content_hash_blocklist (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  sha256            TEXT    UNIQUE,          -- hex string, NULL if not computed
  phash             TEXT,                    -- 64-bit hex perceptual hash
  phash_hamming_threshold INTEGER NOT NULL DEFAULT 10,  -- max Hamming distance for match
  media_type        TEXT    NOT NULL,        -- image | video | audio
  violation_code    TEXT    NOT NULL,
  moderator_id      TEXT,                   -- NULL = system-added (e.g., CSAM PhotoDNA match)
  added_at          INTEGER NOT NULL DEFAULT (unixepoch()),
  expires_at        INTEGER,                -- NULL = permanent block
  notes             TEXT
);

CREATE INDEX IF NOT EXISTS blocklist_sha256   ON content_hash_blocklist (sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS blocklist_phash    ON content_hash_blocklist (phash)  WHERE phash IS NOT NULL;

-- upload_events: tracks all uploads and their hash-check outcomes
CREATE TABLE IF NOT EXISTS upload_events (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  session_token     TEXT    NOT NULL,
  r2_key            TEXT,                   -- NULL if upload was blocked before R2 write
  sha256            TEXT    NOT NULL,
  phash             TEXT,
  match_type        TEXT,                   -- none | exact | perceptual
  matched_hash_id   INTEGER,
  action            TEXT    NOT NULL DEFAULT 'allowed', -- allowed | quarantined | blocked
  created_at        INTEGER NOT NULL DEFAULT (unixepoch()),
  FOREIGN KEY (matched_hash_id) REFERENCES content_hash_blocklist(id)
);

CREATE INDEX IF NOT EXISTS upload_events_session
  ON upload_events (session_token, created_at DESC);
```

---

## Section 2 — SHA-256 Streaming on Upload

```typescript
// upload-handler.ts

interface Env {
  MEDIA_BUCKET: R2Bucket;
  DB: D1Database;
  UPLOAD_QUEUE: Queue;
}

export async function handleUpload(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const sessionToken = request.headers.get('X-Session-Token');
  if (!sessionToken) return new Response('Unauthorized', { status: 401 });

  const contentType = request.headers.get('Content-Type') ?? '';
  if (!contentType.startsWith('image/') && !contentType.startsWith('video/')) {
    return new Response('Unsupported media type', { status: 415 });
  }

  // Tee the stream: one branch for SHA-256, one for R2 upload
  const [streamForHash, streamForR2] = request.body!.tee();

  // Compute SHA-256 concurrently with buffering for R2
  const sha256Promise = computeStreamSha256(streamForHash);
  const r2Key = `pending/${sessionToken}/${crypto.randomUUID()}`;

  // Write to R2 — note: R2 PutObject requires the full body, so we buffer for small files
  // For large video uploads, use R2 multipart upload
  const [sha256, r2Object] = await Promise.all([
    sha256Promise,
    env.MEDIA_BUCKET.put(r2Key, streamForR2, {
      httpMetadata: { contentType },
    }),
  ]);

  // Exact hash check against blocklist
  const exactMatch = await env.DB.prepare(`
    SELECT id, violation_code FROM content_hash_blocklist
    WHERE sha256 = ?
      AND (expires_at IS NULL OR expires_at > unixepoch())
  `).bind(sha256).first<{ id: number; violation_code: string }>();

  if (exactMatch) {
    // Delete from R2 (fire-and-forget)
    ctx.waitUntil(env.MEDIA_BUCKET.delete(r2Key));
    ctx.waitUntil(logUploadEvent(env.DB, sessionToken, null, sha256, null,
      'exact', exactMatch.id, 'blocked'));
    return new Response(JSON.stringify({ error: 'content_blocked', code: exactMatch.violation_code }), {
      status: 451, // Unavailable For Legal Reasons
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Queue for async perceptual hash + moderation
  await env.UPLOAD_QUEUE.send({
    type: 'media_moderation',
    r2Key,
    sha256,
    sessionToken,
    mediaType: contentType.startsWith('image/') ? 'image' : 'video',
  });

  ctx.waitUntil(logUploadEvent(env.DB, sessionToken, r2Key, sha256, null,
    'none', null, 'allowed'));

  return new Response(JSON.stringify({ status: 'pending_moderation', key: r2Key }), {
    status: 202,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function computeStreamSha256(stream: ReadableStream<Uint8Array>): Promise<string> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let totalLen = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    totalLen += value.length;
  }

  // Assemble into single buffer
  const buffer = new Uint8Array(totalLen);
  let offset = 0;
  for (const chunk of chunks) {
    buffer.set(chunk, offset);
    offset += chunk.length;
  }

  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function logUploadEvent(
  db: D1Database,
  sessionToken: string,
  r2Key: string | null,
  sha256: string,
  phash: string | null,
  matchType: string,
  matchedHashId: number | null,
  action: string
): Promise<void> {
  await db.prepare(`
    INSERT INTO upload_events (session_token, r2_key, sha256, phash, match_type, matched_hash_id, action)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).bind(sessionToken, r2Key, sha256, phash, matchType, matchedHashId, action).run();
}
```

---

## Section 3 — Perceptual Hash Queue Consumer (Images)

```typescript
// queue-consumer-phash.ts
// Runs as a Cloudflare Queue consumer (async, not on the hot upload path)

interface QueueMessage {
  type: string;
  r2Key: string;
  sha256: string;
  sessionToken: string;
  mediaType: 'image' | 'video';
}

interface Env {
  MEDIA_BUCKET: R2Bucket;
  DB: D1Database;
  AI: Ai;
}

export default {
  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { r2Key, sha256, sessionToken, mediaType } = msg.body;
      if (mediaType !== 'image') {
        msg.ack();
        continue; // Video hashing handled by a separate consumer
      }

      try {
        // Fetch image from R2
        const r2Object = await env.MEDIA_BUCKET.get(r2Key);
        if (!r2Object) { msg.ack(); continue; }

        const imageBytes = await r2Object.arrayBuffer();

        // Compute DCT-based perceptual hash (64-bit)
        const phash = await computeDctPHash(imageBytes);

        // Check against blocklist using Hamming distance
        // D1 doesn't support bitwise Hamming directly; we fetch candidates and compute in JS
        const candidates = await env.DB.prepare(`
          SELECT id, phash, phash_hamming_threshold, violation_code
          FROM content_hash_blocklist
          WHERE phash IS NOT NULL
            AND media_type = 'image'
            AND (expires_at IS NULL OR expires_at > unixepoch())
        `).all<{ id: number; phash: string; phash_hamming_threshold: number; violation_code: string }>();

        let matchedId: number | null = null;
        let matchedViolation: string | null = null;

        for (const row of candidates.results) {
          const dist = hammingDistance(phash, row.phash);
          if (dist <= row.phash_hamming_threshold) {
            matchedId = row.id;
            matchedViolation = row.violation_code;
            break;
          }
        }

        if (matchedId !== null) {
          // Delete from R2 and mark blocked
          await env.MEDIA_BUCKET.delete(r2Key);
          await env.DB.batch([
            env.DB.prepare(`
              UPDATE upload_events SET match_type = 'perceptual', matched_hash_id = ?, action = 'blocked'
              WHERE sha256 = ? AND session_token = ?
            `).bind(matchedId, sha256, sessionToken),
            // Also add exact SHA-256 to blocklist to speed up future checks
            env.DB.prepare(`
              INSERT OR IGNORE INTO content_hash_blocklist (sha256, phash, media_type, violation_code)
              VALUES (?, ?, 'image', ?)
            `).bind(sha256, phash, matchedViolation),
          ]);
        } else {
          // Not a duplicate — update phash in upload_events for future learning
          await env.DB.prepare(`
            UPDATE upload_events SET phash = ? WHERE sha256 = ? AND session_token = ?
          `).bind(phash, sha256, sessionToken).run();
        }

        msg.ack();
      } catch (err) {
        msg.retry({ delaySeconds: 60 });
      }
    }
  }
};

function hammingDistance(a: string, b: string): number {
  // Both are 64-bit hex strings (16 hex chars)
  let dist = 0;
  for (let i = 0; i < a.length; i += 4) {
    const va = parseInt(a.slice(i, i + 4), 16);
    const vb = parseInt(b.slice(i, i + 4), 16);
    let xor = va ^ vb;
    while (xor) { dist += xor & 1; xor >>= 1; }
  }
  return dist;
}

async function computeDctPHash(buffer: ArrayBuffer): Promise<string> {
  // In a real Worker: use Workers AI image embedding or a WASM-compiled DCT pHash library.
  // Stub: returns a deterministic 64-bit hex hash for illustration.
  const hashBuf = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(hashBuf).slice(0, 8))
    .map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Section 4 — Adding Hashes to the Blocklist (Moderator API)

```typescript
// moderator-blocklist-api.ts

export async function addToBlocklist(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{
    sha256?: string;
    phash?: string;
    mediaType: 'image' | 'video' | 'audio';
    violationCode: string;
    moderatorId: string;
    durationDays?: number;
  }>();

  if (!body.sha256 && !body.phash) {
    return new Response('At least one of sha256 or phash is required', { status: 400 });
  }

  const expiresAt = body.durationDays
    ? Math.floor(Date.now() / 1000) + body.durationDays * 86400
    : null;

  await env.DB.prepare(`
    INSERT INTO content_hash_blocklist (sha256, phash, media_type, violation_code, moderator_id, expires_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(sha256) DO UPDATE SET
      phash         = COALESCE(excluded.phash, phash),
      violation_code = excluded.violation_code,
      moderator_id  = excluded.moderator_id,
      expires_at    = excluded.expires_at
  `).bind(body.sha256 ?? null, body.phash ?? null, body.mediaType,
           body.violationCode, body.moderatorId, expiresAt).run();

  return new Response(JSON.stringify({ status: 'added' }), {
    headers: { 'Content-Type': 'application/json' }
  });
}
```

---

## Anti-patterns

- **Blocking by SHA-256 alone**: A single-pixel edit or JPEG re-save produces a completely different
  SHA-256. Exact hashing catches only verbatim re-uploads. Always pair with perceptual hashing.
- **Storing full image bytes in D1 for reference**: D1 rows have a 1MB column limit and D1 is not
  designed for binary storage. Images belong in R2; only hashes go in D1.
- **Running perceptual hash on the upload hot path**: DCT pHash over a 4K image takes 100–300ms.
  Run it in the queue consumer so the user gets an immediate `202 Accepted` response.
- **Setting Hamming threshold too low (< 5)**: Leads to false positives on near-identical but
  legitimately different images (e.g., same product photo from different sellers). Tune threshold
  per violation category: CSAM uses ≤ 4, spam uses ≤ 12.
- **No expiry on blocklist entries**: Defamatory content blocklists may need to be removed if a
  court order is reversed. Always support `expires_at` and an explicit moderator-delete API.
- **Writing `r2_key` before hash check**: If the hash check is async (network call), content is
  momentarily in R2 unblocked. The architecture above writes to R2 but keeps the upload in
  `pending/` prefix with no public URL until the moderation queue confirms it.

---

## Gotchas

- R2 `put()` requires the full body to be consumed. You cannot abort a `put()` mid-stream cleanly;
  the `pending/` prefix approach (upload then delete on block) is the correct pattern.
- `ReadableStream.tee()` in Workers creates two branches that are buffered in memory. For uploads
  over ~5MB, the buffer pressure can cause the Worker to exceed its 128MB memory limit. Gate large
  uploads to the multipart upload path (R2 createMultipartUpload) where SHA-256 is computed per part.
- D1 `SELECT` over a large blocklist (> 50k rows) for Hamming-distance comparison is O(n) in JS.
  For scale, maintain a separate R2-backed Bloom filter or use Cloudflare Vectorize to store
  pHash embeddings for ANN (approximate nearest neighbor) search.
- `crypto.subtle.digest('SHA-256')` is available in Workers but requires the full body to be
  buffered. Streaming SHA-256 is not natively available — implement a chunked accumulation pattern
  as shown above, or use a WASM SHA-256 that accepts incremental updates.
- The `451 Unavailable For Legal Reasons` HTTP status is the correct code for content blocked for
  legal/compliance reasons (RFC 7725). Return `403` only for auth/permission failures, not
  hash-match blocks.

---

## Verification

```bash
# 1. Upload a known-blocked image (add its SHA-256 to blocklist first)
SHA=$(echo -n "test" | sha256sum | cut -d' ' -f1)
wrangler d1 execute example project-prod --command \
  "INSERT INTO content_hash_blocklist (sha256, media_type, violation_code)
   VALUES ('$SHA', 'image', 'test_block');"

curl -X POST https://example.com/api/upload \
  -H "X-Session-Token: testsession" \
  -H "Content-Type: image/jpeg" \
  --data-binary "test"
# Expected: 451 { "error": "content_blocked", "code": "test_block" }

# 2. Verify R2 cleanup (the upload should NOT exist in pending/)
wrangler r2 object list example project-media-prod --prefix "pending/"
# Should not contain the blocked upload key

# 3. Verify upload_events log
wrangler d1 execute example project-prod --command \
  "SELECT action, match_type FROM upload_events ORDER BY created_at DESC LIMIT 5;"

# 4. Verify perceptual hash queue consumer metrics
wrangler queues consumer get example project-media-moderation
# Check: messages_acked vs messages_retried ratio
```

---

## Related

- `877-csam-vendor-integration.md`
- `spam-post-detection-cloudflare-workers-ai.md`
- `r2-etag-conditional-request.md`
- `anonymous-content-reporting-worker-pipeline.md`
- `platform-manipulation-brigading-detection.md`
- `copyright-dmca-takedown-worker-pipeline.md`

---

## Sources

- pHash perceptual hashing algorithm — https://www.phash.org/
- PhotoDNA (Microsoft) for CSAM matching — https://www.microsoft.com/en-us/photodna
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- RFC 7725 (HTTP 451 status code) — https://www.rfc-editor.org/rfc/rfc7725
- Cloudflare Vectorize (ANN search) — https://developers.cloudflare.com/vectorize/
- TMK+PDQF video hashing (Facebook) — https://github.com/facebook/ThreatExchange/tree/main/pdq/cpp
