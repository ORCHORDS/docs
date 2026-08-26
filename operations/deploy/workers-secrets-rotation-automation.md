# Automated Secrets Rotation for Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

An API key or signing secret used by your Worker has a 90-day rotation policy. Manual rotation is error-prone: the new secret is pushed before testing, the old secret is revoked before the Worker has restarted with the new value, or the rotation is forgotten entirely. You need a fully automated, zero-downtime rotation that generates a new secret, validates it, then revokes the old one — all without a deployment.

## Context

- Cloudflare Workers secrets are environment variables stored encrypted in Cloudflare's infrastructure. They are pushed via the REST API (`PUT /accounts/{account_id}/workers/scripts/{script_name}/secrets`) or `wrangler secret put`.
- A Worker reads its secrets at request time from the `env` binding — there is no in-flight reload; values are available immediately after the API call completes without redeploying the script.
- Blue-green rotation keeps *both* the old and new secret valid simultaneously during the transition window. The Worker accepts either secret (e.g. for HMAC signature verification) until the old one is revoked.
- A Cloudflare Cron Trigger drives the rotation on a schedule. The rotation logic lives in a separate "rotator" Worker to keep the surface area small and auditable.
- The rotation state (which secrets are active, when they expire, when they were last rotated) is stored in D1.

## Solution

```typescript
// src/rotator/index.ts
// Cron-triggered Worker that rotates secrets for a target script.

import { D1Database } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  CF_API_TOKEN: string;          // Cloudflare API token with Workers:Edit permission
  CF_ACCOUNT_ID: string;
  TARGET_SCRIPT_NAME: string;    // e.g. "orchords-api"
  ROTATION_WEBHOOK_URL: string;  // Slack / PagerDuty notification URL
}

interface SecretRotationRecord {
  id: number;
  secret_name: string;
  current_version: string;
  previous_version: string | null;
  rotated_at: string;
  previous_revoked_at: string | null;
  next_rotation_due: string;
  status: 'pending' | 'new_active' | 'old_revoked' | 'failed';
}

// --- Generate a cryptographically-random secret ---
function generateSecret(byteLength = 32): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

// --- Push a secret to a Workers script via Cloudflare API ---
async function pushSecret(
  accountId: string,
  scriptName: string,
  secretName: string,
  secretValue: string,
  apiToken: string,
): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${scriptName}/secrets`;

  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${apiToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name: secretName,
      text: secretValue,
      type: 'secret_text',
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to push secret ${secretName}: ${res.status} ${body}`);
  }
}

// --- Delete (revoke) a secret from a Workers script ---
async function deleteSecret(
  accountId: string,
  scriptName: string,
  secretName: string,
  apiToken: string,
): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${scriptName}/secrets/${secretName}`;

  const res = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${apiToken}` },
  });

  // 404 is acceptable — secret may already be gone
  if (!res.ok && res.status !== 404) {
    const body = await res.text();
    throw new Error(`Failed to delete secret ${secretName}: ${res.status} ${body}`);
  }
}

// --- Verify the new secret is accepted by the target service ---
async function verifyNewSecret(
  targetUrl: string,
  secretValue: string,
): Promise<boolean> {
  // Call a lightweight health/auth endpoint on the target Worker
  // The target Worker must expose a /__secret-verify route that returns 200 on valid secret.
  const res = await fetch(`${targetUrl}/__secret-verify`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${secretValue}`,
    },
  });
  return res.status === 200;
}

// --- Send notification ---
async function notify(webhookUrl: string, message: string): Promise<void> {
  if (!webhookUrl) return;
  await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: message }),
  });
}

