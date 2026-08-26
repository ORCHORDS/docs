# Dynamic Workflow Configuration Loaded from Cloudflare D1 at Runtime

- Date: 2026-08-22
- Author: example.com
- Status: production

## Eliminating Hard-Coded Build Config from GitHub Actions Workflows

GitHub Actions workflows conventionally store build configuration as static environment variables in the YAML file or in repository secrets. This works for values that rarely change, but becomes a bottleneck when multiple services share configuration (feature flags, API endpoints, canary percentages, target regions) that engineering teams need to update without opening a PR to every workflow file.

The alternative is to treat workflow configuration as data: store it in a Cloudflare D1 SQLite database, expose a thin Workers API endpoint that validates the caller and serialises a config row as JSON, and have each workflow job call that endpoint at startup to export the resolved values as `$GITHUB_ENV` entries. The job's subsequent steps see the variables exactly as if they had been declared in the workflow YAML, but the values come from a versioned, auditable database row that any authorised user can update through a web UI or CLI without touching the workflow file.

Versioning the config schema in D1 (a `schema_version` column with a monotone integer) lets the Worker refuse requests from stale workflow callers that don't understand new fields, surfacing the mismatch as a workflow failure with a clear error message rather than a silent mis-configuration.

## Context

- D1 database: `build_config` table with columns `(id TEXT PRIMARY KEY, schema_version INTEGER, payload TEXT, updated_at TEXT)`
- Workers endpoint: `GET /config/:configId?schema_version=N` — returns the payload if versions match
- Caller authentication: OIDC JWT from `actions/github-oidc` validated in the Worker using `jose`
- GitHub Actions step: shell script that calls the endpoint and writes to `$GITHUB_ENV`

## D1 Schema and Seed

```sql
-- migrations/0001_create_build_config.sql
CREATE TABLE IF NOT EXISTS build_config (
  id             TEXT    PRIMARY KEY,
  schema_version INTEGER NOT NULL DEFAULT 1,
  payload        TEXT    NOT NULL,  -- JSON blob
  updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- seed a row for the "api-service" workflow
INSERT OR REPLACE INTO build_config (id, schema_version, payload) VALUES (
  'api-service',
  1,
  '{"NODE_ENV":"production","API_REGION":"us-east-1","FEATURE_NEW_CHECKOUT":"false","MAX_WORKERS":"4"}'
);
```

## Workers API Endpoint

```ts
// src/config-api.ts
import { jwtVerify, createRemoteJWKSet } from "jose";

export interface Env {
  DB: D1Database;
  GITHUB_JWKS_URL: string; // https://token.actions.githubusercontent.com/.well-known/jwks
  ALLOWED_REPO: string;    // e.g. "my-org/api-service"
}

const SUPPORTED_SCHEMA_VERSION = 1;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Validate OIDC token
    const authHeader = request.headers.get("Authorization") ?? "";
    const token = authHeader.replace(/^Bearer\s+/, "");
    if (!token) return new Response("Unauthorized", { status: 401 });

    try {
      const JWKS = createRemoteJWKSet(new URL(env.GITHUB_JWKS_URL));
      const { payload: claims } = await jwtVerify(token, JWKS, {
        issuer: "https://token.actions.githubusercontent.com",
        audience: "https://config.example.com",
      });

      if (claims.repository !== env.ALLOWED_REPO) {
        return new Response("Forbidden: repository mismatch", { status: 403 });
      }
    } catch (err) {
      return new Response(`Token validation failed: ${err}`, { status: 401 });
    }

    const url = new URL(request.url);
    const configId = url.pathname.split("/").pop() ?? "";
    const callerVersion = parseInt(url.searchParams.get("schema_version") ?? "0", 10);

    const row = await env.DB.prepare(
      "SELECT schema_version, payload FROM build_config WHERE id = ?"
    )
      .bind(configId)
      .first<{ schema_version: number; payload: string }>();

    if (!row) return new Response("Config not found", { status: 404 });

    if (callerVersion !== SUPPORTED_SCHEMA_VERSION || row.schema_version !== SUPPORTED_SCHEMA_VERSION) {
      return new Response(
        JSON.stringify({
          error: "schema_version_mismatch",
          server: SUPPORTED_SCHEMA_VERSION,
          caller: callerVersion,
          stored: row.schema_version,
        }),
        { status: 409, headers: { "Content-Type": "application/json" } }
      );
    }

    return new Response(row.payload, {
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  },
};
```

