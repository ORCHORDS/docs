# Workers Secrets Store Scoped Access Binding Pattern

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Your Workers share secrets through `wrangler.toml` plain-text vars or KV-backed manual rotation scripts. When the secret set grows across dozens of services you need centralized lifecycle management, audit trails, and least-privilege scoping so that a compromised Worker cannot read secrets it never needs.

Cloudflare Secrets Store (GA 2025) provides a managed vault with per-secret binding granularity. This article covers the binding pattern that restricts each Worker to only the secrets it explicitly declares, plus the rotation and audit workflow around it.

---

## Context

Cloudflare Secrets Store stores named secrets encrypted at rest with AEAD (XChaCha20-Poly1305) inside Cloudflare's key management service. Secrets are exposed to Workers via **bindings** declared in `wrangler.toml` — the Worker runtime injects them as environment variables at cold-start. The binding layer is the security boundary: a Worker without a binding for `STRIPE_SECRET_KEY` cannot reach that value even if it runs in the same account.

Key properties:
- Secrets never appear in `wrangler.toml` values — only binding names appear.
- Secret *values* are written once through the Cloudflare dashboard or `wrangler secret put` and are opaque to the deploy pipeline.
- Rotation updates the value in the Store; bound Workers pick up the new value on the next isolate cold-start (typically within 30 s under high traffic).
- Access audit logs are available via Cloudflare Logpush to R2 or a SIEM.

---

## Declaring Scoped Bindings in wrangler.toml

Only list the secrets this specific Worker actually needs. Do not create a catch-all binding that exposes the entire store namespace.

```toml
# wrangler.toml — payment-processor Worker
name = "payment-processor"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[secrets_store.bindings]]
binding = "STRIPE_SECRET_KEY"
secret_name = "stripe/production/secret-key"

[[secrets_store.bindings]]
binding = "WEBHOOK_SIGNING_SECRET"
secret_name = "stripe/production/webhook-secret"

# NOT bound here: database credentials, SendGrid key, etc.
```

The Worker runtime exposes `env.STRIPE_SECRET_KEY` as a string. Any secret not listed in `[[secrets_store.bindings]]` is unreachable.

---

## Reading Secrets at Runtime

```typescript
export interface Env {
  STRIPE_SECRET_KEY: string;
  WEBHOOK_SIGNING_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Secrets are injected as plain strings — no async fetch required.
    const stripe = new StripeClient(env.STRIPE_SECRET_KEY);

    const sig = request.headers.get("stripe-signature") ?? "";
    const body = await request.text();

    try {
      const event = stripe.webhooks.constructEvent(
        body,
        sig,
        env.WEBHOOK_SIGNING_SECRET
      );
      return handleStripeEvent(event);
    } catch (err) {
      return new Response("Signature verification failed", { status: 400 });
    }
  },
};
```

Secrets are strings in the isolate scope — never log them or include them in error responses.

---

## Zero-Downtime Rotation Workflow

Cloudflare Secrets Store uses a two-phase rotation model compatible with upstream service key rotation:

```typescript
// rotation-helper.ts — run as a one-off script or Cron Trigger
export async function rotateStripeKey(env: Env): Promise<void> {
  // Phase 1: create new key at the upstream (Stripe)
  const newKey = await createStripeRestrictedKey();

  // Phase 2: write to Secrets Store via REST API (from a privileged Worker or CI)
  const url =
    "https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/secrets_store/secrets/stripe%2Fproduction%2Fsecret-key";

  const resp = await fetch(url, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ value: newKey }),
  });

  if (!resp.ok) {
    throw new Error(`Secrets Store write failed: ${resp.status}`);
  }

  // Phase 3: Workers pick up new value on next cold-start.
  // Phase 4: revoke old key at upstream after propagation window (≥ 60 s).
  await sleep(90_000);
  await revokeOldStripeKey();
}
```

The `CF_API_TOKEN` used here must have the `Secrets Store: Edit` permission and nothing else. Keep it in a separate Workers binding or CI environment variable, never embedded in application code.

