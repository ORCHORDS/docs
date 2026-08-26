# Trunk-Based Development with Cloudflare Workers

**Author:** example.com
**Project:** example project (example.com) — pnpm monorepo, Cloudflare Workers + Pages
**Last updated:** 2026-08-22

---

## Overview

Trunk-based development (TBD) is a source-control branching model where all engineers integrate their work into a single shared branch — `main` — at least once a day. Short-lived feature branches (< 2 days) are the only allowed deviation, and they are merged back to `main` via pull request before they diverge. For a Cloudflare Workers monorepo, TBD pairs naturally with Wrangler's deploy pipeline: every merge to `main` triggers an automatic deploy, making the trunk the single source of truth for what is running in production.

This article covers how to implement trunk-based development for example project, including feature flag patterns that let incomplete features live in `main` without affecting end users, Wrangler deploy-on-merge automation, and mobile feature gates that coordinate between the Cloudflare Workers API and the mobile client.

---

## Why Trunk-Based Development for Cloudflare Workers

Cloudflare Workers deploy in seconds globally. This makes the traditional "long-lived feature branch → staging → production" pipeline unnecessary overhead. With TBD:

- **Integration problems surface immediately** — a branch that lives two hours instead of two weeks has near-zero merge conflict risk.
- **Deploy frequency becomes a non-event** — teams deploy tens of times per day without fear, because each change is small and reviewable.
- **Preview environments are disposable** — `wrangler deploy --env preview` gives every PR its own Workers URL. There is no long-lived "staging" environment to protect.
- **Rollback is a re-deploy** — because changes are small, reverting a bad merge is a new commit + deploy cycle, not an emergency branch surgery.

---

## Repository Branch Policy

```
main (protected, deploy-on-push)
  └── feat/add-payment-webhook  (< 2 days, 1 author)
  └── fix/rate-limit-header     (< 1 day, 1 author)
```

### Branch protection rules (GitHub)

```yaml
# .github/branch-protection.yml (via Terraform or UI)
branch: main
required_status_checks:
  strict: true
  contexts:
    - "ci / typecheck"
    - "ci / lint"
    - "ci / test"
require_pull_request_reviews:
  required_approving_review_count: 1
  dismiss_stale_reviews: true
enforce_admins: false          # admins can break glass in incidents
allow_force_pushes: false
allow_deletions: false
```

The key constraint: **no branch lives longer than two working days**. If a feature needs more time, it ships behind a feature flag in the off state.

---

## Feature Flags for Incomplete Work

Feature flags are the mechanism that makes TBD safe. Code for an unfinished feature merges to `main` on day one, gated by a flag that defaults to `false`. The feature is invisible in production until the team deliberately enables it.

### Flag storage in Cloudflare Workers KV

```typescript
// packages/workers/src/lib/flags.ts
export type FeatureFlag =
  | "payment_v2_enabled"
  | "ai_suggestions_enabled"
  | "mobile_offline_sync";

export async function isEnabled(
  flag: FeatureFlag,
  env: Env,
  userId?: string
): Promise<boolean> {
  // KV key pattern: "flag:<name>" → "true" | "false"
  // KV key pattern: "flag:<name>:user:<id>" → override for canary user
  if (userId) {
    const userOverride = await env.FLAGS_KV.get(`flag:${flag}:user:${userId}`);
    if (userOverride !== null) return userOverride === "true";
  }
  const global = await env.FLAGS_KV.get(`flag:${flag}`);
  return global === "true";
}
```

```typescript
// packages/workers/src/routes/payment.ts
export async function handlePayment(request: Request, env: Env): Promise<Response> {
  const userId = getUserId(request);
  if (await isEnabled("payment_v2_enabled", env, userId)) {
    return handlePaymentV2(request, env);
  }
  return handlePaymentV1(request, env);
}
```

### Setting flags without a deploy

Use the Cloudflare dashboard, Wrangler CLI, or a thin admin Worker to flip flags:

```bash
# Enable for all users (no code deploy needed)
wrangler kv:key put --binding=FLAGS_KV "flag:payment_v2_enabled" "true" --env production

# Enable only for a canary user
wrangler kv:key put --binding=FLAGS_KV "flag:payment_v2_enabled:user:usr_abc123" "true" --env production
```

This decouples **deployment** (shipping code) from **release** (turning the feature on).

---

## Wrangler Deploy-on-Merge GitHub Action

Every merge to `main` automatically deploys all affected Workers. Turborepo's `--filter` ensures only changed packages are deployed.

```yaml
# .github/workflows/deploy.yml
name: Deploy to Cloudflare Workers

on:
  push:
    branches: [main]

concurrency:
  group: deploy-production
  cancel-in-progress: false   # never cancel an in-flight production deploy

jobs:
  deploy:
    name: Deploy Workers
    runs-on: ubuntu-latest
    permissions:
      contents: read
      deployments: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2        # need HEAD and HEAD~1 for Turborepo diff

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build affected packages
        run: pnpm turbo run build --filter="...[HEAD~1]"

      - name: Deploy API Worker
        if: ${{ steps.changed.outputs.api == 'true' }}
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          workingDirectory: packages/api-worker
          command: deploy --env production

      - name: Deploy Web Pages
        if: ${{ steps.changed.outputs.web == 'true' }}
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          workingDirectory: packages/web
          command: pages deploy dist --project-name=example project-web

      - name: Tag deployment
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.repos.createDeployment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              ref: context.sha,
              environment: 'production',
              auto_merge: false,
              required_contexts: [],
              description: `Deploy ${context.sha.slice(0, 7)} to Cloudflare Workers`,
            });
```

