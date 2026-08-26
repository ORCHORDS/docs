# Email List Import Deduplication — Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A client imports a CSV export from an old ESP. The file has 80 000 rows with
mixed casing, plus-addressed variants (`user+tag@example.com`), and entries
already in the active list. Without deduplication, contacts receive duplicate
welcome sequences and suppression lists become inconsistent.

---

## Context

A Worker receives a multipart upload (or a pre-signed R2 URL to a CSV), streams
it line by line through a Web Streams `TransformStream`, normalises each
address, and batch-inserts into D1 with `INSERT OR IGNORE`. A deduplication
summary is written back to KV so the import job can be polled and any
anomalies flagged before the list goes live.

---

## Address Normalisation

Normalise before any storage comparison — two records that look different
but resolve to the same mailbox should count as one.

```typescript
// src/email-normalise.ts
export function normaliseEmail(raw: string): string | null {
  const trimmed = raw.trim().toLowerCase();
  const atIdx = trimmed.lastIndexOf('@');
  if (atIdx < 1) return null;

  const domain = trimmed.slice(atIdx + 1);
  let local = trimmed.slice(0, atIdx);

  // Strip plus-addressing subaddress (RFC 5321 §4.5.3 does not guarantee
  // semantics; treat it as the same mailbox for deduplication purposes)
  local = local.split('+')[0];

  // Gmail dot-insensitivity (applies to gmail.com / googlemail.com only)
  if (domain === 'gmail.com' || domain === 'googlemail.com') {
    local = local.replace(/\./g, '');
  }

  // Basic structural validation
  if (!/^[^\s@]{1,64}$/.test(local) || !/^[^\s@]+\.[^\s@]{2,}$/.test(domain)) {
    return null;
  }

  return `${local}@${domain}`;
}
```

---

## D1 Schema

```sql
CREATE TABLE contacts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  email_norm      TEXT    NOT NULL UNIQUE,   -- normalised form
  email_raw       TEXT    NOT NULL,          -- original casing preserved
  source          TEXT,
  imported_at     INTEGER NOT NULL,
  status          TEXT    NOT NULL DEFAULT 'pending'
);

CREATE TABLE import_jobs (
  id              TEXT    PRIMARY KEY,       -- UUID
  filename        TEXT,
  total_rows      INTEGER,
  inserted        INTEGER DEFAULT 0,
  duplicates      INTEGER DEFAULT 0,
  invalid         INTEGER DEFAULT 0,
  started_at      INTEGER,
  finished_at     INTEGER
);
```

---

## Streaming CSV Parser Worker

