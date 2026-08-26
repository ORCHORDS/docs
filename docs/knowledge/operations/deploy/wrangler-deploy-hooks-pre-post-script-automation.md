# Wrangler Deploy Hooks: Pre/Post Script Automation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

After running `wrangler deploy`, you need to automatically execute follow-up tasks: purge a CDN cache layer, seed a KV namespace with feature flags, notify a Slack channel, or register the new deployment version with an external observability platform. Equally, before deploy you want to run lint, bundle analysis, or D1 migration dry-runs. Wrangler has no native plugin system, but the surrounding npm and shell layer gives you composable hook points that are reliable and versionable in source control.

## Context

Wrangler does not expose lifecycle hooks comparable to Webpack plugins or Gradle tasks. The entry points available are:

1. **`package.json` scripts** — `predeploy` / `postdeploy` npm lifecycle scripts run automatically before and after the `deploy` script.
2. **Shell composition in CI** — explicit `&&` chains or separate steps in GitHub Actions / GitLab CI give full control over sequencing and failure handling.
3. **Wrangler `--dispatch-namespace` and `--env` flags** — parameterize the deploy step without forking the hook scripts.

The npm lifecycle approach is the most portable: the same `npm run deploy` command in CI and locally produces the same hook execution.

## Pre-deploy Hooks via npm Lifecycle Scripts

```json
// package.json
{
  "scripts": {
    "predeploy": "npm run validate && npm run migrate:dry-run && npm run bundle:check",
    "deploy": "wrangler deploy",
    "postdeploy": "npm run cache:purge && npm run notify:slack && npm run smoke:test",
    "validate": "tsc --noEmit && wrangler deploy --dry-run --outdir dist/check",
    "migrate:dry-run": "wrangler d1 migrations apply DB --dry-run",
    "bundle:check": "tsx scripts/bundle-size-check.ts dist/",
    "cache:purge": "tsx scripts/purge-cf-cache.ts",
    "notify:slack": "tsx scripts/slack-notify.ts",
    "smoke:test": "tsx scripts/smoke-test.ts"
  }
}
```

`npm` runs `predeploy` before invoking the `deploy` script and `postdeploy` immediately after it exits with code 0. If `predeploy` exits non-zero, `deploy` never runs. If `deploy` exits non-zero, `postdeploy` is skipped. This makes the chain safe by default.

## Bundle Size Guard (Pre-deploy)

```typescript
// scripts/bundle-size-check.ts
import { statSync, readdirSync } from 'fs';
import { join } from 'path';

const WORKER_BUNDLE_LIMIT_BYTES = 10 * 1024 * 1024; // 10 MB (Wrangler default free tier)
const COMPRESSED_LIMIT_BYTES = 1 * 1024 * 1024;     // 1 MB compressed

function checkDir(dir: string): void {
  const files = readdirSync(dir);
  for (const file of files) {
    const filePath = join(dir, file);
    const stat = statSync(filePath);
    if (stat.isFile() && file.endsWith('.js')) {
      const sizeKb = Math.round(stat.size / 1024);
      if (stat.size > WORKER_BUNDLE_LIMIT_BYTES) {
        console.error(`FAIL bundle too large: ${filePath} is ${sizeKb} KB (limit: ${WORKER_BUNDLE_LIMIT_BYTES / 1024} KB)`);
        process.exit(1);
      }
      console.log(`✓ ${file}: ${sizeKb} KB`);
    }
  }
}

checkDir(process.argv[2] ?? 'dist');
```

## Cache Purge Hook (Post-deploy)

```typescript
// scripts/purge-cf-cache.ts
interface PurgeResult {
  result: { id: string };
  success: boolean;
  errors: Array<{ message: string }>;
}

async function purgeCacheByTags(tags: string[]): Promise<void> {
  const zoneId = process.env.CF_ZONE_ID;
  const apiToken = process.env.CLOUDFLARE_API_TOKEN;

  if (!zoneId || !apiToken) {
    throw new Error('CF_ZONE_ID and CLOUDFLARE_API_TOKEN must be set');
  }

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ tags }),
    }
  );

  const data = (await res.json()) as PurgeResult;
  if (!data.success) {
    throw new Error(`Cache purge failed: ${data.errors.map((e) => e.message).join(', ')}`);
  }
  console.log(`✓ Purged cache tags: ${tags.join(', ')} (id: ${data.result.id})`);
}

// Tags correspond to Cache-Tag response headers set by the Worker
purgeCacheByTags(['api-v1', 'worker-response']).catch((e) => {
  console.error(e.message);
  process.exit(1);
});
```

## Deployment Notification Hook (Post-deploy)

