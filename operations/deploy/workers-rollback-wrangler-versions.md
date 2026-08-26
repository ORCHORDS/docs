# Rolling Back a Workers Deployment with wrangler versions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A deployment just went out and error rates spiked or a critical regression was detected. You need to revert to the last known-good version of your Worker without waiting for a new code push, code review, or CI run. Wrangler's versioned deployments let you promote any previous version back to 100 % traffic in seconds.

---

## Context

As of `wrangler` 3.40+ (and the Cloudflare Workers Versions API), every `wrangler deploy` creates a numbered version record. Versions are distinct from deployments: a deployment is a traffic-weight assignment across one or more versions. You can split traffic 90/10 across two versions, or promote a single version to 100 %. `wrangler versions list` shows all available versions with their IDs and metadata. `wrangler versions deploy --version-id <id> --percentage 100` atomically shifts all traffic to the chosen version with no cold-start penalty — the script bundle is already on the Cloudflare network. In CI you can query Analytics Engine for error rate, and if the rate exceeds a threshold within a monitoring window, automatically invoke the rollback in the same pipeline step.

---

## Section 1 — Config / wrangler.toml

```toml
name = "api"
main = "src/worker.ts"
compatibility_date = "2026-08-01"

# Versioned deployments are enabled by default on accounts
# using the new Workers platform. No extra config needed.
# Optional: tag each deploy with metadata for easier listing.
[deploy]
tag = "git-$GIT_SHA"
```

---

## Section 2 — Implementation / Rollback Script

```typescript
// scripts/rollback.ts  (run with: npx tsx scripts/rollback.ts)
import { execSync } from "child_process";

interface WranglerVersion {
  id: string;
  number: number;
  metadata: {
    created_on: string;
    author_email: string;
    source: string;
    tag?: string;
  };
  annotations?: {
    "workers/message"?: string;
    "workers/tag"?: string;
  };
}

function runWrangler(args: string): string {
  return execSync(`wrangler ${args} --json 2>/dev/null`, {
    encoding: "utf8",
    env: { ...process.env },
  }).trim();
}

async function getVersions(): Promise<WranglerVersion[]> {
  const output = runWrangler("versions list");
  const parsed = JSON.parse(output);
  // wrangler returns { result: [...] } or the array directly depending on version
  return Array.isArray(parsed) ? parsed : parsed.result ?? [];
}

async function rollbackToVersion(versionId: string): Promise<void> {
  console.log(`Rolling back to version: ${versionId}`);
  execSync(
    `wrangler versions deploy --version-id ${versionId} --percentage 100 --yes`,
    { stdio: "inherit", env: { ...process.env } }
  );
  console.log("Rollback complete.");
}

async function main() {
  const targetId = process.argv[2];

  if (!targetId) {
    // No explicit ID — list versions and roll back to the previous one
    const versions = await getVersions();
    if (versions.length < 2) {
      console.error("Not enough versions to roll back.");
      process.exit(1);
    }
    // versions are ordered newest-first
    const previous = versions[1];
    console.log(
      `No version ID supplied. Rolling back to previous: ${previous.id} ` +
      `(created ${previous.metadata.created_on})`
    );
    await rollbackToVersion(previous.id);
  } else {
    await rollbackToVersion(targetId);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

```bash
#!/usr/bin/env bash
# scripts/auto-rollback.sh
# Usage: called from CI after a deploy step.
# Reads DEPLOY_VERSION_ID from the environment (set by the deploy step).
# Queries Analytics Engine for error rate; rolls back if threshold exceeded.
set -euo pipefail

ACCOUNT_ID="${CF_ACCOUNT_ID:?}"
API_TOKEN="${CLOUDFLARE_API_TOKEN:?}"
ERROR_THRESHOLD="${ERROR_THRESHOLD:-1}"        # percent
MONITOR_WINDOW="${MONITOR_WINDOW:-300}"        # seconds
DEPLOY_VERSION_ID="${DEPLOY_VERSION_ID:?}"

echo "Monitoring for ${MONITOR_WINDOW}s after deploy..."
sleep "$MONITOR_WINDOW"

QUERY="SELECT SUM(_sample_interval * is_error) / SUM(_sample_interval) * 100 AS err_pct
       FROM api_requests
       WHERE timestamp >= NOW() - INTERVAL '$(( MONITOR_WINDOW / 60 ))' MINUTE"

