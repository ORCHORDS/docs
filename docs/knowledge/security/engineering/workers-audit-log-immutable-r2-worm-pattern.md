# Workers Audit Log with Immutable R2 WORM Pattern

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project must retain tamper-evident audit logs of moderation actions — post deletions, user bans, shadow-bans, and admin configuration changes — for compliance and forensic purposes. Logs stored in D1 can be silently altered by a rogue admin with database access. R2 object storage, with Object Lock / WORM semantics applied per-object, provides an append-only audit trail that cannot be modified or deleted without Cloudflare-level intervention.

## Context

Cloudflare R2 supports Object Lock (Write-Once-Read-Many) in compliance mode, preventing any principal — including the account owner — from overwriting or deleting a locked object before its retention period expires. Workers write one JSON log entry per audit event as an individual R2 object with a deterministic key. The key includes a cryptographic hash of the payload, making key forgery detectable.

## Threat Model

Without immutable logging, a malicious insider could:
- Delete a `DELETE FROM posts` entry from D1 to hide a moderation action.
- Overwrite a log entry to change who performed an action.
- Truncate a log table before an audit.

R2 WORM makes these attacks impossible without physically accessing Cloudflare infrastructure. HMAC-chaining of log entries makes out-of-order detection possible even if a non-locked bucket is used as a secondary index.

```typescript
// threat-model.ts
type InsiderRisk = "delete_log" | "overwrite_log" | "truncate_table";

const controls: Record<InsiderRisk, string> = {
  delete_log:      "R2 Object Lock compliance mode; no DELETE until retention_period",
  overwrite_log:   "Object key includes SHA-256 of payload; overwrite changes key",
  truncate_table:  "D1 index is optional; R2 is the authoritative store",
};
```

## R2 Bucket Configuration

```bash
# Enable Object Lock on the bucket (must be done at creation time)
wrangler r2 bucket create example project-audit-logs --jurisdiction=eu --object-lock

# Set a default retention rule (90 days compliance mode) via Cloudflare API
curl -X PUT "https://api.cloudflare.com/client/v4/accounts/{account_id}/r2/buckets/example project-audit-logs/lock" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [{
      "id": "default-90d",
      "enabled": true,
      "mode": "Compliance",
      "condition": { "type": "Age", "maxAgeSeconds": 7776000 }
    }]
  }'
```

## Audit Event Schema

```typescript
// audit-event.ts
export interface AuditEvent {
  event_id:    string;   // UUID v4
  ts:          number;   // epoch ms
  actor_sub:   string;   // admin subject (Access JWT sub)
  actor_email: string;
  action:      string;   // e.g. "post.delete", "user.ban"
  target_type: string;   // "post" | "user" | "config"
  target_id:   string;
  metadata:    Record<string, unknown>;
  prev_hash:   string;   // SHA-256 of previous log entry (chain)
}
```

## Immutable Write Implementation

Each event object key is `{DATE}/{HOUR}/{EVENT_ID}-{PAYLOAD_HASH_PREFIX}.json`. The payload hash in the key makes silent overwrite detectable — a different payload produces a different key.

```typescript
// audit-writer.ts
const enc = new TextEncoder();

async function sha256Hex(data: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", enc.encode(data));
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function writeAuditEvent(
  bucket: R2Bucket,
  event: AuditEvent,
  chainTipKey: KVNamespace  // stores the key of the latest entry for chaining
): Promise<string> {
  const payload = JSON.stringify(event);
  const payloadHash = await sha256Hex(payload);

  // Key: date-partitioned for range queries, hash suffix for integrity
  const d = new Date(event.ts);
  const date = d.toISOString().slice(0, 10);   // YYYY-MM-DD
  const hour = d.toISOString().slice(11, 13);  // HH
  const key = `${date}/${hour}/${event.event_id}-${payloadHash.slice(0, 12)}.json`;

  // Write with explicit retention header (per-object override, compliance mode)
  await bucket.put(key, payload, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: {
      event_id:    event.event_id,
      actor_email: event.actor_email,
      action:      event.action,
      payload_sha256: payloadHash,
    },
  });

  // Update chain tip in KV (eventually consistent; not part of the tamper-proof store)
  await chainTipKey.put("audit_chain_tip", key);

  return key;
}

export async function buildAuditEvent(
  action: string,
  targetType: string,
  targetId: string,
  actor: { sub: string; email: string },
  metadata: Record<string, unknown>,
  kv: KVNamespace
): Promise<AuditEvent> {
  const prevKey = await kv.get("audit_chain_tip") ?? "";
  const prevHash = prevKey ? await sha256Hex(prevKey) : "genesis";

  return {
    event_id:    crypto.randomUUID(),
    ts:          Date.now(),
    actor_sub:   actor.sub,
    actor_email: actor.email,
    action,
    target_type: targetType,
    target_id:   targetId,
    metadata,
    prev_hash:   prevHash,
  };
}
```

