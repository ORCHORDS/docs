# PR Preview Environments with Wrangler

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your team reviews PRs by reading code diffs alone. Reviewers cannot interact with the actual changes before merge. You want every PR to automatically get a live preview Worker on a unique URL so reviewers can click through real API responses, and you want that environment torn down automatically when the PR is closed.

## Context

Wrangler does not have a first-party "preview environment per PR" concept like Cloudflare Pages does. However, you can achieve the same result by deploying a Workers route scoped to a PR-specific subdomain (`pr-<number>.preview.example.com`) from GitHub Actions. A D1 preview database branch (or a shared preview D1 with per-PR table prefix) isolates data. The preview URL is posted as a PR comment via the GitHub API.

## Solution

### Dynamic wrangler config for preview environments

Instead of a static `wrangler.toml` env, generate a temporary config file at deploy time:

```typescript
// scripts/generate-preview-config.ts
import { writeFileSync } from "fs";

const PR_NUMBER = process.env.PR_NUMBER!;
const PREVIEW_KV_ID = process.env.PREVIEW_KV_ID!;
const PREVIEW_D1_ID = process.env.PREVIEW_D1_ID!;
const ZONE_NAME = "example.com";

const config = {
  name: `api-worker-pr-${PR_NUMBER}`,
  main: "src/index.ts",
  compatibility_date: "2025-01-01",
  vars: {
    APP_ENV: "preview",
    PR_NUMBER,
  },
  kv_namespaces: [
    { binding: "CACHE", id: PREVIEW_KV_ID },
  ],
  d1_databases: [
    {
      binding: "DB",
      database_name: `api-db-preview-${PR_NUMBER}`,
      database_id: PREVIEW_D1_ID,
    },
  ],
  routes: [
    {
      pattern: `pr-${PR_NUMBER}.preview.example.com/*`,
      zone_name: ZONE_NAME,
    },
  ],
};

// Write TOML-equivalent as JSON for wrangler --config
writeFileSync("wrangler.preview.json", JSON.stringify(config, null, 2));
console.log(`Preview config written for PR #${PR_NUMBER}`);
```

### D1 preview database provisioning

```typescript
// scripts/provision-preview-d1.ts
import Cloudflare from "cloudflare";

const cf = new Cloudflare({ apiToken: process.env.CF_API_TOKEN });
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const PR_NUMBER = process.env.PR_NUMBER!;
const MIGRATIONS_DIR = "./migrations";
import { readdirSync, readFileSync } from "fs";
import { join } from "path";

async function main(): Promise<void> {
  const dbName = `api-db-preview-${PR_NUMBER}`;

  // Check if preview DB already exists
  const databases = await cf.d1.database.list({ account_id: ACCOUNT_ID });
  const existing = databases.result.find((db) => db.name === dbName);

  let databaseId: string;
  if (existing) {
    console.log(`Reusing existing preview DB: ${dbName} (${existing.uuid})`);
    databaseId = existing.uuid;
  } else {
    console.log(`Creating preview D1 database: ${dbName}`);
    const created = await cf.d1.database.create({ account_id: ACCOUNT_ID, name: dbName });
    databaseId = created.uuid;
    console.log(`Created: ${databaseId}`);

    // Run all migrations on the new DB
    const migrationFiles = readdirSync(MIGRATIONS_DIR)
      .filter((f) => f.endsWith(".sql"))
      .sort();

    for (const file of migrationFiles) {
      const sql = readFileSync(join(MIGRATIONS_DIR, file), "utf-8");
      await cf.d1.database.query(databaseId, { account_id: ACCOUNT_ID, sql });
      console.log(`  Applied migration: ${file}`);
    }
  }

  // Write the DB ID to a file for the next step
  const { writeFileSync } = await import("fs");
  writeFileSync(".preview-d1-id", databaseId);
  console.log(`Preview D1 ID written: ${databaseId}`);
}

main().catch((err) => { console.error(err); process.exit(1); });
```

### GitHub Actions PR deploy workflow

```yaml
# .github/workflows/preview.yml
name: PR Preview

on:
  pull_request:
    types: [opened, synchronize, reopened, closed]

jobs:
  deploy-preview:
    if: github.event.action != 'closed'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci

      - name: Provision preview D1 database
        run: npx ts-node scripts/provision-preview-d1.ts
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          PR_NUMBER: ${{ github.event.pull_request.number }}

      - name: Generate preview wrangler config
        run: |
          PREVIEW_D1_ID=$(cat .preview-d1-id)
          PR_NUMBER=${{ github.event.pull_request.number }} \
          PREVIEW_KV_ID=${{ secrets.PREVIEW_KV_ID }} \
          PREVIEW_D1_ID=$PREVIEW_D1_ID \
          npx ts-node scripts/generate-preview-config.ts
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Deploy preview Worker
        run: npx wrangler deploy --config wrangler.preview.json
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Post preview URL as PR comment
        uses: actions/github-script@v7
        with:
          script: |
            const pr = context.payload.pull_request.number;
            const url = `https://pr-${pr}.preview.example.com`;
            const body = [
              `### Preview Environment`,
              ``,
              `A preview Worker has been deployed for this PR.`,
              ``,
              `**URL:** ${url}`,
              `**Health:** ${url}/healthz`,
              ``,
              `> This preview will be torn down automatically when the PR is closed.`,
            ].join('\n');

            // Update existing comment or create new one
            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: pr,
            });

            const existing = comments.find(c =>
              c.user?.login === 'github-actions[bot]' &&
              c.body?.includes('Preview Environment')
            );

            if (existing) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                comment_id: existing.id,
                body,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: pr,
                body,
              });
            }

  teardown-preview:
    if: github.event.action == 'closed'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci

      - name: Delete preview Worker
        run: |
          npx wrangler delete api-worker-pr-${{ github.event.pull_request.number }} \
            --force
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Delete preview D1 database
        run: npx ts-node scripts/teardown-preview-d1.ts
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
```

### Preview teardown script

```typescript
// scripts/teardown-preview-d1.ts
import Cloudflare from "cloudflare";

const cf = new Cloudflare({ apiToken: process.env.CF_API_TOKEN });
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const PR_NUMBER = process.env.PR_NUMBER!;

async function main(): Promise<void> {
  const dbName = `api-db-preview-${PR_NUMBER}`;
  const databases = await cf.d1.database.list({ account_id: ACCOUNT_ID });
  const target = databases.result.find((db) => db.name === dbName);

  if (!target) {
    console.log(`No preview D1 database found for PR #${PR_NUMBER}. Skipping.`);
    return;
  }

  await cf.d1.database.delete(target.uuid, { account_id: ACCOUNT_ID });
  console.log(`Deleted preview D1 database: ${dbName} (${target.uuid})`);
}

main().catch((err) => { console.error(err); process.exit(1); });
```

### Preview environment Worker flag

```typescript
// src/index.ts — preview-specific behavior
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Banner for preview environments — identify the PR in API responses
    if (env.APP_ENV === "preview") {
      const response = await router(url, request, env);
      const newHeaders = new Headers(response.headers);
      newHeaders.set("X-Preview-PR", env.PR_NUMBER ?? "unknown");
      newHeaders.set("X-Preview-Warning", "This is a preview environment. Data may be reset.");
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: newHeaders,
      });
    }

    return router(url, request, env);
  },
};
```

## Implementation Details

- The DNS wildcard `*.preview.example.com` must be set up as a Cloudflare-proxied CNAME pointing to `<zone>.workers.dev` before this workflow can route traffic. Add it once via the Cloudflare dashboard or Terraform.
- Use a single shared preview KV namespace across all PR environments (with a `pr-<number>:` key prefix convention in your code) to avoid hitting the KV namespace limit per account.
- `wrangler.preview.json` is generated at runtime and must not be committed to the repository. Add it to `.gitignore`.
- Protect the preview subdomain from crawlers by returning `X-Robots-Tag: noindex, nofollow` on all preview responses.

## Anti-patterns

- **Sharing a preview database across PRs**: Two concurrent PRs mutating the same D1 database will interfere. Use per-PR databases or per-PR table prefixes enforced in the application layer.
- **Not cleaning up on PR close**: Orphaned preview Workers accumulate and can hit account limits. Always handle the `closed` PR event.
- **Deploying previews on draft PRs**: Use `github.event.pull_request.draft == false` in the job `if` condition to avoid burning resources on WIP branches.
- **Hardcoding the preview domain in application code**: The preview URL must come from environment config (`APP_ENV`, `PR_NUMBER`) not from hardcoded strings.

## Gotchas

- `wrangler delete` requires the exact Worker name. If the deploy step failed partway through, the Worker may not exist. Add `|| true` (or catch the error in a script) so the teardown step does not fail the entire workflow.
- GitHub Actions `pull_request` events from forks do not have access to repository secrets by default. Preview deploys from fork PRs require `pull_request_target` with careful permission scoping — or a separate approve-and-deploy workflow pattern.
- The Cloudflare API rate limit for creating Workers is 20/minute. On repos with burst activity (many PRs opened simultaneously), adds a retry loop with exponential backoff.
- Preview Workers share the same account limits as production Workers (CPU time, subrequest budget). Isolate preview routes by domain to prevent a runaway test from exhausting production budgets.

## Verification

```bash
# List all preview Workers
wrangler list | grep api-worker-pr

# Check the preview URL for PR #<number>
curl -s https://pr-42.preview.example.com/healthz | jq .

# Verify preview headers are set
curl -sI https://pr-42.preview.example.com/healthz | grep -i x-preview

# Confirm teardown removed the D1 database
wrangler d1 list | grep preview-42
```

## Related

- `workers-environment-promotion-pipeline.md`
- `workers-deployment-verification-smoke-tests.md`
- `workers-zero-downtime-d1-migration-deploy.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#delete
- https://developers.cloudflare.com/d1/platform/client-api/
- https://developers.cloudflare.com/workers/configuration/routing/routes/
- https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#pull_request
- https://developers.cloudflare.com/fundamentals/api/how-to/manage-wildcard-domains/
