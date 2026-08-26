# GitHub Actions Matrix Strategy for Multi-Zone Cloudflare Workers Deployment

2026-08-24 / example.com / production

---

## Symptom / Use-case

An organisation operates a single Workers codebase that must be deployed to multiple Cloudflare
zones (e.g. `api.us.example.com`, `api.eu.example.com`, `api.ap.example.com`), each with its
own account ID, route pattern, environment variables, and KV namespace bindings. Running
sequential `wrangler deploy` commands blocks the pipeline for 3–5 minutes per zone. A matrix
strategy fans the deploys out in parallel, so all zones finish in roughly the time it takes to
deploy one, while keeping zone-specific secrets and config isolated.

## Context

Cloudflare Workers routes are zone-scoped: each zone lives in a Cloudflare account (or the same
account with different zones) and requires its own `CLOUDFLARE_API_TOKEN` that is scoped to that
zone. GitHub Actions matrix lets you define a list of zone descriptors — each with an account ID,
zone name, and wrangler environment — and spin up one job per entry, all running in parallel. Zone
credentials are stored as environment-scoped GitHub Secrets and injected into each matrix job via
`secrets` + `matrix` interpolation.

```
matrix:
  zone: [us, eu, ap]
        │       │      │
        ▼       ▼      ▼
   job:us  job:eu  job:ap     ← run in parallel
   wrangler wrangler wrangler
   deploy   deploy   deploy
   --env us --env eu --env ap
```

Each matrix leg deploys to a dedicated wrangler environment (`[env.us]`, `[env.eu]`, `[env.ap]`)
with per-environment KV namespace IDs, routes, and vars. Zone-scoped API tokens live in GitHub
Environments named `us-production`, `eu-production`, `ap-production` so protection rules and
required reviewers can be applied per-region.

## Code

### Wrangler configuration with per-zone environments

```toml
# wrangler.toml
name = "global-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[env.us]
name = "global-api-us"
routes = [{ pattern = "api.us.example.com/*", zone_name = "us.example.com" }]
[env.us.vars]
REGION = "us"
[env.us.kv_namespaces]
binding = "CACHE"
id = "KV_NAMESPACE_ID_US"

[env.eu]
name = "global-api-eu"
routes = [{ pattern = "api.eu.example.com/*", zone_name = "eu.example.com" }]
[env.eu.vars]
REGION = "eu"
[env.eu.kv_namespaces]
binding = "CACHE"
id = "KV_NAMESPACE_ID_EU"

[env.ap]
name = "global-api-ap"
routes = [{ pattern = "api.ap.example.com/*", zone_name = "ap.example.com" }]
[env.ap.vars]
REGION = "ap"
[env.ap.kv_namespaces]
binding = "CACHE"
id = "KV_NAMESPACE_ID_AP"
```

### Multi-zone matrix deployment workflow

```yaml
# .github/workflows/deploy-multi-zone.yml
name: Multi-Zone Workers Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  id-token: write   # For OIDC if you want secretless tokens per zone

jobs:
  build:
    name: Build
    runs-on: ubuntu-latest
    outputs:
      artifact-name: ${{ steps.build.outputs.artifact-name }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build
        id: build
        run: |
          pnpm run build
          echo "artifact-name=worker-dist-${{ github.sha }}" >> "$GITHUB_OUTPUT"

      - uses: actions/upload-artifact@v4
        with:
          name: ${{ steps.build.outputs.artifact-name }}
          path: dist/
          retention-days: 1

  deploy:
    name: Deploy ${{ matrix.zone }}
    needs: build
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include:
          - zone: us
            environment: us-production
            account_secret: CF_ACCOUNT_ID_US
            token_secret: CF_API_TOKEN_US
          - zone: eu
            environment: eu-production
            account_secret: CF_ACCOUNT_ID_EU
            token_secret: CF_API_TOKEN_EU
          - zone: ap
            environment: ap-production
            account_secret: CF_ACCOUNT_ID_AP
            token_secret: CF_API_TOKEN_AP
      # By default fail-fast=true; set false so a single zone failure
      # does not cancel the other in-flight deploys.
      fail-fast: false

    environment: ${{ matrix.environment }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Download build artifact
        uses: actions/download-artifact@v4
        with:
          name: ${{ needs.build.outputs.artifact-name }}
          path: dist/

      - name: Install Wrangler
        run: npm install -g wrangler

      - name: Deploy to ${{ matrix.zone }}
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets[matrix.account_secret] }}
          CLOUDFLARE_API_TOKEN: ${{ secrets[matrix.token_secret] }}
        run: |
          wrangler deploy --env ${{ matrix.zone }} --compatibility-date 2026-08-01

      - name: Smoke test ${{ matrix.zone }}
        run: |
          ZONE="${{ matrix.zone }}"
          URL="https://api.${ZONE}.example.com/healthz"
          for i in $(seq 1 6); do
            STATUS=$(curl -sSo /dev/null -w "%{http_code}" "$URL" || echo "000")
            if [ "$STATUS" = "200" ]; then
              echo "Zone $ZONE healthy after $i attempt(s)"
              exit 0
            fi
            echo "Attempt $i: got $STATUS, retrying in 10s..."
            sleep 10
          done
          echo "Zone $ZONE did not become healthy" >&2
          exit 1
```

