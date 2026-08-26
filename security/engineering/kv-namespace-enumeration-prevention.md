# KV Namespace Enumeration Prevention

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
An attacker who gains read access to a Workers KV binding—or who can probe a public-facing Worker—can enumerate key names and infer sensitive data relationships, user IDs, or internal resource structure from the key-naming scheme alone.

## Context
Cloudflare Workers KV exposes `list()`, `get()`, and `getWithMetadata()` operations via the binding API. When key names are predictable (e.g. `user:12345:profile`) or when the `list()` operation is accessible via a Worker endpoint without access controls, an attacker can walk the entire namespace and reconstruct the data model without ever reading values.

---

## Key Design: Opaque, Non-Enumerable Keys

Never expose sequential or semantic keys in KV. Derive storage keys from a one-way function of the logical identifier, using a server-side secret. This makes keys unguessable from the outside, and the `list()` result useless without the secret.

```typescript
// env.KV: KVNamespace
// env.KV_KEY_SECRET: a 32-byte hex secret stored in Workers secrets

async function deriveKVKey(
  env: Env,
  namespace: string,
  logicalId: string
): Promise<string> {
  const encoder = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    hexToBytes(env.KV_KEY_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign(
    'HMAC',
    keyMaterial,
    encoder.encode(`${namespace}:${logicalId}`)
  );
  return `${namespace}:${bufferToHex(signature)}`;
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

function bufferToHex(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

// Usage:
export async function getProfile(env: Env, userId: string) {
  const kvKey = await deriveKVKey(env, 'profile', userId);
  return env.KV.get(kvKey, 'json');
}

export async function putProfile(env: Env, userId: string, data: unknown) {
  const kvKey = await deriveKVKey(env, 'profile', userId);
  await env.KV.put(kvKey, JSON.stringify(data), { expirationTtl: 86400 });
}
```

---

## Blocking the `list()` Vector in Worker Handlers

If any Worker endpoint exposes KV listing functionality, it must be guarded by authentication and scope. Never expose raw `list()` results to unauthenticated callers.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only allow list operations from internal service bindings or
    // requests with a verified admin JWT.
    if (new URL(request.url).pathname.startsWith('/admin/kv/list')) {
      const auth = request.headers.get('Authorization') ?? '';
      if (!isVerifiedAdminToken(auth, env.ADMIN_SECRET)) {
        return new Response('Forbidden', { status: 403 });
      }
      // Limit cursor-based listing to admin context only
      const { keys } = await env.KV.list({ limit: 100 });
      return Response.json({ keys: keys.map(k => k.name) });
    }
    // Normal application paths never call KV.list()
    return handleAppRequest(request, env);
  }
};

function isVerifiedAdminToken(auth: string, secret: string): boolean {
  const token = auth.replace('Bearer ', '');
  // In production, use full JWT verification; this is simplified
  return token.length > 0 && timingSafeEqual(token, secret);
}

function timingSafeEqual(a: string, b: string): boolean {
  const ea = new TextEncoder().encode(a);
  const eb = new TextEncoder().encode(b);
  if (ea.length !== eb.length) return false;
  let diff = 0;
  for (let i = 0; i < ea.length; i++) diff |= ea[i] ^ eb[i];
  return diff === 0;
}
```

---

## Metadata Scrubbing

KV `list()` returns key names AND metadata. Never store PII, user IDs, or relationship data in KV metadata—it is returned alongside keys in bulk list responses and is harder to protect than the value payload.

```typescript
// BAD: metadata reveals user relationship
await env.KV.put(key, value, {
  metadata: { userId: '12345', email: 'user@example.com', plan: 'pro' }
});

// GOOD: metadata is opaque, non-identifying
await env.KV.put(key, value, {
  expirationTtl: 3600,
  metadata: { schemaVersion: 2, createdAt: Date.now() }
});
```

---

## Namespace Prefix Partitioning with Access Control

When different tenants or services share a KV namespace, enforce prefix-based partitioning validated server-side. Never trust a client-supplied prefix.

```typescript
async function tenantScopedGet(
  env: Env,
  tenantId: string,
  subkey: string
): Promise<string | null> {
  // The tenantId comes from the verified JWT, never from the request URL
  const kvKey = await deriveKVKey(env, `tenant:${tenantId}`, subkey);
  return env.KV.get(kvKey);
}

async function tenantScopedList(
  env: Env,
  tenantId: string,
  cursor?: string
): Promise<KVNamespaceListResult<unknown, string>> {
  // Even with opaque keys, derive a deterministic prefix per tenant
  // so listing only returns that tenant's keys
  const prefixKey = await deriveKVKey(env, 'tenantprefix', tenantId);
  return env.KV.list({ prefix: prefixKey.slice(0, 16), cursor, limit: 50 });
}
```

---

## Anti-patterns

- Using `user:${userId}:data` as KV keys — the colon-delimited structure leaks schema on list.
- Storing email addresses or display names directly in KV key names.
- Exposing a `GET /kv/list` Worker endpoint without authentication.
- Using KV metadata to cache PII for performance, assuming metadata is "safer" than values.
- Assuming KV bindings in `wrangler.toml` with `preview_id` set are safe in CI logs — they expose namespace IDs.

---

## Gotchas

- KV `list()` with no prefix returns ALL keys in the namespace; it does not respect any implicit per-Worker scope.
- If you rotate the `KV_KEY_SECRET`, all derived keys change and existing values become unreachable. Implement a key migration strategy before rotating the secret.
- HMAC-SHA-256 output is 32 bytes (64 hex chars). KV key length is limited to 512 bytes — derived keys are well within limit but confirm if you prefix with long namespace strings.
- Cloudflare's KV Workers binding does not enforce read-only vs. read-write distinctions at the namespace level in free or paid plans (as of 2026); access control is entirely your Worker's responsibility.
- The `expirationTtl` metadata field IS visible in list responses via `getWithMetadata()` — do not use TTL values to encode business logic that you want hidden.

---

## Verification

1. Deploy the Worker with opaque HMAC-derived keys.
2. From the Cloudflare dashboard, use **KV → View** to manually list namespace keys and confirm they appear as hex digests with no semantic content.
3. Attempt to call your Worker's any endpoint as an unauthenticated user and verify `list()` paths return `403`.
4. Write a test that calls `list()` on the test namespace and asserts zero keys have readable semantic names:

```typescript
// Vitest + miniflare integration test
import { describe, it, expect } from 'vitest';

describe('KV key opacity', () => {
  it('stored keys contain no semantic identifiers', async () => {
    await putProfile(env, 'user123', { name: 'Alice' });
    const { keys } = await env.KV.list();
    for (const k of keys) {
      expect(k.name).not.toContain('user123');
      expect(k.name).not.toContain('profile');
      expect(/^[0-9a-f]{64}$/.test(k.name.split(':').pop()!)).toBe(true);
    }
  });
});
```

---

## Related

- `api-key-rotation-workers-kv-secrets.md`
- `multi-tenancy-isolation-workers-kv-d1.md`
- `workers-kv-ttl-token-revocation-expiry.md`
- `r2-object-key-enumeration-prevention.md`
- `workers-environment-variable-hygiene.md`

---

## Sources

- https://developers.cloudflare.com/kv/api/list-keys/
- https://developers.cloudflare.com/kv/reference/kv-namespaces/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#metadata
