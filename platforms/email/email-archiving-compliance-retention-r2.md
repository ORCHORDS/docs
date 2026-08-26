# Email Archiving and Compliance Retention with Cloudflare R2

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Financial services, healthcare, legal, and public-sector organisations must retain copies
of all email communications for defined periods: SEC Rule 17a-4 requires broker-dealers
to retain records for 3–6 years; FINRA Rule 4511 mandates 3 years for general business
communications; HIPAA requires 6 years from creation or last use; GDPR grants data
subjects the right of access for all processing records. An inbound email parsed by a
Cloudflare Email Worker or an outbound transactional email sent through an ESP must be
archived in a tamper-evident, indexed, and retrievable form. Cloudflare R2 provides
durable object storage with no egress fees, WORM-compatible write patterns, and native
integration with Workers.

## Context

Email archiving differs from email backup. A backup is a point-in-time snapshot of a
mailbox. An archive is an indexed, immutable, per-message store with full-text search,
metadata indexing, and legal hold capabilities. The archive must be:

- **Immutable**: once stored, messages cannot be altered or deleted before the
  retention deadline.
- **Indexed**: metadata (sender, recipients, subject, date) is searchable without
  downloading the full MIME body.
- **Retrievable**: authorised administrators can export a specific message or date range
  within an SLA (typically 24 hours for e-discovery).
- **Audited**: every access to the archive is itself logged.

R2 handles storage; D1 provides the metadata index; Workers glue them together.

## Architecture

```
[Inbound CF Email Worker]──────────────────────────┐
                                                    ▼
[ESP Event Webhook (outbound sent event)] ──► [Archive Worker]
                                                    │
                          ┌─────────────────────────┤
                          │                         │
                  [R2: raw .eml blobs]        [D1: message index]
                          │
                 [Object lock policy: WORM]
```

Each archived message is stored as a raw RFC 5322 `.eml` blob in R2 under a
content-addressable path. The D1 index holds envelope metadata for fast search. Legal
hold prevents deletion of objects tagged with a hold flag.

## R2 Storage Layout

```
archive/
  2026/
    08/
      22/
        {messageId}.eml
        {messageId}.meta.json
```

Keys are prefixed by date (YYYY/MM/DD) for efficient lifecycle rule targeting. Each
message is stored twice: the raw `.eml` and a compact `.meta.json` containing only
envelope fields, enabling metadata-only listing without reading the full message body.

## D1 Message Index Schema

```sql
CREATE TABLE archived_messages (
  id              TEXT    PRIMARY KEY,   -- SHA-256 of raw .eml (hex)
  r2_key          TEXT    NOT NULL UNIQUE,
  direction       TEXT    NOT NULL,      -- 'inbound' | 'outbound'
  message_id      TEXT,                  -- RFC 5322 Message-ID header
  from_address    TEXT    NOT NULL,
  to_addresses    TEXT    NOT NULL,      -- JSON array
  cc_addresses    TEXT,                  -- JSON array
  subject         TEXT,
  sent_at         INTEGER NOT NULL,      -- Unix ms from Date header
  size_bytes      INTEGER NOT NULL,
  has_attachments INTEGER NOT NULL DEFAULT 0,
  retention_class TEXT    NOT NULL DEFAULT 'standard',  -- 'standard' | 'legal_hold'
  retain_until    INTEGER NOT NULL,      -- Unix ms; deletion not permitted before this
  archived_at     INTEGER NOT NULL,
  deleted_at      INTEGER                -- NULL until retention expires and object removed
);

CREATE INDEX idx_am_from        ON archived_messages(from_address);
CREATE INDEX idx_am_sent_at     ON archived_messages(sent_at);
CREATE INDEX idx_am_retention   ON archived_messages(retention_class, retain_until);
CREATE INDEX idx_am_message_id  ON archived_messages(message_id);
```

## Archive Worker (Inbound)

Cloudflare Email Workers receive inbound messages as a `ForwardableEmailMessage`. The
Worker serialises the message to raw RFC 5322 and stores it in R2:

