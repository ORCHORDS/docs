# HMAC Webhook Signature Zero-Downtime Key Rotation

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Rotating a webhook shared secret breaks in-flight deliveries that the provider already signed with the old key before your endpoint switched. Providers such as GitHub and Stripe retry failed deliveries for up to 72 hours, so an atomic cut-over drops valid events. A grace-period dual-verification ring in Workers KV accepts both the old and new secret simultaneously, enabling zero-downtime rotation.

## Context

Webhook providers sign payloads with HMAC-SHA256 of a shared secret embedded in your endpoint configuration. When you update that secret, events dispatched moments before the change arrive carrying a valid old-key signature. Workers Secrets cannot hold two values simultaneously, but Workers KV can store a structured "secret ring" with per-secret activation and expiry timestamps. The endpoint iterates the ring and accepts any currently valid secret, then a cron job prunes expired entries after the provider's retry window closes.

## Secret Ring Schema and Helpers

```typescript
interface WebhookSecret {
  value: string;       // hex-encoded 32-byte secret
  label: string;       // human-readable "2026-08" for audit logs
  activatedAt: number; // epoch ms
  expiresAt: number;   // epoch ms — stop accepting after this
}

interface SecretRing {
  secrets: WebhookSecret[];
}

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    out[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return out;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

function extractSignatureHex(header: string): string | null {
  // GitHub: "sha256=<hex>"
  const gh = header.match(/^sha256=([0-9a-f]{64})$/i);
  if (gh) return gh[1];
  // Stripe: "t=<epoch>,v1=<hex>"
  const stripe = header.match(/v1=([0-9a-f]{64})/i);
  if (stripe) return stripe[1];
  return null;
}
```

## Dual-Verification Middleware

```typescript
async function verifyWebhookSignature(
  request: Request,
  rawBody: ArrayBuffer,
  env: Env,
): Promise<{ valid: boolean; label: string | null }> {
  const sigHeader = request.headers.get('X-Hub-Signature-256') ??
                    request.headers.get('Stripe-Signature');
  if (!sigHeader) return { valid: false, label: null };

  // Reject Stripe events older than 5 minutes to prevent replay
  const stripeTs = sigHeader.match(/t=(\d+)/)?.[1];
  if (stripeTs && Math.abs(Date.now() / 1000 - Number(stripeTs)) > 300) {
    return { valid: false, label: null };
  }

  const providedHex = extractSignatureHex(sigHeader);
  if (!providedHex) return { valid: false, label: null };

  // Cache secret ring in PoP for 60s to avoid KV read on every request
  const ring = await env.WEBHOOK_KV.get<SecretRing>('secret_ring', {
    type: 'json',
    cacheTtl: 60,
  });
  if (!ring) return { valid: false, label: null };

  const now = Date.now();
  const active = ring.secrets.filter(s => s.expiresAt > now);

  // Stripe includes the timestamp in the signed payload: "t=<ts>,v1=" signs "ts.body"
  const signedBody = stripeTs
    ? new TextEncoder().encode(`${stripeTs}.${new TextDecoder().decode(rawBody)}`)
    : rawBody;

  for (const secret of active) {
    const key = await crypto.subtle.importKey(
      'raw', hexToBytes(secret.value),
      { name: 'HMAC', hash: 'SHA-256' },
      false, ['verify'],
    );
    const ok = await crypto.subtle.verify(
      'HMAC', key, hexToBytes(providedHex), signedBody,
    );
    if (ok) return { valid: true, label: secret.label };
  }

  return { valid: false, label: null };
}
```

