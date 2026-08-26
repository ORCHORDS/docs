# Hyperdrive Connection String Secret Hygiene in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A team stores a Postgres connection string (including password) as a plaintext `wrangler.toml` variable or as a Worker environment variable instead of using a Cloudflare secret. Another team hard-codes the Hyperdrive binding name to a development database and ships it to production. Either mistake leaks credentials into `wrangler.toml` version control or misroutes production traffic to an unprotected dev database.

## Context

Cloudflare Hyperdrive accepts a `connectionString` at configuration time, then issues an internal binding (`env.HYPERDRIVE`) to Workers. The connection string contains a database hostname, port, user, and password. Because `wrangler deploy` uploads bindings in plaintext environment variables alongside secrets, it is easy to accidentally commingle them. The correct posture: the raw connection string lives only in a Cloudflare secret created via `wrangler secret put` or the dashboard API, and the Hyperdrive config is created by referencing that secret — never by pasting the URL into `wrangler.toml` directly.

## 1. Creating Hyperdrive via Secret Reference (CLI)

Never paste the full connection string into `wrangler.toml`. Instead create the Hyperdrive config referencing the secret:

```bash
# Store the connection string as a secret first
echo "postgresql://appuser:S3cr3tP@ssw0rd@db.internal:5432/prod" \
  | wrangler secret put DATABASE_URL

# Create Hyperdrive config — Cloudflare resolves the secret server-side
wrangler hyperdrive create prod-db \
  --connection-string "$(wrangler secret get DATABASE_URL 2>/dev/null || echo 'USE_SECRET')"
```

In `wrangler.toml`, reference only the binding name and Hyperdrive config ID:

```toml
[[hyperdrive]]
binding = "HYPERDRIVE"
id     = "abc123def456"   # Hyperdrive config ID, NOT the connection string
```

## 2. Using the Binding Safely in a Worker

```typescript
interface Env {
  HYPERDRIVE: Hyperdrive;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // env.HYPERDRIVE.connectionString is a TRANSIENT string issued per-request.
    // Never log it, cache it in KV, or return it in a response body.
    const db = await connectToDB(env.HYPERDRIVE.connectionString);
    const rows = await db.query("SELECT id FROM users WHERE id = $1", [userId]);
    return Response.json(rows);
  },
};

async function connectToDB(connStr: string) {
  // Use a Postgres driver that supports the Workers TCP socket API
  // e.g. postgres.js with `socket` option pointed at connect()
  const { Client } = await import("pg"); // bundled at build time
  const client = new Client({ connectionString: connStr });
  await client.connect();
  return client;
}
```

## 3. Detecting Leaked Connection Strings in CI

Add a pre-deploy check that fails the build if any plaintext credentials appear in `wrangler.toml`:

```typescript
// scripts/check-no-plaintext-creds.ts
import { readFileSync } from "fs";

const toml = readFileSync("wrangler.toml", "utf8");
const credentialPattern =
  /(?:postgres(?:ql)?|mysql|mongodb):\/\/[^:]+:[^@]+@/i;

if (credentialPattern.test(toml)) {
  console.error(
    "ERROR: Plaintext database credential found in wrangler.toml. " +
      "Use `wrangler secret put` and reference the Hyperdrive config ID instead."
  );
  process.exit(1);
}
console.log("OK: No plaintext credentials found in wrangler.toml.");
```

Run this in your CI pipeline before `wrangler deploy`.

## 4. Per-Environment Hyperdrive Config Isolation

Use separate Hyperdrive configs per environment so that a staging credential can never accidentally reach production:

```toml
[env.staging]
[[env.staging.hyperdrive]]
binding = "HYPERDRIVE"
id     = "staging-config-id-111"

[env.production]
[[env.production.hyperdrive]]
binding = "HYPERDRIVE"
id     = "production-config-id-999"
```

This ensures `wrangler deploy --env staging` and `wrangler deploy --env production` use completely separate Hyperdrive configs backed by separate secrets.

## 5. Rotating a Compromised Hyperdrive Credential

```bash
# 1. Revoke the old database password at the database level immediately.
# 2. Update the Cloudflare secret with the new password.
echo "postgresql://appuser:NewP@ssw0rd@db.internal:5432/prod" \
  | wrangler secret put DATABASE_URL

# 3. Update the Hyperdrive config to pick up the new secret.
wrangler hyperdrive update prod-db \
  --connection-string "$(wrangler secret get DATABASE_URL 2>/dev/null)"

# 4. Verify Hyperdrive health.
wrangler hyperdrive get prod-db
```

Because Hyperdrive maintains a connection pool, the old connections drain within seconds of the config update; no Worker redeploy is required.

## 6. Audit: Listing Hyperdrive Configs Programmatically

```typescript
// audit-hyperdrive.ts — run via `wrangler dev` or as a cron Worker
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.ACCOUNT_ID}/hyperdrive/configs`,
      { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
    );
    const { result } = (await resp.json()) as { result: HyperdriveConfig[] };

    for (const cfg of result) {
      // Ensure no config is still pointing to a dev/staging hostname in production
      if (
        cfg.origin.host.includes("dev") ||
        cfg.origin.host.includes("staging")
      ) {
        console.warn(`AUDIT FAIL: Hyperdrive config ${cfg.id} points to non-prod host ${cfg.origin.host}`);
      }
    }
  },
};
```

## Anti-patterns

- Storing the full `postgresql://user:pass@host/db` string in `wrangler.toml` or as a plain `[vars]` entry — it appears in `wrangler.toml` diffs, CI logs, and the Workers dashboard.
- Logging `env.HYPERDRIVE.connectionString` — it exposes the transient credential to log drains.
- Sharing one Hyperdrive config across staging and production environments.
- Using `wrangler secret get` in application code to reconstruct the connection string at runtime — defeats the purpose of Hyperdrive's managed pooling.

## Gotchas

- `env.HYPERDRIVE.connectionString` changes per Worker invocation (it is a one-time token); do not cache it in a module-level variable.
- `wrangler hyperdrive create` does not accept `--connection-string` from an already-stored Cloudflare secret by name — you must resolve the secret value first (CI pipeline) or paste it interactively. Never persist this resolved value in logs.
- Hyperdrive configs store the credential on Cloudflare's side. If you delete and recreate a config you must re-enter the credential — ensure it is still accessible from your secrets manager before doing so.
- The Workers dashboard "Hyperdrive" panel shows the connection string origin host and port but not the password; however any API token with `hyperdrive:read` can retrieve metadata that may hint at the database topology.

## Verification

```bash
# Confirm wrangler.toml contains no raw credentials
grep -E "(postgres|mysql|mongodb)://" wrangler.toml && echo "FAIL" || echo "PASS"

# Confirm the Hyperdrive config is bound correctly in staging
wrangler hyperdrive get staging-config-id-111

# Smoke-test the Worker uses the correct database
curl -s https://staging.example.com/healthz | jq .db_version
```

## Related

- `workers-environment-variable-hygiene.md`
- `wrangler-cicd-secret-injection-hygiene.md`
- `secrets-management-vault-dynamic-secrets.md`
- `api-key-rotation-zero-downtime.md`
- `multi-tenancy-isolation-workers-kv-d1.md`

## Sources

- Cloudflare Hyperdrive docs: https://developers.cloudflare.com/hyperdrive/
- Cloudflare Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
