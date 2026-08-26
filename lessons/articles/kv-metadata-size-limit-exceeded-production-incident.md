# KV Metadata Size Limit Exceeded Production Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A session cache layer started returning HTTP 400 errors from Workers KV `put` calls. Error logs showed:

```
KV PUT failed: metadata value too large (1024 byte limit exceeded). Key: session:u_8f2a91c3
```

Approximately 12% of new login requests failed silently because the error was caught and swallowed by a generic try/catch. Users received successful auth responses but their session state was never persisted, causing them to be immediately logged out on the next request.

## Context

The team stored structured session metadata — user profile fields, feature flags, device info, A/B test assignments — directly in the KV `metadata` object alongside the session token. Over several product iterations, the metadata object grew from ~80 bytes to ~1.3 KB per key. Cloudflare Workers KV enforces a hard **1,024-byte limit on the serialized JSON metadata** per key. The value (session token) is separate and can be up to 25 MB, but metadata must stay under 1,024 bytes. The limit had never been documented in the team's onboarding material and no guard existed at write time.

## 1. Understanding the KV Metadata Limit

```typescript
// KV key anatomy
interface KVWriteOptions {
  expiration?: number;      // absolute Unix timestamp
  expirationTtl?: number;   // seconds from now
  metadata?: unknown;       // ← HARD LIMIT: JSON.stringify(metadata).length <= 1024 bytes
}

// What the team was storing (1,340 bytes serialized):
const metadata = {
  userId: "u_8f2a91c3",
  email: "user@example.com",
  displayName: "Firstname Lastname",
  avatarUrl: "https://cdn.example.com/avatars/u_8f2a91c3.png",
  plan: "pro",
  flags: { newDashboard: true, betaApi: false, earlyAccess: true },
  device: { ua: "Mozilla/5.0 ...", os: "macOS", browser: "Chrome" },
  abTests: { checkoutFlow: "variant_b", pricing: "control" },
  createdAt: "2026-08-23T10:22:00Z",
  lastSeen: "2026-08-23T14:05:12Z",
};
// JSON.stringify(metadata).length === 1340  ← EXCEEDS LIMIT
```

## 2. Detecting the Problem at Write Time

Add a guard that measures metadata size before every `put` call:

```typescript
const KV_METADATA_LIMIT = 1024;

export async function kvPutSafe<T>(
  kv: KVNamespace,
  key: string,
  value: string,
  options: { expirationTtl?: number; metadata?: T } = {}
): Promise<void> {
  if (options.metadata !== undefined) {
    const serialized = JSON.stringify(options.metadata);
    if (serialized.length > KV_METADATA_LIMIT) {
      throw new Error(
        `KV metadata too large for key "${key}": ${serialized.length} bytes (limit ${KV_METADATA_LIMIT}). ` +
          `Trim or move fields to the value body.`
      );
    }
  }
  await kv.put(key, value, options);
}
```

Use this wrapper everywhere instead of calling `kv.put` directly.

## 3. Restructuring the Data Model

Move large fields out of metadata and into the KV value body:

```typescript
interface SessionMetadata {
  // Keep only lightweight fields needed for list-without-read operations
  userId: string;
  plan: "free" | "pro" | "enterprise";
  expiresAt: number; // unix epoch seconds
}

interface SessionValue {
  token: string;
  email: string;
  displayName: string;
  avatarUrl: string;
  flags: Record<string, boolean>;
  device: { ua: string; os: string; browser: string };
  abTests: Record<string, string>;
  createdAt: string;
  lastSeen: string;
}

export async function writeSession(
  kv: KVNamespace,
  sessionId: string,
  meta: SessionMetadata,
  payload: SessionValue,
  ttlSeconds: number
): Promise<void> {
  const metaJson = JSON.stringify(meta);
  if (metaJson.length > KV_METADATA_LIMIT) {
    throw new Error(`Session metadata exceeds 1024 bytes: ${metaJson.length}`);
  }

  await kv.put(`session:${sessionId}`, JSON.stringify(payload), {
    expirationTtl: ttlSeconds,
    metadata: meta,
  });
}
```