## Admin Rotation Endpoint

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Admin: rotate secret with configurable grace period
    if (request.method === 'POST' && url.pathname === '/admin/rotate-webhook') {
      if (request.headers.get('Authorization') !== `Bearer ${env.ADMIN_TOKEN}`) {
        return new Response('Unauthorized', { status: 401 });
      }

      const { gracePeriodHours = 72 } = await request.json<{ gracePeriodHours?: number }>();
      const gracePeriodMs = gracePeriodHours * 60 * 60 * 1000;
      const now = Date.now();

      const ring = await env.WEBHOOK_KV.get<SecretRing>('secret_ring', 'json') ?? { secrets: [] };

      // Expire existing secrets at the end of the grace period
      const trimmed = ring.secrets
        .map(s => ({ ...s, expiresAt: Math.min(s.expiresAt, now + gracePeriodMs) }))
        .filter(s => s.expiresAt > now);

      // Generate new 32-byte secret
      const newBytes = crypto.getRandomValues(new Uint8Array(32));
      const newSecret: WebhookSecret = {
        value: bytesToHex(newBytes),
        label: new Date(now).toISOString().slice(0, 7), // "2026-08"
        activatedAt: now,
        expiresAt: now + 365 * 24 * 60 * 60 * 1000, // 1-year nominal TTL
      };

      trimmed.push(newSecret);
      await env.WEBHOOK_KV.put('secret_ring', JSON.stringify({ secrets: trimmed }));

      return Response.json({
        rotated: true,
        newLabel: newSecret.label,
        newSecretHex: newSecret.value, // returned once — register with provider immediately
        gracePeriodExpiresAt: new Date(now + gracePeriodMs).toISOString(),
        activeSecretCount: trimmed.length,
      });
    }

    // Normal webhook ingestion path
    const rawBody = await request.arrayBuffer();
    const { valid, label } = await verifyWebhookSignature(request, rawBody, env);

    if (!valid) {
      return new Response('Forbidden', { status: 403 });
    }

    console.log(`Webhook accepted`, { label, url: request.url });

    const payload = JSON.parse(new TextDecoder().decode(rawBody));
    await env.EVENTS_QUEUE.send(payload);
    return new Response('OK', { status: 200 });
  },

  // Cron: prune fully-expired secrets from the ring
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const ring = await env.WEBHOOK_KV.get<SecretRing>('secret_ring', 'json');
    if (!ring) return;
    const now = Date.now();
    const live = ring.secrets.filter(s => s.expiresAt > now);
    if (live.length !== ring.secrets.length) {
      await env.WEBHOOK_KV.put('secret_ring', JSON.stringify({ secrets: live }));
      console.log(`Pruned ${ring.secrets.length - live.length} expired webhook secrets`);
    }
  },
};
```

## Anti-patterns

- Performing an atomic secret swap with no grace period — drops all events in transit at the moment of rotation
- Retaining old secrets indefinitely — negates rotation security; prune after the provider retry window closes
- Comparing signature hex strings with `===` — string equality is not constant-time; use `SubtleCrypto.verify()` exclusively

## Gotchas

- The `newSecretHex` value in the admin response is a credential — treat the admin endpoint itself as a privileged operation requiring separate access control; rotate the `ADMIN_TOKEN` independently
- KV `cacheTtl` of 60 seconds means a freshly rotated secret may not be visible at all PoPs for up to a minute; size the grace period generously (72 h is safe for all major providers)
- When testing rotation, use the provider's webhook replay feature (GitHub: "Redeliver"; Stripe: "Resend") to simulate in-flight events signed with the old key

## Verification

```bash
# Rotate and capture new secret
NEW_HEX=$(curl -s -X POST https://api.example.com/admin/rotate-webhook \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gracePeriodHours":72}' | jq -r .newSecretHex)

# Sign a test payload with the new secret
PAYLOAD='{"action":"test"}'
SIG=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 -hmac "$(echo "$NEW_HEX" | xxd -r -p)" -hex | awk '{print $2}')
curl -s -X POST https://api.example.com/webhook \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  -H "Content-Type: application/json" -d "$PAYLOAD"

# Must return 200 OK; old-key events sent during grace period must also return 200
```

## Related

- `security/webhook-signature-verification-hmac.md`
- `security/api-key-rotation-zero-downtime.md`
- `security/idempotency-one-time-secret-replay.md`

## Sources

- https://docs.github.com/en/webhooks/using-webhooks/securing-your-webhooks
- https://stripe.com/docs/webhooks/best-practices
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/#cachettl-parameter
