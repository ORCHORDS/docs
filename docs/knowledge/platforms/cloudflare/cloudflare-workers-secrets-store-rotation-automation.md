# Cloudflare Workers Secrets Store Automated Rotation

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Rotating secrets without redeploying Workers or causing request failures

Long-lived static secrets (API keys, DB passwords, signing keys) are a primary breach vector.
The naive Cloudflare Workers approach — `wrangler secret put` followed by a redeploy — causes a
brief window where some Worker instances hold the old value and some the new one, breaking
in-flight requests that rely on secret consistency (e.g., HMAC verification, mTLS).

Cloudflare Workers Secrets Store decouples secret values from Worker deployments. Workers read
secrets at request time via a binding, so updating a secret in the Store propagates globally
within seconds without any redeploy. A Cron Trigger Worker handles automated rotation: it fetches
the new secret from an external vault (AWS Secrets Manager or HashiCorp Vault), writes it to the
Secrets Store, and writes an audit row to D1. The old value remains readable until you explicitly
remove it, enabling a true zero-downtime dual-read window.

## Context

- Cloudflare Workers Secrets Store (GA as of 2025)
- External vault: AWS Secrets Manager (swap for Vault as needed)
- D1 database: `rotation-audit`
- Wrangler 3.x with `secrets_store` binding
- Rotation schedule: every 30 days via Cron Trigger

## D1 Rotation Audit Schema

```sql
-- wrangler d1 execute rotation-audit --file=schema.sql
CREATE TABLE IF NOT EXISTS rotation_log (
  id TEXT PRIMARY KEY,
  secret_name TEXT NOT NULL,
  rotated_at INTEGER NOT NULL DEFAULT (unixepoch()),
  rotated_by TEXT NOT NULL,        -- 'scheduled' | 'manual' | 'emergency'
  old_version TEXT,                -- Secrets Store version ID before rotation
  new_version TEXT,                -- Secrets Store version ID after rotation
  source TEXT NOT NULL,            -- 'aws-secrets-manager' | 'vault' | 'manual'
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'propagated' | 'failed'
  error_message TEXT
);

CREATE INDEX idx_rotation_secret ON rotation_log(secret_name, rotated_at DESC);
```

## Secrets Store Binding in wrangler.toml

```toml
# wrangler.toml
name = "secret-rotator"
main = "src/rotator.ts"
compatibility_date = "2026-08-01"

[triggers]
crons = ["0 3 1 * *"]   # first of every month at 03:00 UTC

[[secrets_store_namespaces]]
binding = "SECRETS"
id = "YOUR_SECRETS_STORE_NAMESPACE_ID"

[[d1_databases]]
binding = "AUDIT_DB"
database_name = "rotation-audit"
database_id = "YOUR_D1_ID"

# Secrets needed by the rotator itself (stored via wrangler secret put)
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
```

## AWS Secrets Manager Sync

```ts
// src/aws-client.ts
export async function getSecretFromAWS(
  secretId: string,
  env: { AWS_ACCESS_KEY_ID: string; AWS_SECRET_ACCESS_KEY: string; AWS_REGION: string }
): Promise<{ value: string; versionId: string }> {
  const region = env.AWS_REGION;
  const endpoint = `https://secretsmanager.${region}.amazonaws.com`;

  // AWS Signature V4 — simplified for Workers (no SDK needed)
  const body = JSON.stringify({ SecretId: secretId });
  const now = new Date();
  const dateStamp = now.toISOString().slice(0, 10).replace(/-/g, '');
  const amzDate = now.toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';

  const headers = await signRequest({
    method: 'POST',
    url: endpoint,
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': 'secretsmanager.GetSecretValue',
      'X-Amz-Date': amzDate,
      'Host': `secretsmanager.${region}.amazonaws.com`,
    },
    body,
    service: 'secretsmanager',
    region,
    accessKeyId: env.AWS_ACCESS_KEY_ID,
    secretAccessKey: env.AWS_SECRET_ACCESS_KEY,
    dateStamp,
    amzDate,
  });

  const response = await fetch(endpoint, { method: 'POST', headers, body });
  if (!response.ok) throw new Error(`AWS SM error: ${response.status} ${await response.text()}`);

  const data = await response.json() as { SecretString: string; VersionId: string };
  return { value: data.SecretString, versionId: data.VersionId };
}

// Minimal AWS SigV4 for Workers — real implementation uses Web Crypto
async function signRequest(params: {
  method: string; url: string; headers: Record<string,string>;
  body: string; service: string; region: string;
  accessKeyId: string; secretAccessKey: string;
  dateStamp: string; amzDate: string;
}): Promise<Record<string, string>> {
  // In production use a complete SigV4 implementation or aws4fetch package
  // bundled at build time via wrangler's esbuild step
  throw new Error('Implement SigV4 or bundle aws4fetch');
}
```

## Rotation Worker

```ts
// src/rotator.ts
interface Env {
  SECRETS: SecretsStoreNamespace;
  AUDIT_DB: D1Database;
  AWS_ACCESS_KEY_ID: string;
  AWS_SECRET_ACCESS_KEY: string;
  AWS_REGION: string;
}