---

## Namespace Isolation by Environment

Use secret name prefixes to separate production and staging secrets within the same account:

```toml
# Production worker
[[secrets_store.bindings]]
binding = "DB_PASSWORD"
secret_name = "myapp/production/db-password"

# Staging worker (separate wrangler.toml or environment stanza)
[env.staging]
[[env.staging.secrets_store.bindings]]
binding = "DB_PASSWORD"
secret_name = "myapp/staging/db-password"
```

The staging Worker **cannot** read `myapp/production/db-password` because the binding only maps to the staging secret name.

---

## Audit Logging via Logpush

Enable Secrets Store access logs to detect unexpected secret reads:

```bash
# Create a Logpush job for Secrets Store audit events
curl -X POST "https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "name": "secrets-store-audit",
    "logpull_options": "fields=SecretName,WorkerName,Timestamp,Action",
    "destination_conf": "r2://my-audit-bucket/secrets-audit?account-id={ACCOUNT_ID}",
    "dataset": "secrets_store_audit_logs",
    "enabled": true
  }'
```

Alert on any secret name accessed by a Worker that has no declared binding for it (indicates an API token compromise or misconfiguration).

---

## Anti-patterns

- **Wildcard prefix bindings** — do not create bindings for `myapp/*` if the Worker only needs one secret; the binding granularity is the control plane.
- **Storing secrets in KV or R2** — these lack at-rest encryption auditing and binding-level access control.
- **Logging `env.*` values** — Cloudflare Tail Workers may capture log lines; a secret printed to `console.log` leaks into the tail stream.
- **Using `vars` for rotating credentials** — `[vars]` values are visible in `wrangler.toml` and in the deploy diff; Secrets Store values are not.
- **Reusing the same secret name across tenants** — prefix secret names with tenant identifiers when operating multi-tenant accounts.

---

## Gotchas

- Secrets Store bindings inject values at isolate creation time. A rotation propagates on the *next* cold-start, not immediately. High-traffic Workers may hold stale values for up to 30 seconds during the propagation window.
- The Cloudflare REST API `PUT /secrets_store/secrets/{name}` requires URL-encoding of the secret name (slashes become `%2F`).
- `wrangler secret put` targets the legacy per-Worker encrypted environment; to write to the Secrets Store use `wrangler secrets-store secret put`.
- Secrets Store is available on Workers Paid plans only; free-tier Workers fall back to legacy `wrangler secret`.
- A deleted secret binding leaves `env.BINDING_NAME` as `undefined` at runtime — guard with a startup check.

---

## Verification

```typescript
// startup-check.ts — validate required secrets are present
export function assertRequiredSecrets(env: Env): void {
  const required: (keyof Env)[] = [
    "STRIPE_SECRET_KEY",
    "WEBHOOK_SIGNING_SECRET",
  ];
  const missing = required.filter(
    (k) => !env[k] || (env[k] as string).length === 0
  );
  if (missing.length > 0) {
    throw new Error(`Missing required secrets: ${missing.join(", ")}`);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    assertRequiredSecrets(env);
    // ...
  },
};
```

Run `wrangler dev --local` and intentionally omit a binding to confirm the startup check fires before any request is processed.

---

## Related

- `workers-environment-variable-hygiene.md`
- `api-key-rotation-workers-kv-secrets.md`
- `wrangler-cicd-secret-injection-hygiene.md`
- `multi-tenancy-isolation-workers-kv-d1.md`
- `secrets-encryption-at-rest.md`

---

## Sources

- Cloudflare Secrets Store documentation — https://developers.cloudflare.com/workers/configuration/secrets/
- Cloudflare Logpush datasets — https://developers.cloudflare.com/logs/reference/log-fields/
- Wrangler secrets commands — https://developers.cloudflare.com/workers/wrangler/commands/#secrets-store
- Cloudflare Workers runtime bindings reference — https://developers.cloudflare.com/workers/runtime-apis/bindings/
