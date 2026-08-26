# Email Forwarding Loop Detection with D1 and Email Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A forwarded email bounces between two or more addresses indefinitely because each endpoint has a forwarding rule pointing back. This exhausts resources and causes delivery failures. You need to detect and break the loop before it propagates.

## Context

Cloudflare Email Workers intercept inbound mail. Each message carries a `Message-ID` header that is stable across hops. By recording every `(message_id, hop_number, from_addr, to_addr)` in D1, you can detect when the same `message_id` has been seen more than a configurable maximum number of times, then reject the message. The max-hop policy is stored in KV so it can be updated without redeployment.

Requirements:
- Email Worker with `email` event handler
- D1 database bound as `DB`
- KV namespace bound as `POLICY_KV`

## D1 Schema

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS forwarding_hops (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id    TEXT    NOT NULL,
  hop_number    INTEGER NOT NULL,
  from_addr     TEXT    NOT NULL,
  to_addr       TEXT    NOT NULL,
  forwarded_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_hops_msgid ON forwarding_hops(message_id);
```

## Email Worker — Loop Detection

```typescript
import type { EmailMessage } from 'cloudflare:email';

export interface Env {
  DB: D1Database;
  POLICY_KV: KVNamespace;
}

const DEFAULT_MAX_HOPS = 5;
const FORWARD_TO = 'internal@yourdomain.com';

export default {
  async email(message: EmailMessage, env: Env): Promise<void> {
    const messageId = message.headers.get('Message-ID') ?? `generated-${Date.now()}-${Math.random()}`;
    const fromAddr = message.from;
    const toAddr = message.to;

    // Retrieve policy from KV (falls back to default)
    const maxHopsRaw = await env.POLICY_KV.get('max_hops');
    const maxHops = maxHopsRaw ? parseInt(maxHopsRaw, 10) : DEFAULT_MAX_HOPS;

    // Count existing hops for this message_id
    const countResult = await env.DB.prepare(
      `SELECT COUNT(*) AS cnt FROM forwarding_hops WHERE message_id = ?`
    ).bind(messageId).first<{ cnt: number }>();

    const hopCount = countResult?.cnt ?? 0;

    if (hopCount >= maxHops) {
      // Loop detected — reject the message
      message.setReject(`Loop detected: message_id ${messageId} seen ${hopCount} times (max ${maxHops})`);
      console.warn(`[loop-detect] Rejected ${messageId} after ${hopCount} hops`);
      return;
    }

    // Record this hop
    const nextHop = hopCount + 1;
    await env.DB.prepare(
      `INSERT INTO forwarding_hops (message_id, hop_number, from_addr, to_addr)
       VALUES (?, ?, ?, ?)`
    ).bind(messageId, nextHop, fromAddr, toAddr).run();

    // Add X-Loop-Counter header and forward
    const headers = new Headers({
      'X-Loop-Counter': String(nextHop),
      'X-Original-Message-ID': messageId,
    });

    await message.forward(FORWARD_TO, headers);
    console.info(`[loop-detect] Forwarded ${messageId} hop ${nextHop}/${maxHops} -> ${FORWARD_TO}`);
  },
};
```

## wrangler.toml Configuration

```toml
name = "loop-detect-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[send_email]
binding = "SEND_EMAIL"

[[d1_databases]]
binding = "DB"
database_name = "loop-detect-db"
database_id = "<your-d1-id>"

[[kv_namespaces]]
binding = "POLICY_KV"
id = "<your-kv-id>"

[triggers]
email_routing = true
```

## Updating the Max-Hop Policy via KV

```bash
# Set max hops to 3 without redeploying the Worker
wrangler kv key put --namespace-id <your-kv-id> max_hops 3

# Read the current policy
wrangler kv key get --namespace-id <your-kv-id> max_hops
```

## Pruning Old Hop Records

Add a Cron Trigger to delete records older than 7 days to keep D1 lean:

```typescript
async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
  await env.DB.prepare(
    `DELETE FROM forwarding_hops WHERE forwarded_at < datetime('now', '-7 days')`
  ).run();
}
```

```toml
# Add to wrangler.toml
[triggers]
crons = ["0 3 * * *"]
```

## Anti-patterns

- Do not rely solely on `Received` header count — that header can be stripped or forged.
- Do not use an in-memory counter; Workers are stateless and may run on different machines per request.
- Do not set `max_hops` to 1; legitimate mailing lists add one hop, so a minimum of 3 is sensible.
- Do not catch and silently discard the rejection — log it so loop origins can be investigated.

## Gotchas

- `message.headers.get('Message-ID')` may be `null` for malformed mail; always have a fallback ID.
- `message.setReject()` must be called before any `await` that yields to the event loop — call it as early as possible once the decision is made.
- `message.forward()` is fire-and-forget from the worker's perspective; errors surface as delivery failures, not thrown exceptions.
- D1 `COUNT(*)` is synchronous within a single query but still counts against D1 row-read limits.

## Verification

```bash
# Check hop records in D1
wrangler d1 execute loop-detect-db \
  --command "SELECT message_id, hop_number, from_addr, to_addr FROM forwarding_hops ORDER BY forwarded_at DESC LIMIT 10;"

# Simulate by sending test emails in a loop and observing wrangler tail output
wrangler tail loop-detect-worker --format pretty

# Confirm rejection in Email Routing activity log in the Cloudflare dashboard
```

## Related

- `email-alias-routing-kv-workers.md`
- `email-smtp-pipeline-workers-queues.md`
- [Cloudflare Email Workers docs](https://developers.cloudflare.com/email-routing/email-workers/)
- [Cloudflare D1 docs](https://developers.cloudflare.com/d1/)

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