## GitHub Actions Workflow Step

```yaml
# .github/workflows/build.yml
name: Build API Service

on:
  push:
    branches: [main]

permissions:
  id-token: write   # required for OIDC token
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Fetch dynamic config from D1
        env:
          CONFIG_ENDPOINT: https://config.example.com/config/api-service
          SCHEMA_VERSION: "1"
        run: |
          TOKEN=$(curl -sSfL \
            -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=https://config.example.com" \
            | jq -r '.value')

          CONFIG=$(curl -sSf \
            -H "Authorization: Bearer $TOKEN" \
            "${CONFIG_ENDPOINT}?schema_version=${SCHEMA_VERSION}")

          # Export every key in the JSON object as a GitHub env variable
          echo "$CONFIG" | jq -r 'to_entries[] | "\(.key)=\(.value)"' >> "$GITHUB_ENV"

      - name: Build with resolved config
        run: |
          echo "Building for region: $API_REGION"
          echo "Feature flag: $FEATURE_NEW_CHECKOUT"
          npm ci && npm run build
```

## Versioned Config Schema

When the schema needs a new field, bump `schema_version` in both the D1 row and the Worker constant, and update the workflow's `SCHEMA_VERSION` env var in the same PR:

```ts
// Migrate existing rows during a schema bump (run as a one-off D1 query)
const MIGRATE_V1_TO_V2 = `
  UPDATE build_config
  SET schema_version = 2,
      payload = json_patch(payload, '{"LOG_LEVEL":"info"}'),
      updated_at = datetime('now')
  WHERE schema_version = 1;
`;
```

```toml
# wrangler.toml
name = "build-config-api"
main = "src/config-api.ts"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "build-config"
database_id = "<your-d1-database-id>"

[vars]
GITHUB_JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks"
ALLOWED_REPO = "my-org/api-service"
```

## Anti-patterns

- Storing the Workers endpoint URL or config ID in a workflow secret — these are not sensitive and should be plain `env:` vars for debuggability
- Using a static long-lived API key instead of OIDC — rotating keys across dozens of workflows is operationally costly
- Caching config responses in the Worker or CDN — build jobs should always read the current value
- Putting secrets (database passwords, API keys) in the D1 payload — D1 config is for non-sensitive build parameters; secrets belong in Actions secrets or Workers Secrets
- Ignoring `schema_version` in callers — version mismatches silently produce wrong configs

## Gotchas

- `ACTIONS_ID_TOKEN_REQUEST_TOKEN` and `ACTIONS_ID_TOKEN_REQUEST_URL` are only injected when `id-token: write` permission is declared at the job level
- `jq` must be available on the runner; it is pre-installed on `ubuntu-latest` and `macos-latest`
- D1 `json_patch` requires SQLite JSON1 extension, which D1 enables by default
- OIDC tokens expire within minutes; the workflow step must acquire and use the token in the same step
- Workers deployed with `wrangler deploy` in the same workflow run that reads config can cause a circular dependency if the config controls the deploy target

## Verification

```ts
// Test config endpoint with a mocked D1 binding
import { env } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import worker from "./src/config-api";

describe("config API", () => {
  it("returns 409 on schema version mismatch", async () => {
    await env.DB.prepare(
      "INSERT INTO build_config (id, schema_version, payload) VALUES (?, ?, ?)"
    ).bind("test-svc", 2, '{"FOO":"bar"}').run();

    const req = new Request("https://example.com/config/test-svc?schema_version=1", {
      headers: { Authorization: "Bearer <valid-oidc-token>" },
    });
    const res = await worker.fetch(req, env);
    expect(res.status).toBe(409);
    const body = await res.json<{ error: string }>();
    expect(body.error).toBe("schema_version_mismatch");
  });
});
```

## Related

- `documentation/categories/github/github-actions-cloudflare-d1-migration-pipeline.md`
- `documentation/categories/github/github-actions-cloudflare-deploy-workflow.md`
- `documentation/categories/github/github-actions-dynamic-matrix-and-fail-fast.md`

## Sources

- https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/
