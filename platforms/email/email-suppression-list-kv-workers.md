# Global Suppression List with Cloudflare Workers KV

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Emails sent to addresses that previously hard-bounced or unsubscribed damage sender reputation and violate CAN-SPAM/GDPR. A centralized suppression check in front of every sending path ensures no suppressed address is ever sent to, regardless of which ESP or queue processes the message.

## Context
Cloudflare Workers KV provides globally replicated, sub-millisecond reads — ideal for a suppression list that must be consulted on every outbound send. Unlike a D1 database (strong consistency, higher latency), KV's eventual consistency model is acceptable here because false negatives (briefly missing a suppression) are far less harmful than blocking the entire send pipeline with DB latency. Suppressions are written with a reason code and timestamp and optionally expire for soft suppressions.

## KV Schema and Key Design

Keys follow `suppress:{normalized_email}` to enable O(1) lookup without scanning. Values are JSON-encoded metadata to support auditing.

```typescript
interface SuppressionRecord {
  reason: "hard_bounce" | "spam_complaint" | "unsubscribe" | "manual";
  source: string;        // e.g. "ses-bounce-webhook", "postmark-complaint"
  suppressedAt: string;  // ISO-8601
  expiresAt?: string;    // ISO-8601; absent means permanent
}

function suppressionKey(email: string): string {
  return `suppress:${email.trim().toLowerCase()}`;
}
```

## Writing a Suppression

Suppressions are written by webhook handlers (bounce, complaint) and by the unsubscribe flow. Permanent suppressions omit `expirationTtl`; soft suppressions (e.g., temporary blocks) expire automatically.

```typescript
export interface Env {
  SUPPRESSION_LIST: KVNamespace;
}

async function suppress(
  email: string,
  record: SuppressionRecord,
  kv: KVNamespace,
  ttlSeconds?: number
): Promise<void> {
  const key = suppressionKey(email);
  const value = JSON.stringify(record);
  const opts = ttlSeconds ? { expirationTtl: ttlSeconds } : undefined;
  await kv.put(key, value, opts);
}

// Example: called from a hard-bounce webhook
async function handleHardBounce(email: string, env: Env): Promise<void> {
  await suppress(
    email,
    {
      reason: "hard_bounce",
      source: "ses-bounce-webhook",
      suppressedAt: new Date().toISOString(),
    },
    env.SUPPRESSION_LIST
    // No TTL — permanent suppression
  );
}
```

## Checking Suppression Before Send

Every outbound send path must call `isSuppressed` before dispatching to the ESP. Return the reason so the caller can log it appropriately.

```typescript
async function isSuppressed(
  email: string,
  kv: KVNamespace
): Promise<SuppressionRecord | null> {
  const key = suppressionKey(email);
  const raw = await kv.get(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SuppressionRecord;
  } catch {
    // Corrupted entry — treat as suppressed and re-write a sentinel
    return {
      reason: "manual",
      source: "parse-error-sentinel",
      suppressedAt: new Date().toISOString(),
    };
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { email, template, data } = await request.json<{
      email: string;
      template: string;
      data: Record<string, string>;
    }>();

    const suppression = await isSuppressed(email, env.SUPPRESSION_LIST);
    if (suppression) {
      return Response.json(
        { skipped: true, reason: suppression.reason },
        { status: 200 }
      );
    }

    // Dispatch to ESP…
    return Response.json({ sent: true });
  },
};
```

## Bulk Import via Wrangler KV Bulk API

Seeding the suppression list from an existing ESP export can be done with the Wrangler bulk-write endpoint. The following script prepares a JSON payload compatible with the `PUT /bulk` API.

```typescript
// run as a local script with Node.js before deploying
import { readFileSync, writeFileSync } from "node:fs";

const emails: string[] = readFileSync("existing-suppressions.csv", "utf8")
  .split("\n")
  .map((l) => l.trim().toLowerCase())
  .filter((l) => l.includes("@"));

const kvPairs = emails.map((email) => ({
  key: `suppress:${email}`,
  value: JSON.stringify({
    reason: "manual",
    source: "bulk-import-2026-08-23",
    suppressedAt: new Date().toISOString(),
  } satisfies SuppressionRecord),
}));

writeFileSync("suppression-bulk.json", JSON.stringify(kvPairs));
// Then: wrangler kv:bulk put --binding SUPPRESSION_LIST suppression-bulk.json
```

## Removing a Suppression (Re-subscribe)

Honour explicit re-subscribe requests by deleting the KV key. Log the deletion for the audit trail before removing.

```typescript
async function removeSuppressionWithAudit(
  email: string,
  requestedBy: string,
  kv: KVNamespace
): Promise<void> {
  const existing = await isSuppressed(email, kv);
  if (!existing) return; // nothing to remove

  console.log(JSON.stringify({
    event: "suppression_removed",
    email,
    requestedBy,
    previousReason: existing.reason,
    removedAt: new Date().toISOString(),
  }));

  await kv.delete(suppressionKey(email));
}
```

## Anti-patterns
- Checking suppression only in the ESP integration layer — bypassed when switching providers or using multiple queues
- Using a D1 query per send at high throughput — KV reads are cheaper and globally consistent for this read-heavy workload
- Suppressing on soft bounces without a retry counter — legitimate servers may be temporarily offline
- Not normalising email addresses before key construction (e.g., `User@EXAMPLE.COM` and `user@example.com` becoming different keys)

## Gotchas
- KV is eventually consistent — a suppression written in one region may take up to 60 seconds to propagate worldwide; acceptable for post-delivery events but not for real-time revocation
- KV `list()` is not suitable for iterating all suppressions at scale — use an R2-backed CSV export for reporting
- Workers free tier has KV write limits; high-complaint campaigns can spike writes unexpectedly

## Verification
1. POST a send request for a suppressed address — confirm response contains `{ skipped: true, reason: "hard_bounce" }`
2. Inspect KV namespace in the Cloudflare dashboard — verify key `suppress:test@example.com` with correct JSON
3. Call `removeSuppressionWithAudit`, then resend — confirm the message is dispatched
4. Run the bulk import script with a 10-address test CSV and verify all keys appear in the KV namespace

## Related
- `/documentation/categories/email/bounce-suppression-d1.md`
- `/documentation/categories/email/email-cross-esp-suppression-sync-d1.md`
- `/documentation/categories/email/suppression-list-management.md`
- `/documentation/categories/email/one-click-unsubscribe-rfc8058-gdpr.md`

## Sources
- Cloudflare Workers KV documentation: https://developers.cloudflare.com/kv/
- RFC 5321 §3.7 — Mail Forwarding and Delivery Status
- CAN-SPAM Act 15 U.S.C. § 7704 — unsubscribe honouring within 10 business days
