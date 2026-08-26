# Cloudflare Pages Preview URL Injection into GitHub PR Status

- **Date:** 2026-08-24
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A pull request is opened. Cloudflare Pages builds a preview deployment automatically, but the preview URL appears only inside the Cloudflare dashboard. Reviewers must leave GitHub, navigate to the dashboard, and manually find the correct preview URL. This context-switch delays code review and introduces broken-link risk when preview URLs are pasted manually into PR comments.

---

## Context

Cloudflare Pages fires a `pages:deployment` webhook after every successful build, including preview deployments triggered by pull requests. GitHub exposes two integration points for surfacing deployment URLs: **Commit Statuses** (shown inline on each commit SHA) and **Deployments + Deployment Statuses** (shown in the PR's "Deployments" sidebar and environment list). By wiring a Cloudflare Worker to the Pages webhook and forwarding the preview URL to the GitHub API, every PR gets its preview link injected automatically within seconds of the Pages build completing — no third-party apps required.

---

## 1. Pages Webhook Configuration

```typescript
// wrangler.toml (webhook receiver Worker)
name = "pages-pr-status-injector"
main = "src/index.ts"
compatibility_date = "2026-07-01"

[vars]
GITHUB_OWNER = "your-org"
GITHUB_REPO = "your-repo"

# Secrets (set via wrangler secret put):
# PAGES_WEBHOOK_SECRET   — shared secret configured in Pages dashboard
# GITHUB_APP_TOKEN       — GitHub App installation token or PAT with repo:status scope
```

---

## 2. Pages Webhook Payload Types

```typescript
// src/types.ts
export interface PagesDeploymentWebhook {
  id: string;
  url: string;                    // https://<hash>.your-project.pages.dev
  environment: "preview" | "production";
  deployment_trigger: {
    type: "github" | "api" | "adhoc";
    metadata: {
      branch: string;
      commit_hash: string;        // Full 40-char SHA
      commit_message: string;
      author: string;
    };
  };
  build_config: {
    build_command: string;
    destination_dir: string;
  };
  stages: Array<{
    name: string;
    status: "success" | "failure" | "skipped" | "active" | "idle";
    ended_on: string | null;
  }>;
  created_on: string;
  modified_on: string;
}
```

---

## 3. Webhook Receiver Worker

```typescript
// src/index.ts
import type { PagesDeploymentWebhook } from "./types";

export interface Env {
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
  PAGES_WEBHOOK_SECRET: string;
  GITHUB_APP_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Verify Cloudflare Pages webhook signature
    const signature = request.headers.get("X-Hub-Signature-256") ?? "";
    const body = await request.text();
    const valid = await verifySignature(body, signature, env.PAGES_WEBHOOK_SECRET);
    if (!valid) {
      return new Response("Unauthorized", { status: 401 });
    }

    const payload: PagesDeploymentWebhook = JSON.parse(body);

    // Only act on GitHub-triggered preview deployments
    if (
      payload.environment !== "preview" ||
      payload.deployment_trigger.type !== "github"
    ) {
      return new Response("Skipped: not a GitHub-triggered preview", { status: 200 });
    }

    const { commit_hash, branch } = payload.deployment_trigger.metadata;
    const previewUrl = payload.url;

    // Determine build success from stages
    const deployStage = payload.stages.find((s) => s.name === "deploy");
    const githubState =
      deployStage?.status === "success" ? "success" : "failure";

    await Promise.all([
      postCommitStatus(env, commit_hash, previewUrl, githubState, branch),
      createGitHubDeployment(env, commit_hash, previewUrl, githubState, branch),
    ]);

    return new Response("OK", { status: 200 });
  },
} satisfies ExportedHandler<Env>;

async function verifySignature(
  body: string,
  signature: string,
  secret: string
): Promise<boolean> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
  const expected =
    "sha256=" +
    Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  return timingSafeEqual(signature, expected);
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}
```

---

## 4. GitHub Commit Status and Deployment APIs

```typescript
// src/github.ts
const GITHUB_API = "https://api.github.com";

export async function postCommitStatus(
  env: { GITHUB_OWNER: string; GITHUB_REPO: string; GITHUB_APP_TOKEN: string },
  sha: string,
  targetUrl: string,
  state: "success" | "failure" | "pending" | "error",
  branch: string
): Promise<void> {
  const res = await fetch(
    `${GITHUB_API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/statuses/${sha}`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_APP_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "pages-pr-injector/1.0",
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        state,
        target_url: targetUrl,
        description:
          state === "success"
            ? `Preview ready on branch: ${branch}`
            : "Cloudflare Pages build failed",
        context: "cloudflare-pages/preview",
      }),
    }
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`GitHub status API failed ${res.status}: ${text}`);
  }
}

export async function createGitHubDeployment(
  env: { GITHUB_OWNER: string; GITHUB_REPO: string; GITHUB_APP_TOKEN: string },
  sha: string,
  targetUrl: string,
  state: "success" | "failure",
  branch: string
): Promise<void> {
  // Create the deployment record
  const deployRes = await fetch(
    `${GITHUB_API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/deployments`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_APP_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "pages-pr-injector/1.0",
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        ref: sha,
        environment: `preview-${branch}`,
        auto_merge: false,
        required_contexts: [],
        description: "Cloudflare Pages preview deployment",
        transient_environment: true,
        production_environment: false,
      }),
    }
  );

  if (!deployRes.ok) {
    console.error(`Deployment create: ${deployRes.status}`);
    return;
  }

  const { id: deploymentId } = (await deployRes.json()) as { id: number };

  // Post the deployment status with the Pages URL
  await fetch(
    `${GITHUB_API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/deployments/${deploymentId}/statuses`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_APP_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "pages-pr-injector/1.0",
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        state,
        environment_url: targetUrl,
        log_url: targetUrl,
        description: "Cloudflare Pages preview",
        auto_inactive: true,
      }),
    }
  );
}
```

---

## 5. Cloudflare Pages Webhook Registration

```bash
# Register the webhook in Cloudflare Pages via API (one-time setup)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/${PAGES_PROJECT}/webhooks" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://pages-pr-status-injector.<your-workers-subdomain>.workers.dev",
    "secret": "'"${PAGES_WEBHOOK_SECRET}"'"
  }'

# Verify webhook is registered
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/${PAGES_PROJECT}/webhooks" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[].url'
```

---

## 6. GitHub Actions Fallback (CI-Side Status Posting)

For teams that do not use the Pages webhook, a GitHub Actions step can post the status after Pages finishes:

```yaml
# .github/workflows/pages-preview-status.yml
name: Inject Pages Preview URL

on:
  deployment_status: {}     # GitHub fires this when any deployment status changes

jobs:
  inject-status:
    if: |
      github.event.deployment_status.state == 'success' &&
      github.event.deployment.environment != 'production'
    runs-on: ubuntu-latest
    steps:
      - name: Post Pages preview URL as commit status
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PREVIEW_URL: ${{ github.event.deployment_status.environment_url }}
          SHA: ${{ github.event.deployment.sha }}
        run: |
          gh api \
            --method POST \
            -H "Accept: application/vnd.github+json" \
            "/repos/${{ github.repository }}/statuses/${SHA}" \
            -f state=success \
            -f target_url="${PREVIEW_URL}" \
            -f description="Preview ready" \
            -f context="cloudflare-pages/preview"
```

---

## Anti-patterns

- **Posting the status from `push` CI** without waiting for Pages to finish — the URL does not exist yet, the status points to a 404.
- **Using a PAT with `repo` scope** instead of a fine-grained token with `statuses:write` — violates least-privilege; the status API only needs `statuses:write` and `deployments:write`.
- **Not verifying the webhook signature** — any public HTTP endpoint that blindly processes JSON can be abused to forge status updates on arbitrary commits.
- **Posting `pending` state and never updating it** — a permanently pending status blocks PR merge when required status checks are configured.

---

## Gotchas

- Cloudflare Pages preview URLs are per-deployment, not per-branch. If a branch has multiple commits pushed quickly, each push produces a different URL. Post the status for each commit SHA independently.
- GitHub's **required status checks** in branch protection only recognize the `context` string. Use a stable context like `cloudflare-pages/preview` — not the dynamic branch name — so the required check name never changes.
- The `transient_environment: true` flag on GitHub Deployments ensures the environment is marked inactive when the branch is deleted, keeping the Environments sidebar clean.
- The Pages webhook delivers events for both **preview** and **production** environments. The receiver must filter on `payload.environment === "preview"` to avoid posting PR statuses for production deploys.

---

## Verification

```bash
# 1. Check that the commit status was posted
gh api /repos/YOUR_ORG/YOUR_REPO/commits/SHA/statuses \
  | jq '.[] | select(.context == "cloudflare-pages/preview") | {state, target_url}'

# 2. Check that the GitHub Deployment was created
gh api /repos/YOUR_ORG/YOUR_REPO/deployments \
  | jq '.[] | select(.environment | startswith("preview-")) | {id, environment, url: .statuses_url}'

# 3. Tail the Worker to see webhook processing logs
wrangler tail pages-pr-status-injector --format=pretty

# 4. Manually replay the last webhook event from Cloudflare dashboard:
# Pages → Project → Settings → Webhooks → Redeliver
```

---

## Related

- `cloudflare-pages-preview-deployments.md` — Pages preview deployment configuration
- `pages-preview-deployment-cleanup-automation.md` — automated teardown of stale preview environments
- `deploy-notification-webhooks-slack-teams-workers.md` — posting deployment events to Slack/Teams
- `oidc-federated-deploy-credentials.md` — GitHub OIDC-based token for CI authentication

---

## Sources

- Cloudflare Docs — Pages Webhooks: https://developers.cloudflare.com/pages/platform/webhooks/
- GitHub Docs — Commit Statuses API: https://docs.github.com/en/rest/commits/statuses
- GitHub Docs — Deployments API: https://docs.github.com/en/rest/deployments/deployments
- GitHub Docs — Deployment Statuses API: https://docs.github.com/en/rest/deployments/statuses