## Hardening — Async Fire-and-Forget with Tail Worker

Audit writes must not block the user-facing response. Use `ctx.waitUntil` for the R2 write, and mirror to a Tail Worker for real-time alerting.

```typescript
// handler.ts
export async function moderatePost(
  req: Request,
  env: Env,
  ctx: ExecutionContext,
  auth: AuthContext
): Promise<Response> {
  const { postId } = await req.json<{ postId: string }>();

  // Business logic first
  await env.DB.prepare("UPDATE posts SET deleted=1 WHERE id=?").bind(postId).run();

  // Non-blocking audit write
  ctx.waitUntil((async () => {
    const event = await buildAuditEvent(
      "post.delete",
      "post",
      postId,
      auth,
      { reason: "moderation" },
      env.AUDIT_KV
    );
    await writeAuditEvent(env.AUDIT_BUCKET, event, env.AUDIT_KV);
  })());

  return new Response(JSON.stringify({ deleted: true }));
}
```

## Monitoring — Chain Integrity Verification

A nightly cron Worker reads the last 1000 log entries and verifies the hash chain. Any gap or hash mismatch raises an alert.

```typescript
// chain-verifier.ts
export async function verifyRecentChain(
  bucket: R2Bucket,
  since: Date
): Promise<{ ok: boolean; broken_at?: string }> {
  const prefix = since.toISOString().slice(0, 10);
  const listed = await bucket.list({ prefix, limit: 1000 });

  let prevHash = "genesis";
  for (const obj of listed.objects.sort((a, b) => a.key.localeCompare(b.key))) {
    const body = await bucket.get(obj.key);
    if (!body) return { ok: false, broken_at: obj.key };

    const text = await body.text();
    const event = JSON.parse(text) as AuditEvent;

    if (event.prev_hash !== prevHash) {
      return { ok: false, broken_at: obj.key };
    }

    // Verify payload hash matches key suffix
    const computed = await sha256Hex(text);
    const keySuffix = obj.key.split("-").pop()?.replace(".json", "");
    if (!computed.startsWith(keySuffix ?? "")) {
      return { ok: false, broken_at: obj.key };
    }

    prevHash = await sha256Hex(obj.key);
  }
  return { ok: true };
}
```

## Anti-patterns

- Writing audit logs to D1 only — a privileged DB admin can modify rows.
- Using a shared R2 bucket without Object Lock — objects can be deleted.
- Logging to R2 synchronously in the request path — adds latency and can cause timeouts.
- Storing PII (e.g., full post content) in audit logs without encryption — GDPR right-to-erasure conflicts with WORM retention.
- Using a mutable key scheme (e.g., `logs/{date}/latest.json`) — allows silent overwrite by replacing the object at the same key before the lock interval activates.

## Gotchas

- R2 Object Lock must be enabled at bucket creation; it cannot be added to an existing bucket.
- Compliance mode prevents deletion even by the account owner — test the retention period in a separate dev bucket before applying to production.
- `ctx.waitUntil` extends the Worker lifetime but has a maximum of 30 seconds; large batch writes may time out.
- The KV chain tip is not WORM-protected — it is a convenience index only. The authoritative chain is reconstructed by reading R2 objects in sorted key order.
- GDPR erasure requests: encrypt personal data in the `metadata` field with a per-user key and destroy the key on erasure request — the ciphertext remains but is unintelligible.

## Verification

```bash
# Confirm Object Lock is active on the bucket
curl "https://api.cloudflare.com/client/v4/accounts/{account_id}/r2/buckets/example project-audit-logs/lock" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq .

# Write a test event and confirm it appears
wrangler r2 object get example project-audit-logs/{date}/{hour}/{event_id}-*.json

# Attempt to delete the object (should fail with 403 / locked error)
wrangler r2 object delete example project-audit-logs/{key}

# Run the chain verifier cron locally
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+0+*+*+*"
```

## Related

- /documentation/docs/policies/security/audit-log-security.md
- /documentation/docs/policies/security/r2-bucket-public-exposure-audit.md
- /documentation/docs/policies/security/r2-presigned-url-security.md
- /documentation/docs/policies/security/security-logging-what-to-log.md
- /documentation/docs/policies/security/workers-tail-workers-security-event-streaming.md

## Sources

- https://developers.cloudflare.com/r2/buckets/object-lock/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- https://www.nist.gov/publications/guide-computer-security-log-management
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
