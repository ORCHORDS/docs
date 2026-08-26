# Workers AI Toxicity Scoring D1 Audit Trail

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project moderation teams need a persistent, queryable record of every toxicity score assigned to user-generated content so they can audit decisions, retrain classifiers with corrected labels, and respond to regulatory data-access requests. In-memory verdicts discarded after the request cycle leave no paper trail.

## Context

Workers AI runs toxicity classification synchronously in the Worker's request context. D1 is Cloudflare's edge SQL database, co-located with the Worker runtime and accessible without an additional network round-trip. Combining both within a single Worker handler means the score is computed and durably logged inside the same CPU budget with one SQL write.

## Architecture — Audit Schema

The D1 audit table captures the raw score, the model used, the resolved action, any human override, and a SHA-256 of the content for de-identification. The content itself is never stored — only its hash and the associated metadata.

```sql
-- migrations/0001_toxicity_audit.sql
CREATE TABLE IF NOT EXISTS toxicity_audit (
  id            TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  content_hash  TEXT    NOT NULL,   -- SHA-256 of submitted text
  session_hash  TEXT    NOT NULL,   -- hashed anonymous session token
  score         REAL    NOT NULL,   -- 0.0 .. 1.0
  model         TEXT    NOT NULL,
  action        TEXT    NOT NULL,   -- 'allow' | 'block' | 'review'
  category      TEXT,               -- e.g. 'S2' from Llama Guard
  human_label   TEXT,               -- set by moderator: 'tp' | 'fp' | 'tn' | 'fn'
  created_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  reviewed_at   INTEGER
);

CREATE INDEX idx_toxicity_audit_action     ON toxicity_audit(action, created_at DESC);
CREATE INDEX idx_toxicity_audit_session    ON toxicity_audit(session_hash, created_at DESC);
CREATE INDEX idx_toxicity_audit_score_band ON toxicity_audit(score, created_at DESC);
```

## Implementation — Scoring and Writing in One Handler

The Worker scores content with Workers AI and inserts an audit row atomically (D1 write is auto-committed). The SHA-256 is computed using the Web Crypto API available in the Workers runtime.

```typescript
// toxicity-handler.ts
import type { Ai, D1Database } from '@cloudflare/workers-types';

interface Env {
  AI: Ai;
  DB: D1Database;
}

const BLOCK_THRESHOLD  = 0.82;
const REVIEW_THRESHOLD = 0.50;
const MODEL = '@cf/huggingface/distilbert-sst-2-int8';

async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(text),
  );
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function scoreToxicity(
  env: Env,
  content: string,
  sessionToken: string,
): Promise<{ action: string; score: number; auditId: string }> {
  type ClassResult = { label: string; score: number };

  const results = await env.AI.run(MODEL, { text: content }) as ClassResult[];
  const score = results.find(r => r.label === 'NEGATIVE')?.score ?? 0;

  const action =
    score >= BLOCK_THRESHOLD  ? 'block'  :
    score >= REVIEW_THRESHOLD ? 'review' : 'allow';

  const [contentHash, sessionHash] = await Promise.all([
    sha256Hex(content),
    sha256Hex(sessionToken),
  ]);

  const auditId = crypto.randomUUID();

  await env.DB.prepare(`
    INSERT INTO toxicity_audit
      (id, content_hash, session_hash, score, model, action)
    VALUES (?, ?, ?, ?, ?, ?)
  `).bind(auditId, contentHash, sessionHash, score, MODEL, action).run();

  return { action, score, auditId };
}
```

## Implementation — Human Override Endpoint

Moderators correct false positives and false negatives through an internal API that updates `human_label` and `reviewed_at`. These labelled rows feed the weekly model evaluation pipeline.

```typescript
// override-handler.ts
export async function applyHumanLabel(
  db: D1Database,
  auditId: string,
  label: 'tp' | 'fp' | 'tn' | 'fn',
  reviewerToken: string, // internal auth — not stored, only validated
): Promise<boolean> {
  const result = await db.prepare(`
    UPDATE toxicity_audit
       SET human_label  = ?,
           reviewed_at  = unixepoch()
     WHERE id = ?
       AND human_label IS NULL   -- prevent double-labelling
  `).bind(label, auditId).run();

  return (result.meta.changes ?? 0) > 0;
}
```

## Optimization — Batch Export for Retraining

