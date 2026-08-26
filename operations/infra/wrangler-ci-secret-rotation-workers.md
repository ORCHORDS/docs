# Wrangler CI Secret Rotation for Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Workers use long-lived API keys that need to be rotated on a regular schedule (e.g. every 30 days) to meet compliance requirements. Rotating manually is error-prone and easy to skip. You want a fully automated pipeline: generate a new secret, push it with `wrangler secret put`, stamp a KV rotation record, and notify the team on Slack.

---

## Context
`wrangler secret put` reads the secret value from stdin, making it scriptable without the value appearing in shell history. A KV namespace acts as a lightweight audit ledger storing the rotation timestamp and the rotating principal. The GitHub Actions scheduled workflow runs on a cron and scopes its credentials to only the Cloudflare account and Worker it manages. The Slack notification uses an incoming webhook stored as a GitHub Actions secret.

---

## Shell rotation script
```bash
#!/usr/bin/env bash
# scripts/rotate-secret.sh
set -euo pipefail

WORKER_NAME="${1:-my-worker}"
SECRET_NAME="${2:-API_KEY}"
KV_BINDING="ROTATION_LOG"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:?SLACK_WEBHOOK_URL not set}"

# 1. Generate a cryptographically random 40-char hex secret
NEW_SECRET=$(openssl rand -hex 20)

# 2. Push to Workers via wrangler (reads from stdin)
echo -n "${NEW_SECRET}" | wrangler secret put "${SECRET_NAME}" --name "${WORKER_NAME}"

# 3. Record rotation in KV
ROTATION_KEY="${WORKER_NAME}:${SECRET_NAME}:last_rotated"
ROTATION_VALUE=$(jq -n \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg actor "${GITHUB_ACTOR:-cli}" \
  --arg run "${GITHUB_RUN_ID:-local}" \
  '{rotated_at: $ts, actor: $actor, run_id: $run}')

wrangler kv key put --binding="${KV_BINDING}" \
  "${ROTATION_KEY}" \
  "${ROTATION_VALUE}"

# 4. Post Slack notification
SLACK_PAYLOAD=$(jq -n \
  --arg worker "${WORKER_NAME}" \
  --arg secret "${SECRET_NAME}" \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg actor "${GITHUB_ACTOR:-cli}" \
  '{text: (":rotating_light: *Secret rotated*\nWorker: `" + $worker + "`\nSecret: `" + $secret + "`\nTime: " + $ts + "\nActor: " + $actor)}')

curl -sf -X POST \
  -H "Content-Type: application/json" \
  -d "${SLACK_PAYLOAD}" \
  "${SLACK_WEBHOOK_URL}"

echo "Rotation complete for ${WORKER_NAME}/${SECRET_NAME}"
```

## GitHub Actions workflow
```yaml
# .github/workflows/rotate-secrets.yml
name: Rotate Workers Secrets

on:
  schedule:
    - cron: '0 3 1 * *'   # 03:00 UTC on the 1st of every month
  workflow_dispatch:
    inputs:
      worker_name:
        description: 'Worker name override'
        required: false
        default: 'my-worker'
      secret_name:
        description: 'Secret binding name'
        required: false
        default: 'API_KEY'

jobs:
  rotate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
    steps:
      - uses: actions/checkout@v4

      - name: Install wrangler
        run: npm install -g wrangler@latest

      - name: Rotate secret
        run: |
          bash scripts/rotate-secret.sh \
            "${{ github.event.inputs.worker_name || 'my-worker' }}" \
            "${{ github.event.inputs.secret_name || 'API_KEY' }}"
```

## Worker — reading rotation metadata from KV
```typescript
// src/index.ts (snippet — verify secret freshness on startup)
export interface Env {
  ROTATION_LOG: KVNamespace;
  API_KEY: string;
  WORKER_NAME: string;
}

interface RotationRecord {
  rotated_at: string;
  actor: string;
  run_id: string;
}

async function assertSecretFreshness(env: Env, maxAgeDays = 35): Promise<void> {
  const key = `${env.WORKER_NAME}:API_KEY:<redacted-secret>
  const raw = await env.ROTATION_LOG.get(key);
  if (!raw) {
    console.warn('No rotation record found — secret may never have been rotated');
    return;
  }
  const record: RotationRecord = JSON.parse(raw);
  const ageMs = Date.now() - new Date(record.rotated_at).getTime();
  const ageDays = ageMs / 86_400_000;
  if (ageDays > maxAgeDays) {
    console.error(`Secret is ${ageDays.toFixed(1)} days old — rotation overdue!`);
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    ctx.waitUntil(assertSecretFreshness(env));
    // ... rest of handler
    return new Response('ok');
  },
};
```

---

## Anti-patterns
- **Storing the new secret value in a GitHub Actions output or log** — pipe it only through stdin to wrangler; never echo or export it.
- **Using `wrangler secret put` with `--env` without scoping the API token** — an overly broad token can rotate secrets on unintended Workers; scope the token to a single account and Worker.
- **Rotating without verifying the Worker is healthy afterwards** — add a smoke-test step after rotation (e.g. `curl` the Worker health endpoint) before the Slack notification declares success.

---

## Gotchas
- `wrangler secret put` triggers a Worker restart; if the new secret is invalid the Worker will start returning errors before you notice — always validate the secret upstream before pushing.
- The `CLOUDFLARE_API_TOKEN` must have `Workers Scripts: Edit` and `Account: KV Storage: Edit` permissions; the minimal scope is easy to misconfigure in the Cloudflare dashboard.
- KV writes are eventually consistent across regions; the rotation record may not be immediately visible in the Worker's `ROTATION_LOG.get()` call if the Worker is in a different region.

---

## Verification
```bash
# Manually trigger rotation via workflow dispatch
gh workflow run rotate-secrets.yml \
  -f worker_name=my-worker \
  -f secret_name=API_KEY

# Confirm KV record was written
wrangler kv key get --binding=ROTATION_LOG "my-worker:API_KEY:<redacted-secret>"

# Check wrangler sees the secret
wrangler secret list --name my-worker
```

---

## Related
- `workers-ip-allowlist-cloudflare-access-jwt.md`
- `cloudflare-tunnel-private-network-workers.md`

---

## Sources
- wrangler secret commands — https://developers.cloudflare.com/workers/wrangler/commands/#secret
- GitHub Actions scheduled workflows — https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule
- Cloudflare API token permissions — https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