### Preview deploy on PRs

```yaml
# .github/workflows/preview.yml
name: Preview Deploy

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo run build
      - name: Deploy preview Worker
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          workingDirectory: packages/api-worker
          command: deploy --env preview
          # Wrangler names the preview: example project-api-pr-<number>
```

---

## Mobile Feature Gate Pattern

Mobile apps (iOS/Android) cannot be force-updated, so feature flags must account for the app version making the request. The Workers API inspects the `X-App-Version` header and gates features per version.

```typescript
// packages/workers/src/lib/mobile-flags.ts
import { isEnabled } from "./flags";
import { semverGte } from "./semver";

export interface MobileContext {
  platform: "ios" | "android";
  appVersion: string;         // e.g. "2.4.1"
  userId?: string;
}

export async function isMobileFeatureEnabled(
  flag: FeatureFlag,
  ctx: MobileContext,
  env: Env,
  minVersion?: string         // minimum app version required
): Promise<boolean> {
  // Check global / user flag first
  const flagOn = await isEnabled(flag, env, ctx.userId);
  if (!flagOn) return false;

  // Enforce minimum app version gate
  if (minVersion && !semverGte(ctx.appVersion, minVersion)) {
    return false;
  }

  return true;
}
```

```typescript
// packages/workers/src/routes/sync.ts
export async function handleSync(request: Request, env: Env): Promise<Response> {
  const platform = (request.headers.get("X-App-Platform") ?? "ios") as "ios" | "android";
  const appVersion = request.headers.get("X-App-Version") ?? "0.0.0";

  const offlineSyncEnabled = await isMobileFeatureEnabled(
    "mobile_offline_sync",
    { platform, appVersion, userId: getUserId(request) },
    env,
    "2.5.0"   // requires app >= 2.5.0
  );

  if (offlineSyncEnabled) {
    return handleOfflineSync(request, env);
  }
  return handleOnlineSync(request, env);
}
```

The mobile client reads a `/v1/features` endpoint at startup and caches the flag map locally. This prevents per-request latency from KV lookups on the mobile side:

```typescript
// packages/workers/src/routes/features.ts
export async function handleFeatures(request: Request, env: Env): Promise<Response> {
  const ctx = getMobileContext(request);
  const flags: Record<string, boolean> = {
    offline_sync: await isMobileFeatureEnabled("mobile_offline_sync", ctx, env, "2.5.0"),
    ai_suggestions: await isMobileFeatureEnabled("ai_suggestions_enabled", ctx, env, "2.3.0"),
  };
  return Response.json(flags, {
    headers: { "Cache-Control": "max-age=60, stale-while-revalidate=300" },
  });
}
```

---

## Short-Lived Branch Discipline

| Rule | Enforcement |
|------|-------------|
| Branch age ≤ 2 days | Stale branch GitHub Action closes PR with label `stale-branch` after 48 hours |
| One author per branch | Documented convention; pair programming uses one committer |
| Branch from `main` only | Branch protection blocks branches off other feature branches |
| Delete on merge | Repository setting: auto-delete head branch enabled |

### Stale branch sweeper

```yaml
# .github/workflows/stale-branches.yml
name: Stale Branch Check

on:
  schedule:
    - cron: "0 9 * * 1-5"   # weekdays at 09:00 UTC

jobs:
  stale:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const branches = await github.rest.repos.listBranches({
              owner: context.repo.owner,
              repo: context.repo.repo,
              protected: false,
              per_page: 100,
            });
            const cutoff = Date.now() - 2 * 24 * 60 * 60 * 1000;
            for (const branch of branches.data) {
              const { data: commit } = await github.rest.repos.getCommit({
                owner: context.repo.owner,
                repo: context.repo.repo,
                ref: branch.commit.sha,
              });
              const age = new Date(commit.commit.committer.date).getTime();
              if (age < cutoff) {
                core.warning(`Stale branch: ${branch.name}`);
              }
            }
```

---

## Summary

- `main` is always deployable and always deployed on merge via Wrangler.
- Feature flags in Cloudflare KV decouple deployment from release.
- Mobile gates combine flag state with minimum app version, served from a `/v1/features` endpoint cached by clients.
- Short-lived branches (≤ 2 days) with automated stale checks keep the trunk clean.
- PR preview Workers give reviewers a live URL without any shared staging environment.

**References**
- Trunk Based Development: https://trunkbaseddevelopment.com
- Cloudflare Workers KV API: https://developers.cloudflare.com/kv
- `cloudflare/wrangler-action`: https://github.com/cloudflare/wrangler-action