With the restructured model, metadata is ~80 bytes. Full session data lives in the value body, read only when needed.

## 4. Listing Sessions Without Reading Values

A key reason to use metadata is enabling `list()` operations that return filtered results without fetching each value:

```typescript
export async function listUserSessions(
  kv: KVNamespace,
  userId: string
): Promise<Array<{ sessionId: string; expiresAt: number }>> {
  const { keys } = await kv.list<SessionMetadata>({
    prefix: `session:`,
    limit: 1000,
  });

  return keys
    .filter((k) => k.metadata?.userId === userId)
    .map((k) => ({
      sessionId: k.name.replace("session:", ""),
      expiresAt: k.metadata!.expiresAt,
    }));
}
```

This works because metadata is returned inline with `list()` — no extra `get()` per key.

## 5. Monitoring Metadata Size in CI

Add a test that constructs a representative metadata object and asserts it stays within budget:

```typescript
// tests/kv-metadata.test.ts
import { describe, it, expect } from "vitest";
import { buildSessionMetadata } from "../src/session";

const KV_METADATA_LIMIT = 1024;
const SAFETY_MARGIN = 0.85; // fail if >85% of budget used — leave room for growth

describe("KV session metadata size", () => {
  it("must not exceed 85% of the 1024-byte limit", () => {
    const meta = buildSessionMetadata({
      userId: "u_8f2a91c3deadbeef",
      plan: "enterprise",
      expiresAt: Date.now() / 1000 + 86400,
    });
    const size = JSON.stringify(meta).length;
    const budget = KV_METADATA_LIMIT * SAFETY_MARGIN;

    expect(size).toBeLessThan(budget);
    console.log(`Metadata size: ${size}/${KV_METADATA_LIMIT} bytes (${((size / KV_METADATA_LIMIT) * 100).toFixed(0)}% of limit)`);
  });
});
```

## Anti-patterns

- Treating KV metadata as a general-purpose secondary store. It is designed only for fields needed during `list()` without a `get()`.
- Serializing enum-like strings in full when an integer code would do (e.g., `"enterprise"` → `2`).
- Growing metadata across multiple PRs with no one owning the total size budget.
- Catching KV write errors with a blanket `catch` that swallows the failure silently.

## Gotchas

- `JSON.stringify(metadata).length` measures **UTF-8 character count**, not byte count. For metadata containing multibyte Unicode characters (e.g., non-Latin display names), use `new TextEncoder().encode(JSON.stringify(metadata)).length` for the accurate byte count.
- The 1,024-byte limit applies to the serialized metadata **after** Cloudflare's JSON encoding, which may differ from client-side `JSON.stringify` if the runtime re-serializes with different key ordering.
- `kv.list()` returns metadata inline, but `kv.get()` with `{ type: "json", cacheTtl: N }` does NOT return metadata — you must call `kv.getWithMetadata()` when you need both.
- Metadata is not encrypted at rest separately from the value. Do not store sensitive fields (tokens, PII) in metadata.

## Verification

```bash
# Spot-check a live key's metadata size after the fix
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces/$KV_ID/metadata/session:$SESSION_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq 'length'
```

```typescript
// Integration test: write and read back a session, assert no truncation
const meta: SessionMetadata = { userId: "u_test", plan: "pro", expiresAt: 9999999999 };
await writeSession(kv, "test-session-id", meta, payload, 3600);
const { metadata } = await kv.getWithMetadata<SessionMetadata>("session:test-session-id");
assert.deepEqual(metadata, meta, "Metadata round-trip failed");
```

## Related

- kv-write-rate-limit-exceeded-postmortem.md
- kv-consistency-mode-eventual-reads-production-bug.md
- kv-namespace-key-collision-multitenant-isolation-incident.md

## Sources

- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#metadata
- https://developers.cloudflare.com/kv/platform/limits/
- https://developers.cloudflare.com/kv/api/list-keys/