```typescript
// src/email-archive.ts
import { createHash } from 'crypto';

interface Env {
  ARCHIVE_BUCKET: R2Bucket;
  ARCHIVE_DB: D1Database;
  RETENTION_DAYS: string;  // e.g. "2190" for 6 years
}

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const retentionDays = parseInt(env.RETENTION_DAYS, 10);
    const now = Date.now();
    const retainUntil = now + retentionDays * 86_400_000;

    // Read raw bytes from the message stream
    const rawBytes = await new Response(message.raw).arrayBuffer();
    const hash = createHash('sha256').update(new Uint8Array(rawBytes)).digest('hex');

    const sentAt = new Date(message.headers.get('Date') ?? now).getTime();
    const datePath = new Date(sentAt).toISOString().slice(0, 10).replace(/-/g, '/');
    const r2Key = `archive/${datePath}/${hash}.eml`;

    // Store raw .eml with immutability headers
    await env.ARCHIVE_BUCKET.put(r2Key, rawBytes, {
      httpMetadata: { contentType: 'message/rfc822' },
      customMetadata: {
        direction:    'inbound',
        fromAddress:  message.from,
        retainUntil:  retainUntil.toString(),
        archivedAt:   now.toString(),
      },
    });

    // Store lightweight metadata sidecar
    const meta = {
      id: hash, direction: 'inbound',
      from: message.from, to: message.to,
      subject: message.headers.get('Subject') ?? '',
      sentAt, sizeBytes: rawBytes.byteLength,
      retainUntil,
    };
    await env.ARCHIVE_BUCKET.put(
      `archive/${datePath}/${hash}.meta.json`,
      JSON.stringify(meta),
      { httpMetadata: { contentType: 'application/json' } },
    );

    // Index in D1
    await env.ARCHIVE_DB.prepare(`
      INSERT OR IGNORE INTO archived_messages
        (id, r2_key, direction, from_address, to_addresses, subject,
         sent_at, size_bytes, has_attachments, retention_class, retain_until, archived_at)
      VALUES (?, ?, 'inbound', ?, ?, ?, ?, ?, 0, 'standard', ?, ?)
    `).bind(
      hash, r2Key, message.from, JSON.stringify([message.to]),
      message.headers.get('Subject') ?? '',
      sentAt, rawBytes.byteLength, retainUntil, now,
    ).run();

    // Pass through to actual mailbox
    await message.forward(message.to);
  },
};
```

## Lifecycle Rules and Retention Enforcement

R2 does not natively enforce WORM deletion holds. Implement a scheduled Worker cron
to enforce the `retain_until` policy and purge expired objects:

```typescript
// src/retention-cleanup.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const expiredAt = Date.now();
    const rows = await env.ARCHIVE_DB.prepare(`
      SELECT id, r2_key FROM archived_messages
      WHERE retain_until <= ?
        AND retention_class = 'standard'
        AND deleted_at IS NULL
      LIMIT 500
    `).bind(expiredAt).all<{ id: string; r2_key: string }>();

    for (const row of rows.results) {
      await env.ARCHIVE_BUCKET.delete(row.r2_key);
      await env.ARCHIVE_BUCKET.delete(row.r2_key.replace('.eml', '.meta.json'));
      await env.ARCHIVE_DB.prepare(
        'UPDATE archived_messages SET deleted_at = ? WHERE id = ?'
      ).bind(expiredAt, row.id).run();
    }
  },
};
```

Objects with `retention_class = 'legal_hold'` are never touched by the cleanup cron.
Legal holds must be lifted explicitly by an authorised administrator before the object
can be deleted.

## E-Discovery Export

Produce a date-bounded export of messages matching criteria:

