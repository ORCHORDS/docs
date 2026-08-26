# Post-Deploy Slack Notification from GitHub Actions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After `wrangler deploy` runs in CI you want your team's Slack channel to receive a
message that includes the deployment status (success or failure), the worker name,
the deployment URL, and the version tag — without adding an external action or
third-party SDK.

## Context

- Cloudflare Workers deployment via Wrangler CLI in GitHub Actions.
- Slack Incoming Webhook already created and stored as a GitHub Actions secret
  (`SLACK_WEBHOOK_URL`).
- `wrangler deploy` prints structured information to stdout including the Worker URL
  and a version ID.

---

## Section 1 — Capture wrangler deploy output

Run `wrangler deploy` and tee its stdout so it is available both on the Actions log
and in a file you can parse afterwards.

```yaml
# .github/workflows/deploy.yml
name: Deploy Worker

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: npm ci

      - name: Deploy Worker
        id: deploy
        # tee duplicates stdout: terminal + file
        run: |
          set +e
          npx wrangler deploy 2>&1 | tee /tmp/wrangler-output.txt
          echo "exit_code=${PIPESTATUS[0]}" >> "$GITHUB_OUTPUT"
          set -e

      - name: Parse deploy output
        id: parse
        run: |
          OUTPUT=$(cat /tmp/wrangler-output.txt)

          # Extract worker URL (line that starts with https://)
          DEPLOY_URL=$(echo "$OUTPUT" | grep -oP 'https://[^\s]+\.workers\.dev[^\s]*' | head -1)

          # Extract version ID — wrangler prints "Version ID: <uuid>"
          VERSION_ID=$(echo "$OUTPUT" | grep -oP '(?<=Version ID: )[\w-]+' | head -1)

          echo "deploy_url=${DEPLOY_URL}" >> "$GITHUB_OUTPUT"
          echo "version_id=${VERSION_ID}" >> "$GITHUB_OUTPUT"

      - name: Notify Slack — success
        if: steps.deploy.outputs.exit_code == '0'
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          curl -fsSL -X POST "$SLACK_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "$(cat <<EOF
          {
            "text": ":white_check_mark: *Worker deployed successfully*",
            "blocks": [
              {
                "type": "section",
                "text": {
                  "type": "mrkdwn",
                  "text": ":white_check_mark: *Worker deployed*\\nRepo: <${{ github.server_url }}/${{ github.repository }}|${{ github.repository }}>\\nCommit: <${{ github.server_url }}/${{ github.repository }}/commit/${{ github.sha }}|${{ github.sha }}>"
                }
              },
              {
                "type": "section",
                "fields": [
                  { "type": "mrkdwn", "text": "*URL:*\\n<${{ steps.parse.outputs.deploy_url }}|${{ steps.parse.outputs.deploy_url }}>" },
                  { "type": "mrkdwn", "text": "*Version:*\\n`${{ steps.parse.outputs.version_id }}`" }
                ]
              }
            ]
          }
          EOF
          )"

      - name: Notify Slack — failure
        if: steps.deploy.outputs.exit_code != '0'
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          curl -fsSL -X POST "$SLACK_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "$(cat <<EOF
          {
            "text": ":x: *Worker deploy FAILED*",
            "blocks": [
              {
                "type": "section",
                "text": {
                  "type": "mrkdwn",
                  "text": ":x: *Worker deploy FAILED*\\nRepo: <${{ github.server_url }}/${{ github.repository }}|${{ github.repository }}>\\nCommit: <${{ github.server_url }}/${{ github.repository }}/commit/${{ github.sha }}|${{ github.sha }}>\\n\\nCheck the <${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}|Actions log> for details."
                }
              }
            ]
          }
          EOF
          )"
          exit 1   # propagate failure
```

---

## Section 2 — Reusable notification script (TypeScript)

For teams that prefer keeping notification logic in version-controlled TypeScript
rather than inline shell:

