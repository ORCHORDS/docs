# Updating GitHub Commit Statuses from Workers Deploy Pipelines

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
When a Cloudflare Workers deployment is triggered outside of GitHub Actions (e.g., from a Durable Object scheduler, a Webhook, or a custom deploy API), GitHub has no visibility into the deployment result and commit status checks remain absent or stale.
This article shows how to call the GitHub Commit Status API and Deployments API from within a Workers deploy pipeline to keep GitHub in sync.

## Context
The GitHub Statuses API (`POST /repos/{owner}/{repo}/statuses/{sha}`) lets any authenticated client mark a commit as `pending`, `success`, `failure`, or `error` with a description and a target URL.
Cloudflare Workers can call this API over `fetch()` using a fine-grained PAT or a GitHub App installation token stored in Wrangler Secrets.
Pairing commit statuses with the GitHub Deployments API creates a full audit trail of what was deployed where and when — visible in the PR Checks tab and the repository Deployments sidebar.

---

## Commit Status Helper

```typescript
// src/lib/github-status.ts

type CommitState = 'error' | 'failure' | 'pending' | 'success';

interface CommitStatusPayload {
  state: CommitState;
  target_url?: string;
  description?: string;
  context: string; // unique string per check type, e.g. "cf/workers-deploy"
}

export async function setCommitStatus(
  owner: string,
  repo: string,
  sha: string,
  payload: CommitStatusPayload,
  token: string,
): Promise<void> {
  const url = `https://api.github.com/repos/${owner}/${repo}/statuses/${sha}`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'cf-workers-deploy-pipeline/1.0',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`GitHub status API ${res.status}: ${detail}`);
  }
}
```

---

## Deployments API: Create and Update a Deployment

The Deployments API provides richer tracking than commit statuses alone, including environment history and auto-inactive management:

```typescript
// src/lib/github-deployment.ts

interface CreateDeploymentOptions {
  ref: string;           // branch, tag, or SHA
  environment: string;   // 'production', 'staging', 'preview-pr-42'
  description?: string;
  auto_merge?: boolean;  // default true; set false for CI-driven deploys
  required_contexts?: string[]; // [] = skip all status checks
}

export async function createGitHubDeployment(
  owner: string,
  repo: string,
  opts: CreateDeploymentOptions,
  token: string,
): Promise<number> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/deployments`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'cf-workers-deploy-pipeline/1.0',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ...opts,
        auto_merge: opts.auto_merge ?? false,
        required_contexts: opts.required_contexts ?? [],
      }),
    },
  );

  if (!res.ok) throw new Error(`Create deployment failed: ${await res.text()}`);
  const { id } = (await res.json() as { id: number });
  return id;
}

type DeploymentStatusState =
  | 'error' | 'failure' | 'inactive' | 'in_progress'
  | 'queued' | 'pending' | 'success';

export async function updateDeploymentStatus(
  owner: string,
  repo: string,
  deploymentId: number,
  state: DeploymentStatusState,
  environmentUrl?: string,
  token?: string,
): Promise<void> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/deployments/${deploymentId}/statuses`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'cf-workers-deploy-pipeline/1.0',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        state,
        environment_url: environmentUrl,
        log_url: `https://dash.cloudflare.com/?to=/:account/workers/overview`,
      }),
    },
  );

  if (!res.ok) throw new Error(`Update deployment status failed: ${await res.text()}`);
}
```

---

## Wiring into a Deploy Pipeline Worker

```typescript
// src/deploy-pipeline.ts
import { setCommitStatus } from './lib/github-status';
import { createGitHubDeployment, updateDeploymentStatus } from './lib/github-deployment';
import { Env } from './types';

export async function runDeploy(
  sha: string,
  branch: string,
  environment: string,
  env: Env,
): Promise<void> {
  const { GITHUB_OWNER: owner, GITHUB_REPO: repo } = env;
  const token = env.GITHUB_TOKEN;
  const context = `cf/workers-deploy/${environment}`;

  // 1. Mark as pending before deploy starts
  await setCommitStatus(owner, repo, sha, {
    state: 'pending',
    context,
    description: `Deploying to ${environment}…`,
  }, token);

  const deploymentId = await createGitHubDeployment(owner, repo, {
    ref: sha,
    environment,
    description: `Workers deploy from pipeline — ${new Date().toISOString()}`,
  }, token);

  await updateDeploymentStatus(owner, repo, deploymentId, 'in_progress', undefined, token);

  try {
    // --- actual wrangler deploy logic here ---
    const workerUrl = await deployWorker(sha, environment, env);

    // 2. Mark success
    await setCommitStatus(owner, repo, sha, {
      state: 'success',
      context,
      description: `Deployed to ${environment}`,
      target_url: workerUrl,
    }, token);

    await updateDeploymentStatus(owner, repo, deploymentId, 'success', workerUrl, token);
  } catch (err) {
    // 3. Mark failure
    await setCommitStatus(owner, repo, sha, {
      state: 'failure',
      context,
      description: `Deploy failed: ${(err as Error).message.slice(0, 120)}`,
    }, token);

    await updateDeploymentStatus(owner, repo, deploymentId, 'failure', undefined, token);
    throw err;
  }
}

async function deployWorker(
  sha: string,
  environment: string,
  env: Env,
): Promise<string> {
  // Stub: replace with Cloudflare deploy API call or DO trigger
  return `https://my-worker-${environment}.example.workers.dev`;
}
```

---

## Anti-patterns
- Using a classic PAT with `repo` scope — use a fine-grained PAT scoped to `commit_statuses:write` and `deployments:write` on the specific repository.
- Posting a `success` status before verifying the deployment is reachable — smoke test the deployed URL before updating the status.
- Posting duplicate statuses for the same `context` string — GitHub keeps all history but only the latest counts for branch protection; use consistent context names.
- Swallowing deploy errors and still posting `success` — any uncaught exception must be caught and reflected as `failure` or `error`.
- Not setting `auto_merge: false` when creating a GitHub Deployment — this can trigger GitHub to auto-merge branches unexpectedly if all required status checks pass.

## Gotchas
- GitHub retains a maximum of 1000 statuses per `(sha, context)` pair; after that, old entries are pruned but the latest always remains.
- The `deployment_status` webhook event fires for every `updateDeploymentStatus` call — downstream integrations (Slack, PagerDuty) must handle `in_progress` gracefully.
- `required_contexts: []` bypasses all required status checks when creating a deployment; specify the exact contexts if you want protection to apply.
- A SHA must belong to the repository (not a forked repo); always use `context.sha` from the merge commit, not the head SHA of a fork.
- GitHub caps `description` at 140 characters — truncate error messages before setting the status.

## Verification
```bash
# List commit statuses for a SHA
gh api /repos/OWNER/REPO/commits/SHA/statuses \
  | jq '.[] | {context, state, description, updated_at}'

# List deployments and latest status
gh api /repos/OWNER/REPO/deployments \
  | jq '.[:3][] | {id, environment, ref}'

gh api /repos/OWNER/REPO/deployments/DEPLOY_ID/statuses \
  | jq '.[0] | {state, environment_url, updated_at}'
```

## Related
- `github-deployment-api-workers-status-tracking.md`
- `github-status-checks-workers-deploy-gate.md`
- `github-actions-retry-failed-workers-deploy.md`
- `github-required-status-checks.md`

## Sources
- https://docs.github.com/en/rest/commits/statuses
- https://docs.github.com/en/rest/deployments/deployments
- https://docs.github.com/en/rest/deployments/statuses
- https://developers.cloudflare.com/workers/configuration/secrets/
