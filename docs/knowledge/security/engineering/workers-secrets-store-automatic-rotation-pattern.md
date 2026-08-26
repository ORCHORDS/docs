# Workers Secrets Store Automatic Rotation Pattern

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A third-party API key or database password is hardcoded into `wrangler.toml` or set once
via `wrangler secret put` and never changed. When the secret leaks you have manual
scramble-and-redeploy instead of a tested rotation procedure that runs automatically.

## Context

Cloudflare Workers Secrets Store (available to Workers Standard and above) lets Workers
read secrets at runtime without a redeploy. Pairing the Secrets Store API with a scheduled
Cron Trigger produces a self-healing rotation loop: a Cron Worker fetches a new credential
from the upstream provider, writes it into the Secrets Store, and records the rotation event
in D1 — all without touching `wrangler.toml` or triggering a deploy pipeline.

The consuming Worker reads the secret at request time, not at startup, so it sees the new
value on the very next request after the Secrets Store write completes.

---

## Secrets Store setup (wrangler.toml)

```toml
[[secrets_store_secrets]]
binding  = "SECRETS"          # env.SECRETS in Worker code
store_id = "abc123def456"     # from `wrangler secrets-store create`
```

Workers that only need to *read* a secret reference the binding; the rotation Worker needs
the **Secrets Store REST API** and a Cloudflare API token scoped to `Secrets Store: Edit`.

---

## Consuming a secret at request time

```typescript
interface Env {
  SECRETS: SecretsStore;   // injected by the runtime
}

// SecretsStore is a runtime binding; no npm import needed
interface SecretsStore {
  get(name: string): Promise<string | null>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const dbPassword = await env.SECRETS.get('DB_PASSWORD');
    if (!dbPassword) return new Response('Secret missing', { status: 500 });
    // Use dbPassword to build a connection string or auth header
    return handleRequest(request, dbPassword);
  },
};
```

---

## Rotation Worker: fetching a new secret from the provider

```typescript
const CF_API_BASE = 'https://api.cloudflare.com/client/v4';

async function fetchNewCredentialFromProvider(env: RotationEnv): Promise<string> {
  // Example: AWS Secrets Manager, Vault, or your own credential vending service
  const resp = await fetch(env.CREDENTIAL_VENDING_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${await env.SECRETS.get('VENDING_TOKEN')}` },
  });
  if (!resp.ok) throw new Error(`Vending service error: ${resp.status}`);
  const { secret } = await resp.json<{ secret: string }>();
  return secret;
}