A Cron Trigger exports recently labelled rows to R2 as JSONL for the weekly fine-tuning and threshold calibration job. Using D1's streaming query API avoids loading all rows into memory.

```typescript
// export-labelled.ts
export async function exportLabelledToR2(
  db: D1Database,
  r2: R2Bucket,
  since: number, // Unix epoch seconds
): Promise<{ exported: number }> {
  const rows = await db.prepare(`
    SELECT content_hash, score, model, action, human_label, created_at
      FROM toxicity_audit
     WHERE human_label IS NOT NULL
       AND reviewed_at >= ?
     ORDER BY reviewed_at ASC
     LIMIT 5000
  `).bind(since).all();

  if (!rows.results.length) return { exported: 0 };

  const jsonl = rows.results.map(r => JSON.stringify(r)).join('\n');
  const key = `exports/toxicity/${Date.now()}.jsonl`;

  await r2.put(key, jsonl, {
    httpMetadata: { contentType: 'application/jsonlines' },
  });

  return { exported: rows.results.length };
}
```

## Monitoring — Score Distribution Query

Run this against D1 daily to detect classifier drift — a rising tail of scores in the 0.5–0.8 band that are being labelled `fp` (false positive) signals the model needs re-calibration.

```typescript
// drift-check.ts
export async function getScoreDistribution(
  db: D1Database,
  windowHours = 24,
): Promise<{ band: string; count: number; fp_rate: number }[]> {
  const result = await db.prepare(`
    SELECT
      CASE
        WHEN score < 0.5  THEN 'low'
        WHEN score < 0.82 THEN 'mid'
        ELSE                   'high'
      END AS band,
      COUNT(*) AS count,
      ROUND(
        SUM(CASE WHEN human_label = 'fp' THEN 1 ELSE 0 END) * 1.0 / COUNT(*),
        4
      ) AS fp_rate
    FROM toxicity_audit
    WHERE created_at >= unixepoch() - ? * 3600
    GROUP BY band
  `).bind(windowHours).all();

  return result.results as { band: string; count: number; fp_rate: number }[];
}
```

## Anti-patterns

- Storing the raw content text in D1 alongside the score — hashes suffice for audit linkage and avoid a PII storage obligation.
- Using `db.exec()` for parameterised writes — always use `db.prepare().bind()` to prevent SQL injection from content hashes or other string values.
- Running the D1 write inside a `waitUntil` without also guarding the response path — if the write fails silently, blocks still go through without a record.
- Indexing every column — the three partial indexes above cover all query patterns; over-indexing degrades D1 write throughput.
- Allowing `human_label` to be overwritten without a log — implement an append-only `label_history` table for dispute resolution.

## Gotchas

- D1 has a 1 MB row size limit — `content_hash` is always 64 hex chars, well within bounds, but JSONB metadata columns can grow if added carelessly.
- D1 is eventually consistent across replicas; read-your-writes is not guaranteed unless you route the immediate moderator GET to the primary via `db.withSession('first-primary')`.
- `unixepoch()` in D1 SQLite returns seconds, not milliseconds — be consistent with the application layer that computes `Date.now()` in ms.
- Workers AI rate limits are global; a high-volume submission spike can 429 the classifier, leaving the audit row unwritten if the error is not caught and the row is not written with `score = -1` and `action = 'error'`.
- D1 free tier is limited to 100k rows written per day — at scale, partition audit rows into daily tables or use a rolling delete strategy.

## Verification

```bash
# Submit content and check for audit row
AUDIT_ID=$(curl -sX POST https://api.example.com/posts \
  -d '{"text":"test post"}' | jq -r .auditId)

wrangler d1 execute example project-db --command \
  "SELECT id, score, action FROM toxicity_audit WHERE id = '$AUDIT_ID'"

# Apply a human label
curl -sX PATCH https://internal.example.com/moderation/label \
  -H "Authorization: Bearer $MOD_TOKEN" \
  -d "{\"auditId\":\"$AUDIT_ID\",\"label\":\"tp\"}" | jq .
```

## Related

- `documentation/categories/ai-ml/workers-ai-content-safety-classifier-pipeline.md`
- `documentation/categories/ai-ml/workers-ai-spam-detection-ugc.md`
- `documentation/categories/ai-ml/llm-quality-scoring-pipeline-d1.md`
- `documentation/categories/ai-ml/ai-gateway-request-log-analysis-r2-pipeline.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers-ai/models/distilbert-sst-2-int8/
- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
