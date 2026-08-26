# Bulk Importing Secrets to Workers with Wrangler

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to provision or rotate a large set of secrets across one or more Cloudflare Workers environments without manually running `wrangler secret put` for every key — especially in CI/CD pipelines where interactive prompts are not available.

## Context

`wrangler secret put` is designed for one-off interactive use: it reads the secret value from stdin. In automation scenarios (GitHub Actions, CircleCI, Buildkite), you need a non-interactive path. `wrangler secret bulk` accepts a JSON file and pushes all key-value pairs in a single API call, making it CI-safe and scriptable.

The feature is available in Wrangler v3+ and targets the same Cloudflare Workers Secrets API used by the dashboard.

## Bulk Import via JSON File

```bash
# secrets.json — the file wrangler secret bulk expects
# Format: a flat JSON object where every value is a string
cat secrets.json
# {
#   "STRIPE_SECRET_KEY": "sk_live_abc123",
#   "SENDGRID_API_KEY": "SG.xyz789",
#   "DATABASE_URL": "postgres://user:pass@host/db",
#   "JWT_SECRET": "super-long-random-hex-string"
# }

# Push all secrets to the Worker named "api-gateway"
npx wrangler secret bulk secrets.json --name api-gateway

# Scope to a named environment defined in wrangler.toml
npx wrangler secret bulk secrets.json --name api-gateway --env production
npx wrangler secret bulk secrets.json --name api-gateway --env staging

# Generate secrets.json from a .env file with a shell one-liner
# Handles KEY=value lines, strips comments (#) and blank lines
python3 - <<'PY'
import json, re, pathlib

raw = pathlib.Path(".env.production").read_text()
result = {}
for line in raw.splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
    if m:
        key, val = m.group(1), m.group(2).strip('"').strip("'")
        result[key] = val
print(json.dumps(result, indent=2))
PY

# Or with a pure-bash approach using jq
export $(grep -v '^#' .env.production | xargs)
jq -n 'env | with_entries(select(.key | test("^(STRIPE|SENDGRID|JWT|DATABASE)")))'  > secrets.json
npx wrangler secret bulk secrets.json --name api-gateway --env production

# Rotating secrets: update values in secrets.json, re-run the same command
# Wrangler upserts — existing keys are overwritten, new keys are created
npx wrangler secret bulk secrets.json --name api-gateway --env production

# Verify the keys that were imported (values are never returned by the API)
npx wrangler secret list --name api-gateway --env production
```

## Difference Between `put` and `bulk`

| Feature | `wrangler secret put` | `wrangler secret bulk` |
|---|---|---|
| Input method | Interactive stdin prompt | JSON file argument |
| Number of secrets per run | 1 | N (entire file) |
| CI-safe | No (requires TTY) | Yes |
| Partial update | Yes, one key at a time | Yes, upserts all keys in file |
| Rollback support | Manual re-run | Re-run with previous `secrets.json` |

Use `put` for quick one-off changes during local development. Use `bulk` everywhere else.

## Scoping Secrets per Environment

Wrangler environments map to the `[env.<name>]` sections in `wrangler.toml`. Secrets are **per environment** — a secret set for `production` is not visible to `staging`.

```toml
# wrangler.toml
name = "api-gateway"

[env.staging]
name = "api-gateway-staging"

[env.production]
name = "api-gateway-production"
```

```bash
# Each environment gets its own secret set
npx wrangler secret bulk secrets.staging.json  --name api-gateway --env staging
npx wrangler secret bulk secrets.production.json --name api-gateway --env production
```

## CI/CD Integration (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
- name: Import secrets to Workers
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  run: |
    # Build secrets.json from GitHub Actions secrets
    jq -n \
      --arg stripe "${{ secrets.STRIPE_SECRET_KEY }}" \
      --arg sg     "${{ secrets.SENDGRID_API_KEY }}" \
      --arg jwt    "${{ secrets.JWT_SECRET }}" \
      '{STRIPE_SECRET_KEY: $stripe, SENDGRID_API_KEY: $sg, JWT_SECRET: $jwt}' \
      > secrets.json
    npx wrangler secret bulk secrets.json --name api-gateway --env production
    rm secrets.json
```

## Anti-patterns

- **Committing `secrets.json` to version control.** Add it to `.gitignore` immediately. Use a secrets manager (1Password CLI, Vault, AWS Secrets Manager) as the source of truth and generate the file at deploy time.
- **Storing secrets in `wrangler.toml` as `vars`.** `vars` are plain-text environment variables visible in the dashboard and in deployed Worker metadata. Use `secrets` for anything sensitive.
- **Using `wrangler secret put` in CI.** It blocks on stdin and will hang or fail. Always use `bulk` in automation.
- **Sharing a single `secrets.json` across environments.** Staging and production should have separate credentials. Template the file or generate it per environment from a secrets manager.

## Gotchas

- `wrangler secret bulk` does **not** delete keys that are present in the Worker but absent from the JSON file. Deletion requires explicit `wrangler secret delete <KEY>`.
- Secret values are **strings only**. JSON booleans, numbers, or nested objects in `secrets.json` cause a validation error. Stringify everything before writing the file.
- The `--name` flag overrides the `name` field in `wrangler.toml`. If you rely on the config file name, you can omit `--name` but you must run the command from the directory containing `wrangler.toml`.
- Secrets are not available inside `wrangler dev` local mode by default. Pass `--secret KEY=value` or set them as regular environment variables locally.

## Verification

```bash
# List keys (not values) after bulk import
npx wrangler secret list --name api-gateway --env production
# Expected output lists each key with "Secret" type

# Smoke-test that the Worker can read the secret at runtime
curl -s https://api-gateway-production.example.workers.dev/health \
  | jq '.secretsLoaded'
# Endpoint should return true if Worker successfully accessed bindings
```

## Related

- `wrangler-dev-external-api-mock-proxy.md` — local dev overrides for variables
- `vitest-workers-env-type-generation.md` — generating typed `Env` bindings
- Cloudflare Workers Secrets documentation

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#secret-bulk
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/workers/wrangler/environments/