```typescript
async function exportMessages(
  db: D1Database,
  bucket: R2Bucket,
  opts: { fromDate: number; toDate: number; fromAddress?: string },
): Promise<ArrayBuffer[]> {
  const query = opts.fromAddress
    ? 'SELECT r2_key FROM archived_messages WHERE sent_at BETWEEN ? AND ? AND from_address = ?'
    : 'SELECT r2_key FROM archived_messages WHERE sent_at BETWEEN ? AND ?';
  const binds = opts.fromAddress
    ? [opts.fromDate, opts.toDate, opts.fromAddress]
    : [opts.fromDate, opts.toDate];

  const rows = await db.prepare(query).bind(...binds).all<{ r2_key: string }>();
  const objects = await Promise.all(
    rows.results.map(r => bucket.get(r.r2_key).then(o => o?.arrayBuffer()))
  );
  return objects.filter((b): b is ArrayBuffer => b !== undefined);
}
```

For large exports, write results to a temporary R2 prefix and generate a signed URL
rather than streaming everything through the Worker response.

## Anti-patterns

- **Archiving only metadata and discarding the raw body**: e-discovery and DSAR requests
  typically require the full message including headers, MIME structure, and attachments.
  Always store the raw RFC 5322 byte stream.
- **Deleting archive records on GDPR erasure requests**: GDPR Right to Erasure (Art 17)
  is subject to overriding retention obligations (Art 17(3)(b)). Legal holds and
  regulatory retention periods take precedence. Seek legal advice before deleting
  archived communications in response to erasure requests.
- **Using mutable R2 object keys**: if the same key can be overwritten, the archive is
  not tamper-evident. Use content-addressable keys (SHA-256 of raw body) so any
  modification would produce a different key and a new object.
- **Running cleanup before legal hold check**: always check `retention_class` before
  deleting. A single missed legal hold flag causing deletion of a relevant communication
  during litigation is an extremely serious compliance failure.

## Gotchas

- **R2 does not have native object lock**: unlike AWS S3 Object Lock, R2 does not
  enforce WORM at the storage layer. Your cleanup cron must implement and respect the
  `retain_until` / `legal_hold` policy. Consider adding a separate IAM-restricted
  delete route and leaving `ARCHIVE_BUCKET` binding without `delete` permission in the
  archive ingestion Worker.
- **D1 FTS for subject search**: D1 supports SQLite FTS5. Add a virtual FTS table
  over `subject` and `from_address` for fast keyword search without downloading .eml
  blobs.
- **Large attachments bloat R2 costs**: attachments are stored as part of the raw .eml.
  For MIME multipart messages with large binary parts, consider stripping attachments to
  separate R2 objects and replacing them with `message/external-body` references in the
  archived MIME — though this complicates reconstruction.
- **Time zone normalisation**: parse the `Date:` header with a robust parser that handles
  non-UTC offsets. Store `sent_at` as UTC Unix ms in D1 for consistent range queries.

## Verification

1. Send a test email to a routing address handled by the archive Worker; confirm the
   `.eml` object appears in R2 and the row appears in D1 within 5 s.
2. Query the D1 index for the test message by sender address and confirm correct
   `retain_until` timestamp.
3. Attempt to delete an R2 object with `legal_hold` retention class via the cleanup cron
   and confirm it is skipped.
4. Run the e-discovery export for a known date range; open each returned `.eml` in a
   mail client and verify it renders correctly with no data loss.

## Related

- `inbound-email-processing.md`
- `email-consent-audit-trail-d1.md`
- `email-attachment-patterns.md`
- `gdpr-email-consent.md`
- `cloudflare-email-routing-workers.md`

## Sources

- SEC Rule 17a-4: https://www.ecfr.gov/current/title-17/chapter-II/part-240/section-240.17a-4
- HIPAA retention requirements: https://www.hhs.gov/hipaa/for-professionals/privacy/index.html
- Cloudflare R2 docs: https://developers.cloudflare.com/r2/
- RFC 5322 Internet Message Format: https://www.rfc-editor.org/rfc/rfc5322
- Cloudflare Email Workers docs: https://developers.cloudflare.com/email-routing/email-workers/