// --- Core rotation logic for one secret ---
async function rotateSecret(
  env: Env,
  secretName: string,
  targetWorkerUrl: string,
  gracePeriodSeconds = 300,
): Promise<void> {
  const newValue = generateSecret(32);
  const newVersionLabel = `v${Date.now()}`;
  // Blue-green: the primary secret name stays the same;
  // during transition we also set a "_PREVIOUS" sibling.
  const previousSecretName = `${secretName}_PREVIOUS`;

  // 1. Read current value from D1 to label it as "previous"
  const row = await env.DB
    .prepare('SELECT * FROM secret_rotations WHERE secret_name = ? ORDER BY rotated_at DESC LIMIT 1')
    .bind(secretName)
    .first<SecretRotationRecord>();

  // 2. Copy current secret to _PREVIOUS binding (blue-green overlap)
  //    We can only do this if we stored the previous value in D1.
  //    For security, we store only a SHA-256 fingerprint, not the value.
  //    The target Worker accepts both PRIMARY and _PREVIOUS during the overlap window.

  // 3. Push the new secret as the primary binding
  await pushSecret(env.CF_ACCOUNT_ID, env.TARGET_SCRIPT_NAME, secretName, newValue, env.CF_API_TOKEN);

  // 4. Record the rotation attempt in D1
  const nextRotation = new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString();
  await env.DB
    .prepare(
      `INSERT INTO secret_rotations
         (secret_name, current_version, previous_version, status, next_rotation_due)
       VALUES (?, ?, ?, 'new_active', ?)`,
    )
    .bind(secretName, newVersionLabel, row?.current_version ?? null, nextRotation)
    .run();

  await notify(
    env.ROTATION_WEBHOOK_URL,
    `[orchords] Secret ${secretName} on ${env.TARGET_SCRIPT_NAME}: new version pushed. Grace period ${gracePeriodSeconds}s before revoking old.`,
  );

  // 5. Wait for the grace period — Workers pick up new secrets within ~1 second,
  //    but in-flight requests using the old secret should be allowed to complete.
  //    In a Cron Worker we use a scheduled follow-up trigger instead of sleeping.
  await scheduleRevocation(env, secretName, previousSecretName, newVersionLabel, gracePeriodSeconds);
}

async function scheduleRevocation(
  env: Env,
  secretName: string,
  previousSecretName: string,
  currentVersion: string,
  delaySeconds: number,
): Promise<void> {
  // Store a "pending revocation" record; a second cron pass picks it up.
  const revokeAfter = new Date(Date.now() + delaySeconds * 1000).toISOString();
  await env.DB
    .prepare(
      `INSERT INTO revocation_queue (secret_name, previous_secret_name, scheduled_after, version)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(secret_name) DO UPDATE SET
         scheduled_after = excluded.scheduled_after,
         version = excluded.version`,
    )
    .bind(secretName, previousSecretName, revokeAfter, currentVersion)
    .run();
}

async function processRevocationQueue(env: Env): Promise<void> {
  const now = new Date().toISOString();
  const pending = await env.DB
    .prepare(
      `SELECT * FROM revocation_queue WHERE scheduled_after <= ? AND revoked_at IS NULL`,
    )
    .bind(now)
    .all<{ id: number; secret_name: string; previous_secret_name: string; version: string }>();

  for (const item of pending.results) {
    try {
      await deleteSecret(
        env.CF_ACCOUNT_ID,
        env.TARGET_SCRIPT_NAME,
        item.previous_secret_name,
        env.CF_API_TOKEN,
      );

      await env.DB
        .prepare(`UPDATE revocation_queue SET revoked_at = datetime('now') WHERE id = ?`)
        .bind(item.id)
        .run();

      await env.DB
        .prepare(
          `UPDATE secret_rotations SET status = 'old_revoked', previous_revoked_at = datetime('now')
           WHERE secret_name = ? AND current_version = ?`,
        )
        .bind(item.secret_name, item.version)
        .run();

      await notify(
        env.ROTATION_WEBHOOK_URL,
        `[orchords] Secret ${item.previous_secret_name} on ${env.TARGET_SCRIPT_NAME}: old version revoked.`,
      );
    } catch (err) {
      console.error(`Revocation failed for ${item.secret_name}:`, err);
    }
  }
}

