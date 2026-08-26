# Authoring a Custom JavaScript Action in TypeScript

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need behaviour that composite actions cannot express — spawning child processes, calling
third-party APIs at step runtime, or encapsulating logic that is too large to inline in
`actions/github-script`. Writing a proper JavaScript action lets you ship it as a versioned,
reusable step that runs directly on the runner (no Docker cold-start).

## Context

GitHub supports three action kinds: composite, Docker, and JavaScript. JavaScript actions
execute in the runner's Node.js process, have access to `@actions/core`, `@actions/github`,
and the full npm ecosystem, and must ship a pre-bundled `dist/` directory because the runner
never runs `npm install`. TypeScript source is compiled + bundled with `ncc` or `esbuild`
before being committed.

This guide covers: project layout, authoring, local testing, bundling, and consuming the
action from a workflow.

---

## Project Layout

```
my-action/
├── action.yml          # action metadata
├── src/
│   └── main.ts         # entry point
├── dist/
│   └── index.js        # bundled output (committed)
├── tsconfig.json
└── package.json
```

```jsonc
// package.json (key fields)
{
  "name": "my-action",
  "version": "1.0.0",
  "main": "dist/index.js",
  "scripts": {
    "build": "ncc build src/main.ts -o dist --source-map --license licenses.txt",
    "test":  "vitest run"
  },
  "dependencies": {
    "@actions/core":   "^1.10.1",
    "@actions/github": "^6.0.0"
  },
  "devDependencies": {
    "@vercel/ncc": "^0.38.2",
    "typescript":  "^5.5.0",
    "vitest":      "^2.0.0"
  }
}
```

---

## action.yml Metadata

```yaml
# action.yml
name: "Notify D1 Deploy"
description: "Records a deployment event in a Cloudflare D1 database via REST"
author: "example.com"

inputs:
  cloudflare-account-id:
    description: "Cloudflare account ID"
    required: true
  cloudflare-api-token:
    <redacted-secret> "API token with D1 write permission"
    required: true
  database-id:
    description: "D1 database ID"
    required: true
  environment:
    description: "Deployment environment name"
    required: false
    default: "production"

outputs:
  record-id:
    description: "Row ID of the inserted deployment record"

runs:
  using: "node20"
  main: "dist/index.js"
```

---

## TypeScript Implementation

```typescript
// src/main.ts
import * as core from "@actions/core";
import * as github from "@actions/github";

interface D1Result {
  success: boolean;
  results: Array<{ id: number }>;
}

async function insertDeployRecord(
  accountId: string,
  apiToken: string,
  databaseId: string,
  environment: string,
  sha: string,
  actor: string
): Promise<number> {
  const url =
    `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
    `/d1/database/${databaseId}/query`;

  const body = JSON.stringify({
    sql: `INSERT INTO deployments (sha, environment, actor, deployed_at)
          VALUES (?1, ?2, ?3, datetime('now'))
          RETURNING id`,
    params: [sha, environment, actor],
  });

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`D1 query failed ${res.status}: ${text}`);
  }

  const json = (await res.json()) as { result: D1Result[] };
  const firstResult = json.result?.[0];
  if (!firstResult?.success || !firstResult.results?.[0]?.id) {
    throw new Error("Unexpected D1 response shape");
  }
  return firstResult.results[0].id;
}

async function run(): Promise<void> {
  try {
    const accountId = core.getInput("cloudflare-account-id", { required: true });
    const apiToken  = <redacted-secret>"cloudflare-api-token",  { required: true });
    const dbId      = core.getInput("database-id",           { required: true });
    const env       = core.getInput("environment");

    const { sha, actor } = github.context;

    core.info(`Recording deployment of ${sha} to ${env} by ${actor}`);

    const recordId = await insertDeployRecord(
      accountId, apiToken, dbId, env, sha, actor
    );

    core.setOutput("record-id", String(recordId));
    core.info(`Inserted deployment record id=${recordId}`);
  } catch (err) {
    if (err instanceof Error) core.setFailed(err.message);
    else core.setFailed(String(err));
  }
}