// Map: Secrets Store key → AWS Secrets Manager ARN/name
const ROTATION_MAP: Record<string, string> = {
  'stripe-secret-key':  'prod/stripe/secret-key',
  'openai-api-key':     'prod/openai/api-key',
  'db-password':        'prod/postgres/password',
};

export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const trigger = 'scheduled';

    for (const [storeKey, awsSecretId] of Object.entries(ROTATION_MAP)) {
      const logId = crypto.randomUUID();
      try {
        // 1. Get current version from Secrets Store (for audit)
        const current = await env.SECRETS.get(storeKey);
        const oldVersion = current?.metadata?.version ?? null;

        // 2. Fetch new value from AWS Secrets Manager
        const { value: newValue, versionId } = await getSecretFromAWS(awsSecretId, env);

        // 3. Write new value to Secrets Store (propagates globally without redeploy)
        await env.SECRETS.put(storeKey, newValue);

        // 4. Audit log
        await env.AUDIT_DB.prepare(
          `INSERT INTO rotation_log(id,secret_name,rotated_by,old_version,new_version,source,status)
           VALUES(?,?,?,?,?,?,?)`
        ).bind(logId, storeKey, trigger, oldVersion, versionId, 'aws-secrets-manager', 'propagated').run();

        console.log(`Rotated ${storeKey} → version ${versionId}`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        await env.AUDIT_DB.prepare(
          `INSERT INTO rotation_log(id,secret_name,rotated_by,source,status,error_message)
           VALUES(?,?,?,?,?,?)`
        ).bind(logId, storeKey, trigger, 'aws-secrets-manager', 'failed', msg).run();
        console.error(`Rotation failed for ${storeKey}: ${msg}`);
      }
    }
  },

  // Manual rotation endpoint for break-glass emergency rotation
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
    const { secretKey } = await request.json<{ secretKey: string }>();
    if (!ROTATION_MAP[secretKey]) return new Response('Unknown secret', { status: 404 });

    const awsId = ROTATION_MAP[secretKey];
    const { value, versionId } = await getSecretFromAWS(awsId, env);
    await env.SECRETS.put(secretKey, value);

    await env.AUDIT_DB.prepare(
      `INSERT INTO rotation_log(id,secret_name,rotated_by,new_version,source,status)
       VALUES(?,?,?,?,?,?)`
    ).bind(crypto.randomUUID(), secretKey, 'manual', versionId, 'aws-secrets-manager', 'propagated').run();

    return Response.json({ ok: true, version: versionId });
  },
};
```

## Consumer Worker Reading from Secrets Store

```ts
// src/api-worker.ts — reads secret at request time, no redeploy needed after rotation
interface ConsumerEnv {
  SECRETS: SecretsStoreNamespace;
}

export default {
  async fetch(request: Request, env: ConsumerEnv): Promise<Response> {
    const stripeKey = await env.SECRETS.get('stripe-secret-key');
    if (!stripeKey) return new Response('Secret unavailable', { status: 503 });
    // Use stripeKey.value in API calls
    return new Response('ok');
  },
};
```

## Anti-patterns

- Do not rotate by running `wrangler secret put` in CI — it triggers a redeploy and causes version skew across the global Worker fleet
- Do not store the rotator's own AWS credentials in the Secrets Store it manages — use `wrangler secret put` for bootstrap credentials
- Do not rotate all secrets simultaneously — stagger rotations to limit blast radius if one fails
- Do not delete old Secrets Store versions immediately — keep for 24 h to allow in-flight requests to complete

## Gotchas

- Secrets Store `put()` propagates within ~30 s globally; ensure consumer Workers handle a 503 gracefully during that window
- The `SecretsStoreNamespace` type may require `@cloudflare/workers-types` 4.x or later
- AWS SigV4 signing in Workers requires Web Crypto — use `aws4fetch` bundled via esbuild, not the Node.js `aws-sdk`
- D1 `batch()` is preferred over individual inserts for audit rows when rotating many secrets at once

## Verification

```ts
// After rotation, confirm new value is live in consumer Worker
const res = await fetch('https://api.example.com/health');
// Inspect logs for: "Rotated stripe-secret-key → version xxxxxxxx"

// Query D1 audit for last 5 rotations
const rows = await env.AUDIT_DB.prepare(
  `SELECT secret_name, rotated_at, status, new_version
   FROM rotation_log ORDER BY rotated_at DESC LIMIT 5`
).all();
console.table(rows.results);
```

## Related

- documentation/docs/policies/cloudflare/secrets-store-binding-selection-and-blast-radius-control.md
- documentation/docs/policies/cloudflare/api-token-least-privilege-and-rotation-governance.md
- documentation/docs/policies/cloudflare/d1-best-practices.md
- documentation/docs/policies/cloudflare/workers-cron-triggers.md

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/secrets-store/
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