```typescript
// scripts/slack-notify.ts
interface SlackPayload {
  text: string;
  blocks: Array<{
    type: string;
    text?: { type: string; text: string };
    fields?: Array<{ type: string; text: string }>;
  }>;
}

async function notifySlack(): Promise<void> {
  const webhookUrl = process.env.SLACK_WEBHOOK_URL;
  if (!webhookUrl) {
    console.warn('SLACK_WEBHOOK_URL not set, skipping notification');
    return;
  }

  const workerName = process.env.WORKER_NAME ?? 'unknown-worker';
  const gitSha = process.env.GITHUB_SHA?.slice(0, 7) ?? 'local';
  const actor = process.env.GITHUB_ACTOR ?? 'developer';
  const branch = process.env.GITHUB_REF_NAME ?? 'main';
  const runUrl = process.env.GITHUB_SERVER_URL
    ? `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`
    : '';

  const payload: SlackPayload = {
    text: `Deployed ${workerName}@${gitSha}`,
    blocks: [
      {
        type: 'section',
        text: { type: 'mrkdwn', text: `*Deployed* \`${workerName}\`` },
      },
      {
        type: 'section',
        fields: [
          { type: 'mrkdwn', text: `*Branch:* ${branch}` },
          { type: 'mrkdwn', text: `*Commit:* ${gitSha}` },
          { type: 'mrkdwn', text: `*By:* ${actor}` },
          { type: 'mrkdwn', text: runUrl ? `*Run:* <${runUrl}|view>` : '*Run:* local' },
        ],
      },
    ],
  };

  const res = await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Slack notification failed: ${res.status}`);
  }
  console.log('✓ Slack notification sent');
}

notifySlack().catch((e) => {
  // Notification failure should not block CI — log and exit 0
  console.warn(`Slack notification error: ${e.message}`);
});
```

## Capturing the Wrangler Deploy Output

Wrangler prints the deployment URL and version ID to stdout. Capture it in CI to pass downstream to notification and smoke-test scripts:

```bash
# In CI shell or Makefile
DEPLOY_OUTPUT=$(npx wrangler deploy 2>&1 | tee /dev/stderr)
WORKER_URL=$(echo "$DEPLOY_OUTPUT" | grep -oP 'https://[^\s]+\.workers\.dev')
VERSION_ID=$(echo "$DEPLOY_OUTPUT" | grep -oP '(?<=Version ID: )[a-f0-9-]+')

export WORKER_URL VERSION_ID
npx tsx scripts/smoke-test.ts
npx tsx scripts/slack-notify.ts
```

Alternatively, use `wrangler versions upload` which outputs structured JSON with `--json` for easier parsing:

```typescript
// scripts/parse-deploy-output.ts
import { execSync } from 'child_process';

const output = execSync('npx wrangler versions upload --json', { encoding: 'utf8' });
const result = JSON.parse(output) as { id: string; number: number; resources: { bindings: unknown[] } };
console.log(`Uploaded version ${result.id} (#${result.number})`);
process.env.WRANGLER_VERSION_ID = result.id;
```

## CI Integration with Failure Isolation

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - run: npm ci

      # Pre-deploy hooks run here via predeploy npm lifecycle
      # Post-deploy hooks run here via postdeploy npm lifecycle
      - name: Deploy (with hooks)
        run: npm run deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ZONE_ID: ${{ secrets.CF_ZONE_ID }}
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          WORKER_NAME: my-api

      # Separate step for post-deploy monitoring enrollment
      - name: Register deployment with observability platform
        if: success()
        run: npx tsx scripts/register-deploy.ts
        env:
          DATADOG_API_KEY: ${{ secrets.DATADOG_API_KEY }}
```

## Anti-patterns

- **Running `wrangler deploy` directly in CI without npm scripts** — bypasses `predeploy` / `postdeploy` hooks and makes hook execution inconsistent between local and CI.
- **Putting cache purge or notifications inside the Worker script itself** — the Worker runs per-request, not per-deploy; these are deploy-time side effects.
- **Using `postdeploy` for operations that must succeed for the deploy to be valid** — `postdeploy` runs after `deploy` exits 0; a failure there does not roll back the deploy. Put required post-deploy checks in a separate pipeline step with explicit rollback logic.
- **Hard-coding zone IDs or API tokens inside hook scripts** — always use environment variables; hook scripts run locally too.

## Gotchas

- npm's `pre`/`post` lifecycle only fires when the script is invoked via `npm run deploy`, not `npx wrangler deploy` or `yarn wrangler deploy`. Standardize on `npm run deploy` in all documentation and CI configs.
- `wrangler deploy --dry-run` also triggers `predeploy` when called via npm. If your `predeploy` includes a `wrangler deploy --dry-run`, you create infinite recursion. Invoke the dry-run script with `wrangler deploy --dry-run` directly, not via the deploy npm script alias.
- On yarn v2+ (PnP), the `pre`/`post` lifecycle scripts are disabled by default. Set `enableScripts: true` in `.yarnrc.yml` or compose hooks explicitly in CI steps.

## Verification

```bash
# Dry-run to confirm hooks fire in sequence without deploying
DRY_RUN=true npm run deploy

# Check that postdeploy ran by looking at Slack or the cache purge log
# In CI, inspect the step output for:
# ✓ Bundle check passed
# ✓ D1 migration dry-run OK
# ✓ Deployed to workers.dev
# ✓ Purged cache tags: api-v1
# ✓ Slack notification sent
```

## Related

- `pages-deployment-hooks-post-deploy-scripts.md`
- `wrangler-config-validation-pre-deploy-ci-hook.md`
- `deploy-notification-webhooks-slack-teams-workers.md`
- `workers-deployment-diff-changelog-automation.md`

## Sources

- npm lifecycle scripts: https://docs.npmjs.com/cli/v10/using-npm/scripts#pre--post-scripts
- Wrangler deploy flags: https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- Wrangler versions upload: https://developers.cloudflare.com/workers/wrangler/commands/#versions-upload
- Cloudflare cache purge API: https://developers.cloudflare.com/api/operations/zone-purge
