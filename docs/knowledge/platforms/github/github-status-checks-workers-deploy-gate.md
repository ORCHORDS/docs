# GitHub Status Checks – Workers as a Deploy Gate

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need a custom required status check that runs business logic GitHub Actions cannot
express: querying a Cloudflare D1 database for feature flag state, checking an external
SLA window, validating that a migration has been applied to preview before production,
or enforcing that the PR author has acknowledged a security checklist. The check must
block merges until the condition is satisfied and be clearable by a human action (a
comment command, a dashboard button) rather than another CI re-run. A Cloudflare Worker
handles the webhook, runs the validation, and posts the status check result back to
GitHub using a GitHub App installation token.

## Context

GitHub's Commit Status API (`POST /repos/:owner/:repo/statuses/:sha`) and Check Runs API
(`POST /repos/:owner/:repo/check-runs`) are the two surfaces for custom required checks.
Status checks are simpler but less expressive; Check Runs support annotations, images,
and re-request webhooks. This article uses Check Runs because they support
`rerequested` webhooks — when a reviewer clicks "Re-run" in the GitHub UI, GitHub sends
a new webhook to the Worker, allowing the gate to re-evaluate without a new commit. The
Worker authenticates as a GitHub App using an installation token cached in KV.

## 1. GitHub App Permissions Required

The GitHub App must have:

| Permission      | Level          | Purpose                            |
|-----------------|----------------|------------------------------------|
| Checks          | Write          | Create and update check runs       |
| Contents        | Read           | Read PR head commit details        |
| Pull requests   | Read           | Read PR metadata for gate logic    |
| Metadata        | Read (required)| Default for all Apps               |

Subscribed events: `check_suite`, `pull_request`.

## 2. Wrangler Configuration

```toml
# wrangler.toml
name = "github-deploy-gate"
compatibility_date = "2026-06-01"
compatibility_flags = ["nodejs_compat"]

[[kv_namespaces]]
binding = "GH_TOKEN_CACHE"
id = "your-kv-namespace-id"

[[d1_databases]]
binding = "GATE_DB"
database_name = "deploy-gate"
database_id = "your-d1-database-id"

[vars]
GH_APP_ID = "123456"
GH_INSTALLATION_ID = "78901234"
CHECK_NAME = "deploy-gate/readiness"
```

## 3. Webhook Receiver and Signature Verification

```typescript
// src/index.ts
import type { Env } from "./types.ts";
import { verifyWebhookSignature } from "./webhook-verify.ts";
import { handleCheckSuite } from "./handlers/check-suite.ts";
import { handlePullRequest } from "./handlers/pull-request.ts";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.text();
    const signature = request.headers.get("X-Hub-Signature-256") ?? "";
    const event = request.headers.get("X-GitHub-Event") ?? "";

    const valid = await verifyWebhookSignature(body, signature, env.GH_WEBHOOK_SECRET);
    if (!valid) {
      return new Response("Invalid signature", { status: 401 });
    }

    const payload = JSON.parse(body);

    // Respond immediately to satisfy GitHub's 10-second webhook timeout,
    // then process asynchronously using waitUntil
    const ctx = (request as Request & { ctx: ExecutionContext }).ctx;

    switch (event) {
      case "check_suite":
        ctx.waitUntil(handleCheckSuite(payload, env));
        break;
      case "pull_request":
        if (["opened", "synchronize", "reopened"].includes(payload.action)) {
          ctx.waitUntil(handlePullRequest(payload, env));
        }
        break;
    }

    return new Response("Accepted", { status: 202 });
  },
};
```

```typescript
// src/webhook-verify.ts
export async function verifyWebhookSignature(
  body: string,
  signature: string,
  secret: string
): Promise<boolean> {
  if (!signature.startsWith("sha256=")) return false;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const expected = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(body)
  );
  const expectedHex =
    "sha256=" +
    Array.from(new Uint8Array(expected))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

  // Constant-time comparison
  if (expectedHex.length !== signature.length) return false;
  let mismatch = 0;
  for (let i = 0; i < expectedHex.length; i++) {
    mismatch |= expectedHex.charCodeAt(i) ^ signature.charCodeAt(i);
  }
  return mismatch === 0;
}
```

## 4. Gate Logic Against D1

```typescript
// src/gate-logic.ts
import type { Env } from "./types.ts";

interface GateResult {
  passed: boolean;
  summary: string;
  details: string;
}

interface FeatureFlag {
  name: string;
  deploy_allowed: number;
  reason: string;
}

interface MigrationState {
  sha: string;
  applied_at: number;
  environment: string;
}

export async function evaluateDeployGate(
  params: {
    owner: string;
    repo: string;
    sha: string;
    prNumber?: number;
  },
  env: Env
): Promise<GateResult> {
  // Check 1: Is deployment allowed by feature flag?
  const flag = await env.GATE_DB.prepare(
    "SELECT deploy_allowed, reason FROM feature_flags WHERE name = 'global_deploy_gate' LIMIT 1"
  ).first<FeatureFlag>();

  if (flag && !flag.deploy_allowed) {
    return {
      passed: false,
      summary: "Deployments paused",
      details: `Global deploy gate is closed: ${flag.reason}. Contact #platform-infra to re-enable.`,
    };
  }

  // Check 2: Has the preview migration been applied for this SHA?
  if (params.prNumber) {
    const migrationApplied = await env.GATE_DB.prepare(
      `SELECT sha, applied_at FROM migration_states
       WHERE sha = ?1 AND environment = 'preview'
       LIMIT 1`
    )
      .bind(params.sha)
      .first<MigrationState>();

    if (!migrationApplied) {
      return {
        passed: false,
        summary: "Preview migration not applied",
        details: `SHA ${params.sha.slice(0, 7)} has pending schema migrations. Run \`/apply-preview-migration\` in the PR to proceed.`,
      };
    }
  }

  return {
    passed: true,
    summary: "All gate checks passed",
    details: `Deploy allowed for ${params.sha.slice(0, 7)}.`,
  };
}
```

## 5. Posting the Check Run Result

```typescript
// src/handlers/check-suite.ts
import type { Env } from "../types.ts";
import { getInstallationToken } from "../github-token.ts";
import { evaluateDeployGate } from "../gate-logic.ts";