### Dynamic matrix from a JSON file (for large zone counts)

```yaml
# .github/workflows/deploy-dynamic-zones.yml
jobs:
  load-zones:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.set.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4

      - name: Load zone matrix from config
        id: set
        run: |
          # zones.json: [{"zone":"us","environment":"us-production",...}, ...]
          MATRIX=$(cat .github/zones.json | jq -c '{include: .}')
          echo "matrix=$MATRIX" >> "$GITHUB_OUTPUT"

  deploy:
    needs: load-zones
    strategy:
      matrix: ${{ fromJson(needs.load-zones.outputs.matrix) }}
      fail-fast: false
    # ... rest of deploy steps
```

### Zone configuration file for dynamic matrix

```json
[
  {
    "zone": "us",
    "environment": "us-production",
    "account_secret": "CF_ACCOUNT_ID_US",
    "token_secret": "CF_API_TOKEN_US"
  },
  {
    "zone": "eu",
    "environment": "eu-production",
    "account_secret": "CF_ACCOUNT_ID_EU",
    "token_secret": "CF_API_TOKEN_EU"
  },
  {
    "zone": "ap",
    "environment": "ap-production",
    "account_secret": "CF_ACCOUNT_ID_AP",
    "token_secret": "CF_API_TOKEN_AP"
  }
]
```

### Post-deployment rollback job (runs if any deploy matrix leg fails)

```yaml
  rollback:
    name: Rollback ${{ matrix.zone }}
    needs: deploy
    if: failure()
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include:
          - zone: us
            environment: us-production
            account_secret: CF_ACCOUNT_ID_US
            token_secret: CF_API_TOKEN_US
          - zone: eu
            environment: eu-production
            account_secret: CF_ACCOUNT_ID_EU
            token_secret: CF_API_TOKEN_EU
          - zone: ap
            environment: ap-production
            account_secret: CF_ACCOUNT_ID_AP
            token_secret: CF_API_TOKEN_AP
      fail-fast: false

    environment: ${{ matrix.environment }}

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # Need parent commit for rollback

      - name: Rollback ${{ matrix.zone }} to previous version
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets[matrix.account_secret] }}
          CLOUDFLARE_API_TOKEN: ${{ secrets[matrix.token_secret] }}
        run: |
          git checkout HEAD~1 -- src/ wrangler.toml
          wrangler deploy --env ${{ matrix.zone }}
```

## Anti-patterns

- **Using repository-level secrets for zone tokens.** If any job in the matrix can read
  `CF_API_TOKEN_US`, it can also exfiltrate the tokens for `EU` and `AP`. Store each token in
  its own GitHub Environment secret so the zone job only sees its own credential.
- **`fail-fast: true` (the default) on a multi-zone matrix.** When one zone fails, the other
  running jobs are cancelled, leaving those zones in an ambiguous state. Set `fail-fast: false`
  and let each zone finish or fail independently.
- **Deploying to all zones from a single `wrangler deploy` command using `--all-environments`.**
  This is sequential and cannot be parallelised. Matrix jobs run in parallel by default.
- **Using the same KV namespace ID across zones.** KV namespaces are account-scoped; you cannot
  share a namespace between accounts. Each zone environment must reference its own namespace ID.

## Gotchas

- GitHub Actions matrix jobs that reference an `environment` key with required reviewers will
  each pause for approval separately. Configure required-reviewer count at the environment level
  and accept that reviewers will see `N` pending approvals (one per zone) for a full rollout.
- `secrets[matrix.token_secret]` — indexing `secrets` by a matrix value — works in `env` blocks
  but not directly in `with` blocks. Wrap the secret in an environment variable and reference the
  env var in the step that needs it.
- Wrangler reads `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` from environment variables.
  Do not pass `--account-id` on the CLI if the environment variable is also set; they conflict on
  some Wrangler versions.
- The maximum concurrent jobs per GitHub plan limits effective parallelism. On Free/Pro plans the
  limit is 20 concurrent jobs; Teams 60; Enterprise 500. Plans with low limits should batch zones.

## Verification

```shell
# After the matrix workflow completes, verify all zones report the same git SHA
for ZONE in us eu ap; do
  echo -n "Zone $ZONE version: "
  curl -sSf "https://api.${ZONE}.example.com/version" | jq -r '.sha'
done

# Verify wrangler environments are distinct scripts:
CLOUDFLARE_API_TOKEN=$CF_API_TOKEN_US wrangler deployments list --env us
CLOUDFLARE_API_TOKEN=$CF_API_TOKEN_EU wrangler deployments list --env eu
```

## Related

- `github-actions-matrix-strategy-workers.md`
- `github-actions-dynamic-matrix-and-fail-fast.md`
- `github-actions-workers-multi-region-smoke-test.md`
- `github-actions-reusable-workflows-workers-deploy.md`
- `github-actions-environment-protection.md`

## Sources

- <https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow>
- <https://developers.cloudflare.com/workers/wrangler/environments/>
- <https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions#using-secrets-in-a-matrix-strategy>
- <https://developers.cloudflare.com/workers/configuration/routing/routes/>