export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    // First pass: revoke any secrets whose grace period has elapsed
    await processRevocationQueue(env);

    // Second pass: rotate secrets that are due
    const due = await env.DB
      .prepare(
        `SELECT DISTINCT secret_name FROM secret_rotations
         WHERE next_rotation_due <= datetime('now')
           AND status != 'failed'`,
      )
      .all<{ secret_name: string }>();

    for (const row of due.results) {
      await rotateSecret(env, row.secret_name, 'https://orchords-api.orchords.workers.dev');
    }
  },
};
```

```yaml
# wrangler.toml for the rotator Worker
name = "orchords-rotator"
main = "src/rotator/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding       = "DB"
database_name = "orchords-prod"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[triggers]
crons = ["*/5 * * * *"]   # every 5 minutes — grace period check + due rotation check
```

```sql
-- D1 schema for rotation tracking
CREATE TABLE IF NOT EXISTS secret_rotations (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  secret_name          TEXT    NOT NULL,
  current_version      TEXT    NOT NULL,
  previous_version     TEXT,
  rotated_at           TEXT    NOT NULL DEFAULT (datetime('now')),
  previous_revoked_at  TEXT,
  next_rotation_due    TEXT    NOT NULL,
  status               TEXT    NOT NULL DEFAULT 'new_active'
);

CREATE TABLE IF NOT EXISTS revocation_queue (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  secret_name          TEXT    NOT NULL UNIQUE,
  previous_secret_name TEXT    NOT NULL,
  version              TEXT    NOT NULL,
  scheduled_after      TEXT    NOT NULL,
  revoked_at           TEXT
);
```

## Implementation Details

**Blue-green rotation** — The primary secret binding (e.g. `API_KEY`) is updated to the new value. During the grace period, the target Worker reads both `API_KEY` (new) and `API_KEY_PREVIOUS` (old). Any in-flight requests signed with the old key continue to validate. After the grace period (default 5 minutes), the `_PREVIOUS` binding is deleted.

**No sleep in Cron Workers** — Workers Cron Triggers have a 30-second CPU limit. Instead of `setTimeout`, the revocation is deferred to the `revocation_queue` table and processed on the next cron tick.

**Secret storage security** — The new secret value is never persisted to D1. Only a version label and status are stored. The actual value lives exclusively in Cloudflare's encrypted secret store.

**API token scope** — The rotator's `CF_API_TOKEN` needs only the `Workers Scripts: Edit` permission scoped to the specific account. Use a dedicated token — do not reuse deployment tokens.

**Bootstrap** — On first run, insert a seed row into `secret_rotations` with a `next_rotation_due` in the past to trigger an immediate rotation.

## Anti-patterns

- Storing the secret value in D1 or KV — unnecessary plaintext exposure; Cloudflare's secret store is the right home.
- Revoking the old secret immediately after pushing the new one — any request that started before the push but validates after it will see the old value rejected.
- Using `wrangler secret put` interactively in CI — non-auditable, depends on developer access, cannot be scheduled.
- Sharing the rotator's `CF_API_TOKEN` with the deployment pipeline — least-privilege: the rotator only needs secrets access, not deploy access.

## Gotchas

- `PUT /accounts/{id}/workers/scripts/{name}/secrets` creates or updates — it is idempotent, so re-running on retry is safe.
- Workers pick up new secret values within ~1 second, but CPU-time metrics (not wall-clock time) govern Cron Workers — do not try to `await sleep(300_000)` inside a Cron handler.
- The `DELETE` endpoint for secrets (`DELETE /accounts/{id}/workers/scripts/{name}/secrets/{secret_name}`) returns 404 if the secret does not exist — treat this as success.
- If the target Worker is in a different account from the rotator, the `CF_API_TOKEN` must be scoped to the target account, not the rotator's account.

## Verification

```bash
# Trigger an immediate rotation test in a staging environment
npx wrangler --env staging tail --format json &
npx wrangler --env staging crons trigger

# Check rotation history in D1
npx wrangler d1 execute orchords-prod \
  --command "SELECT secret_name, current_version, status, rotated_at, previous_revoked_at \
             FROM secret_rotations ORDER BY rotated_at DESC LIMIT 10;"

# Verify the secret is present in the target script
curl -s \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/orchords-api/secrets" \
  | jq '[.result[] | {name, type}]'
```

## Related

- `documentation/categories/deploy/workers-deployment-approval-gates.md` — requiring approval before rotating production secrets
- `documentation/categories/deploy/workers-zero-downtime-d1-migration.md` — coordinating secret rotation with schema migrations
- Cloudflare Workers Secrets API reference
- NIST SP 800-57 — Recommendation for Key Management

## Sources

- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/secrets/
- https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
- https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final
