# Updating Cloudflare Hyperdrive Configurations in GitHub Actions

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your Cloudflare Workers use Hyperdrive to accelerate Postgres queries, and you need CI to automatically create or update Hyperdrive configs when connection strings change — for example when promoting a staging database to production or rotating database credentials.

## Context
Hyperdrive stores a connection string (host, port, database, user, password) in Cloudflare's edge network and assigns each configuration a UUID. Workers reference this UUID via a binding in `wrangler.toml`. Because the UUID is stable across credential rotations, CI can update the origin credentials without changing the binding or redeploying the Worker — only the Hyperdrive config record itself needs to be patched. This pattern is more reliable than embedding the connection string as a secret because the Worker never sees the raw credentials.

## Detecting Config Drift

A TypeScript script compares the current Hyperdrive config against the desired state stored in `infrastructure/hyperdrive.json`.

```typescript
// scripts/sync-hyperdrive.ts
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;
const BASE = `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/hyperdrive/configs`;

interface HyperdriveOrigin {
  host: string;
  port: number;
  database: string;
  user: string;
  password: string;
  scheme: 'postgres' | 'postgresql';
}

interface HyperdriveDesired {
  name: string;
  origin: HyperdriveOrigin;
  caching?: { disabled?: boolean; max_age?: number };
}

async function cfFetch(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      'Content-Type': 'application/json',
      ...((init?.headers as Record<string, string>) ?? {}),
    },
  });
  if (!res.ok) throw new Error(`Cloudflare API error ${res.status}: ${await res.text()}`);
  return res.json() as Promise<{ result: any }>;
}

async function listConfigs(): Promise<Array<{ id: string; name: string }>> {
  const { result } = await cfFetch('');
  return result ?? [];
}

async function upsertConfig(desired: HyperdriveDesired, existingId?: string) {
  if (existingId) {
    console.log(`Updating Hyperdrive config '${desired.name}' (${existingId})`);
    await cfFetch(`/${existingId}`, {
      method: 'PUT',
      body: JSON.stringify(desired),
    });
  } else {
    console.log(`Creating Hyperdrive config '${desired.name}'`);
    const { result } = await cfFetch('', {
      method: 'POST',
      body: JSON.stringify(desired),
    });
    console.log(`Created with ID: ${result.id}`);
  }
}
```

## Reading Desired State from Config File

```typescript
// infrastructure/hyperdrive.json (tracked in VCS — passwords come from env vars at runtime)
// {
//   "configs": [
//     {
//       "name": "prod-postgres",
//       "origin_env": "PROD_DB_URL",
//       "caching": { "max_age": 60 }
//     }
//   ]
// }

import { readFileSync } from 'node:fs';

const manifest = JSON.parse(readFileSync('infrastructure/hyperdrive.json', 'utf8'));

const configs = await listConfigs();
const configsByName = new Map(configs.map((c) => [c.name, c.id]));

for (const entry of manifest.configs) {
  const rawUrl = process.env[entry.origin_env];
  if (!rawUrl) throw new Error(`Missing env var ${entry.origin_env}`);

  const url = new URL(rawUrl);
  const desired: HyperdriveDesired = {
    name: entry.name,
    origin: {
      host: url.hostname,
      port: Number(url.port) || 5432,
      database: url.pathname.slice(1),
      user: url.username,
      password: <redacted-secret>
      scheme: 'postgres',
    },
    caching: entry.caching,
  };

  await upsertConfig(desired, configsByName.get(entry.name));
}

console.log('Hyperdrive sync complete.');
```

## GitHub Actions Workflow

```yaml
# .github/workflows/hyperdrive-sync.yml
name: Sync Hyperdrive Configs

on:
  push:
    branches: [main]
    paths:
      - 'infrastructure/hyperdrive.json'
  workflow_dispatch:
    inputs:
      force:
        description: 'Force update even without file change'
        type: boolean
        default: false

permissions:
  contents: read
  id-token: write

jobs:
  sync:
    runs-on: ubuntu-24.04
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Sync Hyperdrive configs
        env:
          CF_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_HYPERDRIVE_API_TOKEN }}
          PROD_DB_URL: ${{ secrets.PROD_DB_URL }}
          STAGING_DB_URL: ${{ secrets.STAGING_DB_URL }}
        run: pnpm tsx scripts/sync-hyperdrive.ts

      - name: Summarize result
        if: always()
        run: |
          echo "## Hyperdrive Sync" >> $GITHUB_STEP_SUMMARY
          echo "Completed at $(date -u)" >> $GITHUB_STEP_SUMMARY
```

## wrangler.toml Binding

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[hyperdrive]]
binding = "DB"
id = "a1b2c3d4e5f6..."   # stable UUID; never changes on credential rotation
```

## Worker Usage

```typescript
// src/index.ts
export interface Env {
  DB: Hyperdrive;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // env.DB.connectionString is the connection URL with Hyperdrive's pooler endpoint.
    // Pass it to your Postgres client — the worker never sees the raw credentials.
    const { Pool } = await import('pg');
    const pool = new Pool({ connectionString: env.DB.connectionString });

    const { rows } = await pool.query('SELECT NOW() AS ts');
    await pool.end();

    return Response.json({ ts: rows[0].ts });
  },
};
```

## Credential Rotation Pattern

When rotating database passwords, update the Hyperdrive config first, then rotate the database password, ensuring zero downtime:

1. Create a new database user or generate a new password.
2. Run `hyperdrive-sync.yml` with the new `PROD_DB_URL` secret.
3. Verify Workers can connect via Hyperdrive (smoke test).
4. Revoke the old database credentials.

## Anti-patterns
- Embedding the raw Postgres URL as a Worker secret — the Worker then has access to the raw credentials, and secret rotation requires a Worker redeploy.
- Using a Cloudflare API token with `Account:Edit` scope for Hyperdrive updates — scope it to `Hyperdrive:Edit` only.
- Storing the Hyperdrive config UUID in the workflow environment variables — it belongs in `wrangler.toml` as a binding, tracked in VCS.
- Deleting and recreating the Hyperdrive config to change credentials — this changes the UUID and breaks the binding without a Worker redeploy.

## Gotchas
- Hyperdrive `PUT` to update a config requires the full body including `name`, `origin`, and `caching` — partial updates (PATCH) are not supported.
- The Cloudflare API returns `200` for both create and update; check `result.id` in the response to confirm the config was written.
- Hyperdrive cannot connect to databases on private networks unless Cloudflare Tunnel or Magic WAN is configured.
- The `max_age` cache setting applies per-query; queries with parameters are not cached regardless of this setting.

## Verification
1. Update a connection string in an environment variable and trigger the workflow.
2. Check the Cloudflare dashboard under **Workers > Hyperdrive** to confirm the origin host/user updated.
3. Deploy a test Worker that queries `SELECT current_user` and verify it returns the new database user.
4. Confirm the Hyperdrive config UUID in `wrangler.toml` is unchanged after the update.

## Related
- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-oidc-cloudflare-deploy.md`
- `github-actions-secrets-management.md`
- `github-actions-environment-protection.md`

## Sources
- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/configuration/connect-to-postgres/
- https://developers.cloudflare.com/api/resources/hyperdrive/subresources/configs/
