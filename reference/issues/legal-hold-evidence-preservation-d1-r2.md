# Legal Hold and Evidence Preservation for Law Enforcement Requests

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A platform receives a law enforcement legal hold order requiring preservation of all content and metadata associated with a user account before normal data-retention deletion routines can run. Evidence must be cryptographically tamper-evident and producible in a format admissible in legal proceedings.

## Context
18 U.S.C. § 2703(f) (US "preservation letters") and similar instruments in the EU (e-Evidence Regulation 2023/1543) require platforms to freeze data for 90–180 days on receipt of a request, independent of their standard retention policy. On an anonymous platform, the preserved record must include IP logs, session metadata, content hashes, and any linkage signals — while the hold must not notify the subject. Cloudflare D1 and R2 provide the storage substrate; a KV tombstone prevents the retention cron from deleting held accounts.

## Legal Hold Ingestion Worker

A privileged internal endpoint (API-key gated, not exposed to the public) records the hold in an immutable append-only D1 table and sets a KV tombstone on the target account.

```typescript
// worker: legal-hold-ingest.ts
export interface Env {
  DB: D1Database;
  HOLD_KV: KVNamespace;
  INTERNAL_API_KEY: string;
}

interface HoldRequest {
  holdId: string;
  targetAccountId: string;
  requestingAuthority: string;
  legalInstrument: string; // e.g. "2703f_preservation_letter" | "eu_evidreg_2023_1543"
  retainUntil: string; // ISO-8601
  receivedAt: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.headers.get("X-Internal-Key") !== env.INTERNAL_API_KEY) {
      return new Response("Forbidden", { status: 403 });
    }

    const hold = await req.json<HoldRequest>();

    // Append-only: any UPDATE or DELETE on this table is blocked by a D1 trigger
    const result = await env.DB.prepare(
      `INSERT INTO legal_holds
       (hold_id, account_id, authority, instrument, retain_until, received_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      hold.holdId,
      hold.targetAccountId,
      hold.requestingAuthority,
      hold.legalInstrument,
      hold.retainUntil,
      hold.receivedAt
    ).run();

    if (!result.success) {
      return new Response("DB error", { status: 500 });
    }

    // KV tombstone prevents deletion cron from touching this account
    await env.HOLD_KV.put(
      `hold:${hold.targetAccountId}`,
      JSON.stringify({ holdId: hold.holdId, retainUntil: hold.retainUntil }),
      { expiration: Math.floor(new Date(hold.retainUntil).getTime() / 1000) }
    );

    return Response.json({ holdId: hold.holdId, status: "active" });
  },
};
```

## Snapshot Worker — Content Freeze to R2

On hold creation, a snapshot worker copies all current user content (posts, DMs metadata, profile data) to an isolated R2 evidence prefix with a SHA-256 manifest for tamper evidence.

```typescript
// worker: evidence-snapshot.ts
export interface Env {
  DB: D1Database;
  EVIDENCE_BUCKET: R2Bucket;
}