run();
```

---

## Building and Committing the Bundle

```bash
npm run build
# Produces dist/index.js (~200 KB bundled, no node_modules needed at runtime)

git add dist/
git commit -m "chore: bundle action dist"
git push origin main
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0
```

Use a GitHub Actions workflow to auto-build on push to `main` so `dist/` stays in sync:

```yaml
# .github/workflows/build-action.yml
name: Build Action

on:
  push:
    branches: [main]
    paths: ["src/**", "package*.json", "tsconfig.json"]

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
      - run: npm ci
      - run: npm run build
      - name: Commit dist if changed
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add dist/
          git diff --cached --quiet || git commit -m "chore: rebuild dist [skip ci]"
          git push
```

---

## Consuming the Action

```yaml
# Workflow in another repo (or same repo)
- name: Record deployment in D1
  uses: example-org/example-repo@v1
  with:
    cloudflare-account-id: ${{ secrets.CF_ACCOUNT_ID }}
    cloudflare-api-token:  ${{ secrets.CF_D1_TOKEN }}
    database-id:           ${{ vars.DEPLOYS_DB_ID }}
    environment:           production

- name: Print record ID
  run: echo "Deployment recorded as row ${{ steps.record.outputs.record-id }}"
```

---

## Anti-patterns

- **Not committing `dist/`** — the runner clones the action repo and executes `dist/index.js`
  directly; it never runs `npm install`. Shipping only source silently fails with a
  "Cannot find module" error.
- **Using `runs.using: node16`** — Node 16 is deprecated on GitHub-hosted runners. Use
  `node20`.
- **Storing secrets in action inputs without `core.setSecret`** — any derived value that
  contains the secret must be masked explicitly:
  ```typescript
  core.setSecret(apiToken); // masks in logs even if logged accidentally
  ```
- **Catching all errors and calling `core.warning` instead of `core.setFailed`** — the job
  continues and appears green when it should fail.
- **Bundling with `tsc` alone** — TypeScript emits multiple `.js` files; ncc or esbuild
  produces a single file that includes all `node_modules`.

---

## Gotchas

- `github.context` is populated from `GITHUB_EVENT_PATH` at import time. Mutating it has no
  effect on subsequent steps.
- `core.getInput` always returns a string; cast numeric inputs explicitly.
- Node.js `fetch` is available natively from Node 18+. The `node20` runner supplies it;
  `node16` requires `node-fetch` as a dependency.
- Pinning the action with a SHA (`uses: example-org/example-repo@abc1234`) is safer in
  security-sensitive repos than a mutable tag.
- `dist/` must reflect the current source on every tag. A mismatch is the most common
  support issue with custom actions.

---

## Verification

```bash
# Run unit tests locally
npm test

# Smoke-test with act (local runner emulator)
act push -W .github/workflows/test-action.yml \
  --secret CF_ACCOUNT_ID=xxx \
  --secret CF_D1_TOKEN=xxx

# In CI, check the action step's output
echo "${{ steps.record-deploy.outputs.record-id }}"
```

Check the Actions run log for `##[set-output name=record-id;...]` lines to confirm output
was set before the step completed.

---

## Related

- `github-actions-github-script-octokit-inline.md` — lighter alternative for small inline scripts
- `github-actions-composite-actions.md` — shell/action composition without bundling
- `github-actions-oidc-cloudflare-deploy.md` — keyless Cloudflare auth alternative
- `github-actions-secrets-management.md` — managing tokens consumed by actions

---

## Sources

- https://docs.github.com/en/actions/creating-actions/creating-a-javascript-action
- https://github.com/actions/toolkit
- https://github.com/vercel/ncc
- https://docs.github.com/en/actions/creating-actions/metadata-syntax-for-github-actions
