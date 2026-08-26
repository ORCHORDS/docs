# Matrix Deployment of Multiple Workers with GitHub Actions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have several Cloudflare Workers in a monorepo (`api`, `auth`, `webhooks`) and want to deploy them all on every push to `main` without duplicating workflow steps. Deploying serially is slow; deploying without concurrency controls risks overlapping runs corrupting the same Worker.

---

## Context

GitHub Actions matrix strategy lets you fan out a single job definition across a set of values defined under `matrix`. Each matrix job runs in a separate runner, so all three Workers deploy in parallel by default. A `concurrency` group keyed on the Worker name prevents a second push from racing a still-running deploy for the same service. The `needs: test` dependency ensures the matrix only starts after a passing test job, avoiding deploying broken code. Wrangler picks up per-Worker config through individual `wrangler.toml` files located under `workers/<name>/`.

---

## Section 1 — GitHub Actions workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write   # required if using OIDC tokens

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm test

  deploy:
    needs: test
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false          # keep deploying other workers if one fails
      matrix:
        worker: [api, auth, webhooks]

    # Prevent two deploys of the same worker running simultaneously.
    # 'cancel-in-progress: false' queues the newer run rather than killing it.
    concurrency:
      group: deploy-${{ matrix.worker }}-${{ github.ref }}
      cancel-in-progress: false

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Deploy ${{ matrix.worker }} Worker
        run: |
          npx wrangler deploy \
            --config workers/${{ matrix.worker }}/wrangler.toml
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Verify deployment
        run: |
          WORKER_URL=$(npx wrangler deployments list \
            --config workers/${{ matrix.worker }}/wrangler.toml \
            --json | jq -r '.[0].url')
          echo "Deployed ${{ matrix.worker }} → $WORKER_URL"
          curl --fail --silent --show-error "$WORKER_URL/health"
```

---

## Section 2 — Monorepo layout and per-Worker wrangler.toml

```
workers/
  api/
    src/index.ts
    wrangler.toml
  auth/
    src/index.ts
    wrangler.toml
  webhooks/
    src/index.ts
    wrangler.toml
package.json        # root package with shared devDeps
```

Example `workers/api/wrangler.toml`:

```toml
name = "my-api-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"
account_id = "${CLOUDFLARE_ACCOUNT_ID}"

[vars]
ENV = "production"

[[kv_namespaces]]
binding = "CACHE"
id = "aaabbbccc111222333"
```

Example `workers/auth/wrangler.toml`:

```toml
name = "my-auth-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"
account_id = "${CLOUDFLARE_ACCOUNT_ID}"

[vars]
ENV = "production"
JWT_ISSUER = "https://auth.example.com"
```

---

## Section 3 — Verification / Testing

```bash
# Locally verify each worker builds before pushing
for worker in api auth webhooks; do
  echo "=== Building $worker ==="
  npx wrangler deploy \
    --config workers/$worker/wrangler.toml \
    --dry-run \
    --outdir dist/$worker
done

# List current deployments for all workers
for worker in api auth webhooks; do
  echo "=== Deployments: $worker ==="
  npx wrangler deployments list \
    --config workers/$worker/wrangler.toml
done

# Smoke-test health endpoints after deploy
for subdomain in api auth webhooks; do
  curl --fail --silent "https://$subdomain.example.workers.dev/health" \
    && echo "$subdomain OK" \
    || echo "$subdomain FAILED"
done
```

---

## Anti-patterns

- **Single wrangler.toml for all workers** — Using one config file and switching the `name` field via environment variable breaks isolation; keep one `wrangler.toml` per Worker directory.
- **`cancel-in-progress: true` on the deploy concurrency group** — Killing a running deploy mid-flight can leave a Worker in a broken state; use `false` to queue instead.
- **`fail-fast: true` (the default)** — If one Worker deploy fails it cancels the other matrix jobs before they finish, leaving your platform partially deployed. Set `fail-fast: false`.
- **No `needs: test`** — Skipping the dependency means a broken commit can reach production the moment a runner is free.

---

## Gotchas

- Matrix jobs start roughly simultaneously, so cold-start scaling on shared KV namespaces can cause race conditions during the first few seconds after deploy.
- `wrangler deploy` exits 0 even when the Worker script has a startup error; always follow with a `/health` probe to confirm the new code is actually serving requests.
- If `workers/${{ matrix.worker }}/wrangler.toml` does not exist the step fails silently with a confusing "No config file found" error — add a pre-step that validates all config paths exist.
- The `CLOUDFLARE_ACCOUNT_ID` is technically optional when it is embedded in `wrangler.toml`, but exporting it as an environment variable overrides the file and allows one secret to serve all workers.

---

## Verification

```bash
# Check that wrangler can read each config before pushing
npx wrangler whoami
npx wrangler deploy --config workers/api/wrangler.toml --dry-run
npx wrangler deploy --config workers/auth/wrangler.toml --dry-run
npx wrangler deploy --config workers/webhooks/wrangler.toml --dry-run

# Confirm concurrency groups in the Actions UI
gh run list --workflow deploy.yml --limit 5
```

---

## Related

- `github-environments-cloudflare-workers-secrets.md`
- `github-oidc-cloudflare-api-token-keyless.md`

---

## Sources

- GitHub Actions matrix strategy — https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs
- Wrangler CLI deploy command — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- GitHub Actions concurrency — https://docs.github.com/en/actions/using-jobs/using-concurrency