```typescript
// src/workers/import.ts
import { normaliseEmail } from '../email-normalise';

export interface Env {
  DB: D1Database;
  IMPORT_STATE: KVNamespace;
}

const BATCH_SIZE = 250;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const jobId = crypto.randomUUID();
    const now = Math.floor(Date.now() / 1000);

    await env.DB.prepare(
      `INSERT INTO import_jobs (id, started_at) VALUES (?, ?)`
    ).bind(jobId, now).run();

    // Stream body — avoids loading 80 000 rows into memory at once
    const reader = request.body!
      .pipeThrough(new TextDecoderStream())
      .getReader();

    let remainder = '';
    let batch: string[] = [];
    let inserted = 0, duplicates = 0, invalid = 0;

    const flush = async (): Promise<void> => {
      if (batch.length === 0) return;
      const placeholders = batch.map(() => '(?, ?, ?, ?)').join(',');
      const values: (string | number)[] = [];
      batch.forEach((norm) => values.push(norm, norm, 'csv-import', now));

      const result = await env.DB.prepare(
        `INSERT OR IGNORE INTO contacts (email_norm, email_raw, source, imported_at)
         VALUES ${placeholders}`
      ).bind(...values).run();

      inserted += result.meta.changes ?? 0;
      duplicates += batch.length - (result.meta.changes ?? 0);
      batch = [];
    };

    let done = false;
    while (!done) {
      const { value, done: streamDone } = await reader.read();
      done = streamDone;
      const chunk = remainder + (value ?? '');
      const lines = chunk.split('\n');
      remainder = lines.pop() ?? '';

      for (const line of lines) {
        const raw = line.split(',')[0]; // email is first column
        const norm = normaliseEmail(raw);
        if (!norm) { invalid++; continue; }
        batch.push(norm);
        if (batch.length >= BATCH_SIZE) await flush();
      }
    }

    // Process any remaining partial line
    if (remainder.trim()) {
      const norm = normaliseEmail(remainder.split(',')[0]);
      if (norm) batch.push(norm); else invalid++;
    }
    await flush();

    const total = inserted + duplicates + invalid;
    await env.DB.prepare(
      `UPDATE import_jobs
       SET total_rows=?, inserted=?, duplicates=?, invalid=?, finished_at=?
       WHERE id=?`
    ).bind(total, inserted, duplicates, invalid, Math.floor(Date.now() / 1000), jobId).run();

    // Cache summary in KV for fast polling
    await env.IMPORT_STATE.put(
      `import:${jobId}`,
      JSON.stringify({ jobId, total, inserted, duplicates, invalid, done: true }),
      { expirationTtl: 86400 }
    );

    return new Response(JSON.stringify({ jobId, inserted, duplicates, invalid }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Job Status Polling Endpoint

```typescript
// src/workers/import-status.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const jobId = url.searchParams.get('job');
    if (!jobId) return new Response('Missing job', { status: 400 });

    // Fast path: KV has the summary (job done)
    const cached = await env.IMPORT_STATE.get(`import:${jobId}`);
    if (cached) {
      return new Response(cached, { headers: { 'Content-Type': 'application/json' } });
    }

    // Slow path: job still running — query D1 directly
    const row = await env.DB.prepare(
      `SELECT * FROM import_jobs WHERE id = ?`
    ).bind(jobId).first<ImportJob>();

    if (!row) return new Response('Not found', { status: 404 });
    return new Response(JSON.stringify(row), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Reviewing Duplicates Before Going Live

```sql
-- How many contacts are still in 'pending' status from this import?
SELECT COUNT(*) FROM contacts WHERE status = 'pending';

-- Preview the duplicate rate across sources
SELECT source, COUNT(*) AS total
FROM contacts
GROUP BY source
ORDER BY total DESC;

-- Activate pending contacts after review
UPDATE contacts SET status = 'active' WHERE status = 'pending';
```

---

## Anti-patterns

- **Deduplicating in application code before insert** — a `SELECT` then
  `INSERT` pattern races under concurrent imports. `INSERT OR IGNORE` with a
  `UNIQUE` index on `email_norm` is atomic and far faster.
- **Lowercasing without plus-stripping** — `user+list@gmail.com` and
  `user@gmail.com` would be stored as separate rows and receive duplicate emails.
- **Loading the entire CSV into memory** — a 50 MB file serialised to an array
  of strings blows the Workers 128 MB memory limit. Stream line by line.

---

## Gotchas

- D1's `result.meta.changes` returns the number of rows actually inserted
  (`INSERT OR IGNORE` does not count ignored rows as changes), making it the
  correct signal for counting new vs. duplicate records.
- `TextDecoderStream` decodes UTF-8 by default; CSV exports from Excel may be
  Windows-1252. Detect the encoding or require UTF-8 and document that for
  importers.
- Workers' 30-second CPU time limit applies. For files over ~500 000 rows,
  split into chunks client-side or stream into Queues for background processing.

---

## Verification

```bash
# Upload a test CSV (first column = email)
curl -X POST https://workers.example.com/import \
  --data-binary @test-list.csv \
  -H "Content-Type: text/csv"
# Returns: {"jobId":"...","inserted":970,"duplicates":28,"invalid":2}

# Poll status
curl "https://workers.example.com/import-status?job=<jobId>"

# Verify in D1
wrangler d1 execute MY_DB --command \
  "SELECT COUNT(*) as total, status FROM contacts GROUP BY status"
```

---

## Related

- `email-list-hygiene-validation-workers.md`
- `email-suppression-list-kv-workers.md`
- `email-newsletter-double-opt-in-workers-d1.md`

---

## Sources

- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Web Streams API — https://developer.mozilla.org/en-US/docs/Web/API/Streams_API
- RFC 5321 — SMTP Addressing