const GITHUB_API = "https://api.github.com";

export async function handleCheckSuite(payload: Record<string, unknown>, env: Env) {
  const suite = payload.check_suite as {
    head_sha: string;
    pull_requests: Array<{ number: number }>;
  };
  const repo = payload.repository as { full_name: string; name: string };
  const [owner, repoName] = repo.full_name.split("/");
  const sha = suite.head_sha;
  const prNumber = suite.pull_requests[0]?.number;

  // Create a check run in "in_progress" state immediately
  const token = await getInstallationToken(env);
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
    "User-Agent": `deploy-gate-app/${env.GH_APP_ID}`,
  };

  const createRes = await fetch(
    `${GITHUB_API}/repos/${owner}/${repoName}/check-runs`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({
        name: env.CHECK_NAME,
        head_sha: sha,
        status: "in_progress",
        started_at: new Date().toISOString(),
      }),
    }
  );

  if (!createRes.ok) return;
  const { id: checkRunId } = (await createRes.json()) as { id: number };

  // Evaluate the gate
  const result = await evaluateDeployGate({ owner, repo: repoName, sha, prNumber }, env);

  // Update the check run with the final result
  await fetch(`${GITHUB_API}/repos/${owner}/${repoName}/check-runs/${checkRunId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({
      status: "completed",
      conclusion: result.passed ? "success" : "action_required",
      completed_at: new Date().toISOString(),
      output: {
        title: result.summary,
        summary: result.details,
      },
    }),
  });
}
```

## 6. Branch Protection Configuration

```typescript
// Set via GitHub API or Terraform — require the check run by name
// The name must exactly match env.CHECK_NAME = "deploy-gate/readiness"

// Example using Octokit (for setup scripts, not the Worker itself):
await octokit.rest.repos.updateBranchProtection({
  owner,
  repo,
  branch: "main",
  required_status_checks: {
    strict: true,
    contexts: [], // legacy; use checks instead
    checks: [{ context: "deploy-gate/readiness", app_id: YOUR_APP_ID }],
  },
  enforce_admins: true,
  required_pull_request_reviews: null,
  restrictions: null,
});
```

## Anti-patterns

- **Processing webhook payloads synchronously inside the 10-second timeout window.**
  D1 queries and GitHub API calls can each take 1–3 seconds. Use `waitUntil` to
  move all logic off the critical path; return 202 immediately.
- **Using the `pending` conclusion.** GitHub Check Runs have no `pending` conclusion.
  Use `action_required` to block the merge without implying an error state.
- **Hardcoding the check name as a string literal across multiple files.** A mismatch
  between the name posted to the API and the name configured in branch protection rules
  means the check never counts as required. Store it in a single config constant or
  `wrangler.toml` var.
- **Not verifying the webhook signature before running gate logic.** An unsigned request
  could trigger false gate approvals by sending crafted payloads.

## Gotchas

- `action_required` conclusions do not automatically block merges — you must configure
  the check run name as a required status check in branch protection rules or rulesets.
- Check runs created by a GitHub App are associated with the App's `app_id`. The branch
  protection rule must reference the correct `app_id`, not just the check name, to
  prevent spoofing by a workflow with the same step name.
- The `check_suite.rerequested` action fires when a user clicks "Re-run" in the GitHub
  UI. Your handler must create a new check run (not update the old one) to show fresh
  results — the old check run ID belongs to the completed suite.
- Workers have a 30-second CPU time limit on the paid plan; D1 query timeout defaults
  to 30 seconds as well. For slow gate checks, use a Durable Object with an alarm
  rather than blocking the fetch handler.

## Verification

```bash
# List check runs for a specific commit SHA
gh api repos/owner/repo/commits/<sha>/check-runs \
  --jq '.check_runs[] | {name, status, conclusion}'

# Trigger a re-evaluation by posting a check_suite rerequested event
gh api repos/owner/repo/check-suites/<suite-id>/rerequest --method POST

# Inspect the Worker's log for gate evaluation results
wrangler tail --name github-deploy-gate --format pretty
```

## Related

- `github-apps-installation-token-workers-api-client.md`
- `github-actions-required-status-checks-branch-gates.md`
- `github-required-status-checks.md`
- `github-custom-deployment-protection-rules.md`
- `github-actions-deployment-gates.md`
- `github-app-webhook-workers-handler.md`

## Sources

- GitHub Docs – Check Runs API: https://docs.github.com/en/rest/checks/runs
- GitHub Docs – Required status checks: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging
- Cloudflare Workers – waitUntil: https://developers.cloudflare.com/workers/runtime-apis/handlers/fetch/#contextwaituntil
- Cloudflare D1 – Query API: https://developers.cloudflare.com/d1/worker-api/
