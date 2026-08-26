# Deploying Workers on Git Tag Push via GitHub Actions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You want every git tag matching `v*` to trigger an automated, versioned deploy of your Cloudflare Worker to production, create a GitHub Release, and post a Slack notification with the deploy URL — replacing manual `wrangler deploy` commands run from developer laptops and eliminating version drift between the git tag and the running code.

---

## Context
GitHub Actions supports `push: tags` triggers that fire only when a tag is pushed, keeping the workflow isolated from branch commits. The tag name is available as `github.ref_name` (e.g., `v1.4.2`) and can be injected into the Worker at deploy time using `wrangler deploy --var`. The `gh` CLI bundled in GitHub-hosted runners creates Releases without a separate API call. Slack notifications use the Incoming Webhooks API which requires only a secret URL and a JSON payload via `curl`.

---

## Section 1 — Repository Secrets and Wrangler Config

Required GitHub Actions secrets:

| Secret | Value |
|---|---|
| `CF_API_TOKEN` | Cloudflare API token with `Workers Scripts:Edit` permission |
| `CF_ACCOUNT_ID` | Cloudflare Account ID |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[env.production]
name = "my-worker-production"
route = { pattern = "api.example.com/*", zone_name = "example.com" }

# VERSION var is injected at deploy time via --var; no static value here.
```

---

## Section 2 — GitHub Actions Workflow

```yaml
# .github/workflows/deploy-on-tag.yml
name: Deploy Worker on Tag

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write   # needed for gh release create

jobs:
  deploy:
    name: Deploy to production
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Checkout code at tag
        uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history for release notes

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run tests
        run: npm test

      - name: Deploy Worker to production
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          VERSION="${{ github.ref_name }}"
          echo "Deploying version ${VERSION}"
          DEPLOY_OUTPUT=$(wrangler deploy --env production --var VERSION:"${VERSION}" 2>&1)
          echo "${DEPLOY_OUTPUT}"
          # Extract deploy URL from wrangler output
          DEPLOY_URL=$(echo "${DEPLOY_OUTPUT}" | grep -oP 'https://[a-z0-9.-]+\.workers\.dev' | head -1)
          echo "deploy_url=${DEPLOY_URL}" >> "${GITHUB_OUTPUT}"
          echo "version=${VERSION}" >> "${GITHUB_OUTPUT}"

      - name: Generate release notes from git log
        id: notes
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 HEAD^ 2>/dev/null || echo '')
          if [[ -n "${PREV_TAG}" ]]; then
            NOTES=$(git log "${PREV_TAG}"..HEAD --pretty=format:'- %s (%h)' --no-merges)
          else
            NOTES=$(git log --pretty=format:'- %s (%h)' --no-merges | head -20)
          fi
          # Write multi-line output safely
          {
            echo 'notes<<EOF'
            echo "${NOTES}"
            echo 'EOF'
          } >> "${GITHUB_OUTPUT}"

      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "${{ github.ref_name }}" \
            --title "Release ${{ github.ref_name }}" \
            --notes "${{ steps.notes.outputs.notes }}" \
            --verify-tag

      - name: Notify Slack
        if: always()
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          STATUS="${{ job.status }}"
          VERSION="${{ steps.deploy.outputs.version }}"
          URL="${{ steps.deploy.outputs.deploy_url }}"
          COLOR=$([ "${STATUS}" = 'success' ] && echo 'good' || echo 'danger')
          EMOJI=$([ "${STATUS}" = 'success' ] && echo ':rocket:' || echo ':x:')
          curl -sf -X POST "${SLACK_WEBHOOK_URL}" \
            -H 'Content-Type: application/json' \
            -d "{
              \"attachments\": [{
                \"color\": \"${COLOR}\",
                \"text\": \"${EMOJI} Worker deploy *${VERSION}* ${STATUS}. URL: ${URL}\",
                \"footer\": \"GitHub Actions | ${{ github.repository }}\"
              }]
            }"
```

---

## Section 3 — Worker Version Variable and Smoke Test

```typescript
// src/index.ts
declare const VERSION: string;   // injected via --var at deploy time

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return Response.json({ ok: true, version: VERSION ?? 'dev' });
    }

    // ... main handler
    return new Response('OK');
  },
};
```

```bash
# smoke-test.sh — run after deploy step in CI or locally
set -euo pipefail
WORKER_URL="${1:?worker URL required}"
EXPECTED_VERSION="${2:?expected version required}"

RESPONSE=$(curl -sf "${WORKER_URL}/health")
ACTUAL_VERSION=$(echo "${RESPONSE}" | jq -r '.version')

if [[ "${ACTUAL_VERSION}" != "${EXPECTED_VERSION}" ]]; then
  echo "Version mismatch: expected ${EXPECTED_VERSION}, got ${ACTUAL_VERSION}"
  exit 1
fi

echo "Smoke test passed: version ${ACTUAL_VERSION} is live."
```

---

## Anti-patterns
- **Deploying from branch pushes** — Using `on: push: branches: [main]` for production deploys means every merge triggers a release; tags give you explicit, intentional version gates.
- **Hard-coding VERSION in source** — Forgetting to update a hard-coded version string is a constant source of drift; inject it from the tag at deploy time.
- **Missing `permissions: contents: write`** — The default token cannot create Releases; without this permission the `gh release create` step fails with a cryptic 403.
- **No smoke test after deploy** — Reporting success based solely on `wrangler deploy` exit code misses runtime errors (wrong binding, missing secret, parse error in Worker).

---

## Gotchas
- `github.ref_name` for a tag push contains just the tag (e.g., `v1.4.2`), not the full ref (`refs/tags/v1.4.2`) — use it directly without stripping.
- `wrangler deploy --var` accepts `KEY:VALUE` pairs; if the value contains colons (e.g., a URL), quote the whole argument: `--var "API_URL:https://example.com"`.
- Workers deployed with `--var` expose the value in the Worker's script source via `wrangler workers download` — do not use `--var` for secrets; use `wrangler secret put` instead.
- The `gh release create --verify-tag` flag confirms the tag exists on the remote before creating the release; without it, a workflow racing ahead of tag propagation can create a release pointing to the wrong commit.

---

## Verification

```bash
# Push a test tag and watch the workflow
git tag v1.0.0-test && git push origin v1.0.0-test

# Watch workflow run
gh run watch --repo <owner>/<repo>

# Confirm version in running Worker
curl -s https://my-worker-production.workers.dev/health | jq '.version'
# Expected: "v1.0.0-test"

# List GitHub Releases
gh release list --repo <owner>/<repo> --limit 5

# Clean up test tag
git push origin --delete v1.0.0-test
git tag -d v1.0.0-test
```

---

## Related
- `wrangler-environments-secrets-promotion.md`
- `workers-multi-worker-coordinated-deploy.md`
- `workers-zero-downtime-d1-migration-deploy.md`

---

## Sources
- GitHub Actions tag trigger documentation — https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#push
- Wrangler deploy CLI reference — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- Slack Incoming Webhooks — https://api.slack.com/messaging/webhooks
