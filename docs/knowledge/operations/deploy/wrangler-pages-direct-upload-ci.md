# Wrangler Pages Direct Upload in CI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Teams building Cloudflare Pages projects inside a monorepo or with a custom build pipeline need to upload build artifacts directly via Wrangler rather than relying on Cloudflare's Git integration, which cannot selectively trigger on a sub-directory or insert custom pre-upload checks.

## Context
`wrangler pages deploy <directory>` (the "direct upload" flow) decouples the build step from Cloudflare's own CI infrastructure. The command uploads assets to the Pages asset store and optionally attaches Pages Functions from a separate directory. This is the recommended path for monorepos (e.g., Turborepo, Nx), locked build toolchains, or pipelines that must run static analysis or bundle size checks before the upload. Branch previews and production deploys share the same command — only the `--branch` flag differs.

## wrangler.toml for Pages Projects

Pages projects using direct upload do not strictly need a `wrangler.toml`, but defining one enables typed bindings for Pages Functions.

```toml
# apps/web/wrangler.toml
name = "orchords-web"
pages_build_output_dir = "dist"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "FEATURE_FLAGS"
id = "your-kv-namespace-id"

[[d1_databases]]
binding = "DB"
database_name = "orchords-prod"
database_id = "your-d1-database-id"
```

## Pages Function with Typed Bindings

```typescript
// apps/web/functions/api/user.ts
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
  FEATURE_FLAGS: KVNamespace;
}

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const url = new URL(request.url);
  const userId = url.searchParams.get("id");

  if (!userId) {
    return Response.json({ error: "Missing id" }, { status: 400 });
  }

  const flagEnabled = await env.FEATURE_FLAGS.get("new-profile-ui");

  const user = await env.DB.prepare(
    "SELECT id, name, email FROM users WHERE id = ? LIMIT 1"
  )
    .bind(userId)
    .first();

  if (!user) {
    return Response.json({ error: "Not found" }, { status: 404 });
  }

  return Response.json({ ...user, newProfileUi: flagEnabled === "true" });
};
```

## CI Deploy Script (GitHub Actions)

```yaml
# .github/workflows/pages-deploy.yml
name: Pages Deploy

on:
  push:
    branches: [main]
    paths:
      - "apps/web/**"
      - ".github/workflows/pages-deploy.yml"
  pull_request:
    paths:
      - "apps/web/**"

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      deployments: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npx turbo run build --filter=orchords-web
        env:
          NODE_ENV: production

      - name: Bundle size check
        run: npx tsx scripts/check-bundle-size.ts --max-kb 512 apps/web/dist

      - name: Deploy to Cloudflare Pages
        run: |
          BRANCH="${{ github.head_ref || github.ref_name }}"
          npx wrangler pages deploy apps/web/dist \
            --project-name orchords-web \
            --branch "$BRANCH" \
            --commit-hash "${{ github.sha }}" \
            --commit-message "${{ github.event.head_commit.message }}"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_PAGES_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

## Bundle Size Gate Script

```typescript
// scripts/check-bundle-size.ts
import { readdirSync, statSync } from "fs";
import { join, extname } from "path";

const MAX_KB = parseInt(
  process.argv.find((a) => a.startsWith("--max-kb="))?.split("=")[1] ?? "512"
);
const DIR = process.argv[process.argv.length - 1];

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(full);
    else yield full;
  }
}

const JS_EXTENSIONS = new Set([".js", ".mjs", ".cjs"]);
let totalBytes = 0;
const oversized: string[] = [];

for (const file of walk(DIR)) {
  if (!JS_EXTENSIONS.has(extname(file))) continue;
  const bytes = statSync(file).size;
  totalBytes += bytes;
  const kb = bytes / 1024;
  if (kb > MAX_KB) {
    oversized.push(`${file}: ${kb.toFixed(1)} KB`);
  }
}

console.log(`Total JS bundle size: ${(totalBytes / 1024).toFixed(1)} KB`);
if (oversized.length > 0) {
  console.error("Files exceeding limit:");
  oversized.forEach((f) => console.error(`  ${f}`));
  process.exit(1);
}
console.log("Bundle size check passed.");
```

## Preview URL Extraction and Comment Posting

```typescript
// scripts/post-preview-url.ts
import { execSync } from "child_process";

const PROJECT = "orchords-web";
const BRANCH = process.env.BRANCH_NAME!;
const GH_TOKEN = process.env.GITHUB_TOKEN!;
const PR_NUMBER = process.env.PR_NUMBER!;
const REPO = process.env.GITHUB_REPOSITORY!;

const CF_ACCOUNT = process.env.CF_ACCOUNT_ID!;
const CF_TOKEN = process.env.CF_API_TOKEN!;

async function getLatestPreviewUrl(): Promise<string> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}/pages/projects/${PROJECT}/deployments?page=1&per_page=5`,
    { headers: { Authorization: `Bearer ${CF_TOKEN}` } }
  );
  const json = (await resp.json()) as {
    result: Array<{ url: string; deployment_trigger: { metadata: { branch: string } } }>;
  };
  const match = json.result.find(
    (d) => d.deployment_trigger.metadata.branch === BRANCH
  );
  return match?.url ?? "";
}

async function postComment(previewUrl: string): Promise<void> {
  await fetch(`https://api.github.com/repos/${REPO}/issues/${PR_NUMBER}/comments`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${GH_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      body: `**Preview deployment ready:** ${previewUrl}`,
    }),
  });
}

(async () => {
  const url = await getLatestPreviewUrl();
  if (url) {
    await postComment(url);
    console.log(`Posted preview URL: ${url}`);
  } else {
    console.warn("No matching deployment found for branch:", BRANCH);
  }
})();
```

## Anti-patterns
- Uploading `dist/` without running a build first — `wrangler pages deploy` does not build; it only uploads
- Committing `CLOUDFLARE_API_TOKEN` to the repository instead of storing it in CI secrets
- Using the same API token for Pages deploy and Workers deploy — scope tokens to the minimum required permissions
- Omitting `--branch` flag — Wrangler defaults to `main`, silently promoting a PR build to production
- Deploying on every `push` to every branch without a path filter — unnecessary deploys for unrelated changes

## Gotchas
- `wrangler pages deploy` returns exit 0 even when the deployment is queued but not yet propagated; add a post-deploy smoke test
- Pages Functions inside `functions/` must be co-located with the output directory or specified with `--directory`; the flag is `--directory` not `--functions`
- The `--commit-hash` and `--commit-message` flags are cosmetic — they appear in the dashboard but do not affect routing or deployment logic
- Direct upload does not trigger Cloudflare's branch URL aliasing automatically for non-`main` branches unless the project has "Automatic branch deployments" enabled in the dashboard
- Concurrent deploys to the same branch from parallel CI jobs can cause one to overwrite the other; serialize deploy steps with a mutex or use merge queues

## Verification
```bash
# List recent Pages deployments
npx wrangler pages deployment list --project-name orchords-web

# Tail functions logs for the latest production deployment
npx wrangler pages deployment tail --project-name orchords-web

# Verify the correct commit is live
curl -s https://orchords-web.pages.dev/api/version | jq '.commitHash'
```

## Related
- `cloudflare-pages-preview-deployments.md`
- `cloudflare-pages-build-cache-optimization.md`
- `pages-functions-env-var-management.md`
- `monorepo-deploy-pipeline-turborepo.md`

## Sources
- https://developers.cloudflare.com/pages/functions/
- https://developers.cloudflare.com/workers/wrangler/commands/#pages-deploy
- https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