async function writeToSecretsStore(
  accountId: string,
  storeId: string,
  secretName: string,
  secretValue: string,
  cfToken: string,
): Promise<void> {
  const url = `${CF_API_BASE}/accounts/${accountId}/secrets_store/stores/${storeId}/secrets`;
  const resp = await fetch(url, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${cfToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify([{ name: secretName, value: secretValue, type: 'secret_text' }]),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Secrets Store write failed ${resp.status}: ${body}`);
  }
}
```

---

## Rotation Worker: orchestrator with D1 audit trail

```typescript
interface RotationEnv {
  SECRETS: SecretsStore;
  DB: D1Database;
  CF_ACCOUNT_ID: string;
  CF_SECRETS_STORE_ID: string;
  CF_API_TOKEN: string;        // stored as a Secrets Store secret itself
}

export default {
  async scheduled(_event: ScheduledEvent, env: RotationEnv, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(rotate(env));
  },
};

async function rotate(env: RotationEnv): Promise<void> {
  const secretName = 'DB_PASSWORD';
  const startedAt = Date.now();
  let status = 'ok';
  let errorMsg = '';

  try {
    const newSecret = await fetchNewCredentialFromProvider(env);
    const cfToken = await env.SECRETS.get('CF_API_TOKEN') ?? env.CF_API_TOKEN;
    await writeToSecretsStore(
      env.CF_ACCOUNT_ID, env.CF_SECRETS_STORE_ID, secretName, newSecret, cfToken,
    );
  } catch (err) {
    status = 'error';
    errorMsg = String(err);
    // Re-throw so the Cron infrastructure records the failure
    throw err;
  } finally {
    await env.DB.prepare(
      `INSERT INTO secret_rotation_log (secret_name, status, error, rotated_at)
       VALUES (?, ?, ?, ?)`,
    ).bind(secretName, status, errorMsg, startedAt).run();
  }
}
```

---

## Cron schedule (wrangler.toml)

```toml
[triggers]
crons = ["0 3 * * *"]   # Rotate daily at 03:00 UTC
```

Stagger rotations for different secrets by offset minutes to avoid a thundering-herd
against the vending service.

---

## Dual-secret overlap window for zero-downtime rotation

Some upstreams (databases, third-party APIs) require the old credential to remain valid
during a transition period while existing connections drain.

```typescript
async function rotateDualSlot(env: RotationEnv): Promise<void> {
  // 1. Write new secret to the "next" slot
  const newSecret = await fetchNewCredentialFromProvider(env);
  await writeToSecretsStore(
    env.CF_ACCOUNT_ID, env.CF_SECRETS_STORE_ID, 'DB_PASSWORD_NEXT', newSecret, env.CF_API_TOKEN,
  );

  // 2. Sleep 5 minutes to let in-flight requests finish (Workers can use ctx.waitUntil)
  await new Promise(r => setTimeout(r, 5 * 60 * 1000));

  // 3. Promote: write new secret to canonical slot, remove old
  await writeToSecretsStore(
    env.CF_ACCOUNT_ID, env.CF_SECRETS_STORE_ID, 'DB_PASSWORD', newSecret, env.CF_API_TOKEN,
  );
}
```

The consuming Worker tries `DB_PASSWORD` first; a separate fallback path can try
`DB_PASSWORD_NEXT` during the overlap window if the primary connection fails auth.

---

## Anti-patterns

- **Rotating via `wrangler secret put` in a CI pipeline**: requires a deploy or at minimum exposes the new secret to CI environment logs.
- **Storing the CF API token in `wrangler.toml`** as a plain-text env var: it should itself be a Secrets Store secret, bootstrapped once manually.
- **No D1 audit trail**: without a log you cannot answer "when was this last rotated?" during an incident.
- **Immediate deletion of the old credential at the provider**: in-flight requests that fetched the old secret before rotation will fail until they complete.

## Gotchas

- Secrets Store `get()` calls count toward CPU time — cache the value in a module-level variable for the lifetime of the isolate if you call it on every request. The value is safe to cache for the isolate lifetime because isolate recycling already provides natural refresh.
- The Secrets Store REST API path (`/secrets_store/stores/{id}/secrets`) may differ from the Dashboard URL path; always derive paths from the official API docs.
- Cron Triggers have a 30-second wall-clock limit. If the vending service is slow, move the long-running rotation into a Queue message to avoid the timeout.

## Verification

```bash
# Check last rotation status from D1
wrangler d1 execute <DB_NAME> --command \
  "SELECT secret_name, status, error, datetime(rotated_at/1000, 'unixepoch') as rotated
   FROM secret_rotation_log ORDER BY rotated_at DESC LIMIT 10"
```

## Related

- `workers-secrets-store-scoped-binding.md`
- `api-key-rotation-zero-downtime.md`
- `api-key-rotation-workers-kv-secrets.md`
- `wrangler-cicd-secret-injection-hygiene.md`
- `workers-environment-variable-hygiene.md`

## Sources

- Cloudflare Workers Secrets Store — https://developers.cloudflare.com/workers/runtime-apis/secrets-store/
- Cloudflare Secrets Store REST API — https://developers.cloudflare.com/api/resources/secrets_store/
- NIST SP 800-57 Part 1 Rev 5 — Key Management Recommendations