ERR_PCT=$(curl -sf -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"${QUERY}\"}" \
  | jq -r '.result.data[0].err_pct // 0')

echo "Error rate in last $(( MONITOR_WINDOW / 60 )) min: ${ERR_PCT}%"

if (( $(echo "$ERR_PCT > $ERROR_THRESHOLD" | bc -l) )); then
  echo "ERROR: error rate ${ERR_PCT}% exceeds threshold ${ERROR_THRESHOLD}%"
  echo "Rolling back to previous version..."

  # Get the previous version ID (the one before DEPLOY_VERSION_ID)
  PREV_VERSION=$(wrangler versions list --json 2>/dev/null \
    | jq -r --arg cur "$DEPLOY_VERSION_ID" \
      '[.result // .][0][] | select(.id != $cur) | .id' \
    | head -1)

  if [[ -z "$PREV_VERSION" ]]; then
    echo "ERROR: could not determine previous version ID"
    exit 1
  fi

  wrangler versions deploy \
    --version-id "$PREV_VERSION" \
    --percentage 100 \
    --yes

  echo "Rolled back to version: $PREV_VERSION"
  exit 1
fi

echo "Error rate within threshold. Deployment healthy."
```

---

## Section 3 — CI / Automation

```yaml
# .github/workflows/deploy-with-rollback.yml
name: Deploy with Auto-Rollback

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Install wrangler
        run: npm install -g wrangler

      - name: Deploy
        id: deploy
        run: |
          wrangler deploy --json 2>/dev/null | tee deploy-output.json
          VERSION_ID=$(jq -r '.versions[0].version_id // empty' deploy-output.json)
          echo "version_id=$VERSION_ID" >> $GITHUB_OUTPUT
          echo "Deployed version: $VERSION_ID"

      - name: Monitor and auto-rollback
        env:
          DEPLOY_VERSION_ID: ${{ steps.deploy.outputs.version_id }}
          MONITOR_WINDOW: "120"
          ERROR_THRESHOLD: "0.5"
        run: bash scripts/auto-rollback.sh

      - name: Annotate deployment
        if: success()
        run: |
          wrangler versions upload \
            --message "Deployed from ${{ github.sha }} by ${{ github.actor }}" \
            || true  # annotation is best-effort
```

---

## Anti-patterns

- **Re-deploying old code via `git revert` + CI** — a new code push takes 2–10 minutes through the full CI pipeline; `wrangler versions deploy` is near-instant and does not require a new upload.
- **Pinning rollback to `versions[1]` without verifying health** — the second-newest version may also be broken; always verify the target version ID against deployment notes or tags before promoting.
- **Treating `wrangler rollback` (the deprecated alias) as current** — use `wrangler versions deploy` which is the stable API; the old `rollback` sub-command was removed in wrangler 4.
- **Skipping `--yes` in automated scripts** — without `--yes`, wrangler prompts for confirmation and the CI job hangs until timeout.

---

## Gotchas

- `wrangler versions list --json` output schema changed between wrangler 3 and 4; the rollback script normalises both with `[.result // .][0][]`.
- Environment variables and secrets are resolved at deploy time, not at version creation time. Rolling back the script does not roll back KV/D1 data or secret values.
- `wrangler versions deploy` with `--percentage 100` and a single version ID is equivalent to a full cutover; split deployments (e.g. 50/50 across two versions) require multiple `--version-id`/`--percentage` pairs.
- The Workers Versions API is account-scoped and requires the `Account:Workers Scripts:Edit` permission.
- Versions are retained for 30 days; after that the version ID is no longer valid for promotion.

---

## Verification

```bash
# List all versions with creation time
wrangler versions list

# Show versions as JSON for scripting
wrangler versions list --json | jq '.result // . | .[] | {id, created: .metadata.created_on, tag: .annotations["workers/tag"]}'

# Promote a specific version to 100 %
wrangler versions deploy --version-id <version-id> --percentage 100 --yes

# Verify currently deployed version
wrangler versions view <version-id>

# Check live traffic split
wrangler deployments list
```

---

## Related

- `wrangler-deploy-canary-percentage-routing.md`
- `workers-blue-green-deployment-kv-feature-flags.md`
- `workers-deployment-smoke-test-health-check.md`

---

## Sources

- Cloudflare Workers Versions — https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Wrangler versions commands — https://developers.cloudflare.com/workers/wrangler/commands/#versions
- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