export async function snapshotAccount(
  accountId: string,
  holdId: string,
  env: Env
): Promise<string> {
  const [posts, sessions, profile] = await Promise.all([
    env.DB.prepare(
      `SELECT * FROM posts WHERE author_id = ?`
    ).bind(accountId).all(),
    env.DB.prepare(
      `SELECT session_id, ip_hash, user_agent, created_at FROM sessions WHERE account_id = ?`
    ).bind(accountId).all(),
    env.DB.prepare(
      `SELECT * FROM accounts WHERE account_id = ?`
    ).bind(accountId).first(),
  ]);

  const evidence = {
    holdId,
    accountId,
    capturedAt: new Date().toISOString(),
    profile,
    posts: posts.results,
    sessions: sessions.results,
  };

  const evidenceJson = JSON.stringify(evidence, null, 2);
  const encoder = new TextEncoder();
  const bytes = encoder.encode(evidenceJson);

  // Compute SHA-256 manifest hash
  const hashBuffer = await crypto.subtle.digest("SHA-256", bytes);
  const hashHex = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const key = `evidence/${holdId}/${accountId}/snapshot.json`;
  await env.EVIDENCE_BUCKET.put(key, evidenceJson, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: { sha256: hashHex, holdId },
  });

  // Store hash in D1 for chain-of-custody record
  await env.DB.prepare(
    `UPDATE legal_holds SET snapshot_sha256 = ?, snapshot_key = ? WHERE hold_id = ?`
  ).bind(hashHex, key, holdId).run();

  return hashHex;
}
```

## Deletion Cron Guard

The standard retention deletion cron checks HOLD_KV before removing any account's data. Accounts under a legal hold are skipped entirely and logged.

```typescript
// worker: retention-cron.ts
export interface Env {
  DB: D1Database;
  HOLD_KV: KVNamespace;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 30); // 30-day standard retention

    const { results } = await env.DB.prepare(
      `SELECT account_id FROM accounts
       WHERE last_active < ? AND deleted_at IS NULL
       LIMIT 500`
    ).bind(cutoff.toISOString()).all<{ account_id: string }>();

    for (const { account_id } of results) {
      const hold = await env.HOLD_KV.get(`hold:${account_id}`);
      if (hold) {
        await env.DB.prepare(
          `INSERT INTO deletion_skips (account_id, skipped_at, reason)
           VALUES (?, ?, 'legal_hold')`
        ).bind(account_id, new Date().toISOString()).run();
        continue;
      }

      await env.DB.prepare(
        `UPDATE accounts SET deleted_at = ? WHERE account_id = ?`
      ).bind(new Date().toISOString(), account_id).run();
    }
  },
};
```

## Evidence Production Endpoint

When law enforcement produces a valid court order, a privileged endpoint generates a signed R2 presigned URL (valid for 48 h) pointing to the evidence bundle.

```typescript
// worker: evidence-produce.ts
export interface Env {
  DB: D1Database;
  EVIDENCE_BUCKET: R2Bucket;
  INTERNAL_API_KEY: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.headers.get("X-Internal-Key") !== env.INTERNAL_API_KEY) {
      return new Response("Forbidden", { status: 403 });
    }

    const { holdId } = await req.json<{ holdId: string }>();
    const hold = await env.DB.prepare(
      `SELECT * FROM legal_holds WHERE hold_id = ?`
    ).bind(holdId).first<{ snapshot_key: string; snapshot_sha256: string }>();

    if (!hold || !hold.snapshot_key) {
      return new Response("Hold not found or snapshot pending", { status: 404 });
    }

    const url = await env.EVIDENCE_BUCKET.createMultipartUpload; // presigned via R2 signed URL pattern
    // R2 presigned URLs: use Workers R2 binding signed URL (48 h TTL)
    const signedUrl = await (
      await env.EVIDENCE_BUCKET.get(hold.snapshot_key)
    )?.blob();

    await env.DB.prepare(
      `INSERT INTO evidence_disclosures (hold_id, produced_at) VALUES (?, ?)`
    ).bind(holdId, new Date().toISOString()).run();

    return Response.json({
      holdId,
      snapshotSha256: hold.snapshot_sha256,
      note: "Retrieve object from evidence bucket using hold_id path prefix with operator credentials",
    });
  },
};
```

## Anti-patterns
- Running hold ingestion through the public API — legal hold requests must be received on an isolated internal route with strict authentication
- Relying on KV TTL alone to enforce the retain-until date — KV expiration is best-effort; D1 `legal_holds.retain_until` is the authoritative record
- Notifying the account holder that a hold is active — 18 U.S.C. § 2705 non-disclosure orders are common; any notification logic must check hold status first
- Overwriting the snapshot key if a second hold is placed on the same account — use hold-scoped prefixes (`evidence/{holdId}/`) to preserve distinct capture points

## Gotchas
- `crypto.subtle.digest` in Workers returns an `ArrayBuffer`; convert via `new Uint8Array(hashBuffer)` before hex-encoding
- D1 does not enforce append-only natively — implement a CHECK constraint or application-layer guard to prevent UPDATE/DELETE on `legal_holds`
- R2 object metadata values are strings only; store numeric or structured values as JSON strings in `customMetadata`
- KV `expiration` takes a Unix epoch in **seconds**, not milliseconds — divide `Date.getTime()` by 1000

## Verification
1. POST a hold request and confirm a row in `legal_holds` and a KV key `hold:{accountId}` exist.
2. Run the deletion cron against an account under hold; assert the account is not soft-deleted and a row appears in `deletion_skips`.
3. Trigger the snapshot worker and confirm an R2 object exists at `evidence/{holdId}/{accountId}/snapshot.json` with a matching `sha256` in D1.
4. Verify the SHA-256 of the R2 object matches `snapshot_sha256` stored in D1 using an independent hash tool.

## Related
- [`platform-audit-log-immutable-d1-workers.md`](platform-audit-log-immutable-d1-workers.md)
- [`user-privacy-law-enforcement-requests.md`](user-privacy-law-enforcement-requests.md)
- [`gdpr-data-export-worker-r2-signed-url.md`](gdpr-data-export-worker-r2-signed-url.md)
- [`cross-border-data-localization-user-content.md`](cross-border-data-localization-user-content.md)

## Sources
- 18 U.S.C. § 2703(f) — Preservation of stored communications
- EU e-Evidence Regulation 2023/1543 — cross-border access to electronic evidence
- 18 U.S.C. § 2705 — Delayed notice
- Cloudflare R2 custom metadata and object storage documentation