```typescript
// scripts/notify-slack.ts
import { readFileSync } from 'node:fs';

interface SlackBlock {
  type: string;
  text?: { type: string; text: string };
  fields?: { type: string; text: string }[];
}

interface SlackPayload {
  text: string;
  blocks: SlackBlock[];
}

async function notifySlack(
  webhookUrl: string,
  status: 'success' | 'failure',
  deployUrl: string,
  versionId: string,
  repoUrl: string,
  commitSha: string,
  runUrl: string,
): Promise<void> {
  const isSuccess = status === 'success';

  const payload: SlackPayload = {
    text: isSuccess ? ':white_check_mark: Worker deployed' : ':x: Worker deploy FAILED',
    blocks: [
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: isSuccess
            ? `:white_check_mark: *Worker deployed*\nRepo: <${repoUrl}|repo> · Commit: \`${commitSha.slice(0, 7)}\``
            : `:x: *Worker deploy FAILED*\nRepo: <${repoUrl}|repo> · <${runUrl}|View logs>`,
        },
      },
      ...(isSuccess
        ? [
            {
              type: 'section',
              fields: [
                { type: 'mrkdwn', text: `*URL:*\n<${deployUrl}|${deployUrl}>` },
                { type: 'mrkdwn', text: `*Version:*\n\`${versionId}\`` },
              ],
            } satisfies SlackBlock,
          ]
        : []),
    ],
  };

  const response = await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Slack webhook returned ${response.status}: ${await response.text()}`);
  }
}

// Parse wrangler output file
const outputPath = process.argv[2] ?? '/tmp/wrangler-output.txt';
const output = readFileSync(outputPath, 'utf8');

const deployUrl = output.match(/https:\/\/[^\s]+\.workers\.dev[^\s]*/)?.[0] ?? '';
const versionId = output.match(/Version ID: ([\w-]+)/)?.[1] ?? 'unknown';
const status = (process.env.DEPLOY_STATUS ?? 'failure') as 'success' | 'failure';

await notifySlack(
  process.env.SLACK_WEBHOOK_URL!,
  status,
  deployUrl,
  versionId,
  process.env.GITHUB_REPOSITORY_URL ?? '',
  process.env.GITHUB_SHA ?? '',
  process.env.GITHUB_RUN_URL ?? '',
);

console.log('Slack notification sent.');
```

Call it from the workflow step:

```yaml
- name: Notify Slack
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
    DEPLOY_STATUS: ${{ steps.deploy.outputs.exit_code == '0' && 'success' || 'failure' }}
    GITHUB_REPOSITORY_URL: ${{ github.server_url }}/${{ github.repository }}
    GITHUB_RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
  run: npx tsx scripts/notify-slack.ts /tmp/wrangler-output.txt
  if: always()
```

---

## Section 3 — Verification

```bash
# Dry-run: send a test payload directly
curl -fsSL -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Test notification from CI dry-run"
  }'

# Confirm wrangler output parsing locally
npx wrangler deploy --dry-run 2>&1 | tee /tmp/wrangler-output.txt
grep -oP 'https://[^\s]+\.workers\.dev[^\s]*' /tmp/wrangler-output.txt
grep -oP '(?<=Version ID: )[\w-]+' /tmp/wrangler-output.txt
```

Expected Slack message fields:
- `text` top-level field (for push notifications and accessibility)
- At least one block with `mrkdwn` type
- `deploy_url` resolves to your worker subdomain
- `version_id` is a UUID or short hex string

---

## Anti-patterns

- **Sending the full wrangler stdout as Slack text** — output can exceed Slack's 3000-
  character block limit; always parse and extract the relevant fields.
- **Using `exit 0` unconditionally** — mask the wrangler failure status before the
  Slack step and you'll never detect broken deploys.
- **Hardcoding the webhook URL** — rotate secrets via GitHub Actions secrets, not
  source code.
- **Skipping `if: always()`** — without it the failure notification step is skipped
  when the deploy step fails.

## Gotchas

- `PIPESTATUS` is bash-specific; the workflow step must use `bash` shell (`shell: bash`)
  or the exit code check will silently use the `tee` exit code instead.
- Wrangler URL format changed between major versions — the regex above matches both
  `<name>.<subdomain>.workers.dev` and `<name>-<hash>.<subdomain>.workers.dev`.
- GitHub Actions expression `${{ steps.x.outputs.exit_code == '0' && 'success' || 'failure' }}`
  evaluates left-to-right; the ternary-like pattern only works because 'success' is truthy.

## Related

- `workers-version-binding-traffic-migration.md`
- `workers-deployment-gates-manual-approval.md`
- Cloudflare Workers deployment docs: https://developers.cloudflare.com/workers/wrangler/commands/#deploy

## Sources

- Slack Block Kit builder: https://app.slack.com/block-kit-builder
- GitHub Actions expressions: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/evaluate-expressions-in-workflows-and-actions
- Wrangler CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/
