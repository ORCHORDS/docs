# GitHub Deployment API — Workers Deploy Status Tracking

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Cloudflare Workers deployments succeed or fail silently from GitHub's perspective.
The **Environments** tab shows no history, Slack alerts carry no deployment context,
and rollback links are absent because nothing called the GitHub Deployments REST API
to register the deploy lifecycle.

Use this pattern when you want: live deployment status in the GitHub UI, deployment
history per environment, required-status-check gates that wait for a Workers deploy
to become `success`, and webhook-driven alerts on `deployment_status` events.

---

## Context

The GitHub Deployments API (`POST /repos/{owner}/{repo}/deployments`) creates a
*deployment record* that is independent of a workflow run. A subsequent call to
`POST /repos/{owner}/{repo}/deployments/{id}/statuses` updates its state
(`queued`, `in_progress`, `success`, `failure`, `error`, `inactive`).

Cloudflare Wrangler does not call this API automatically. You must wire it yourself,
either from the GitHub Actions workflow or from a Cloudflare Worker acting as a
deploy hook receiver.

Token requirement: `deployments:write` permission on the workflow token or a GitHub App
installation token.

---

## 1. Create a Deployment Record Before Wrangler Runs

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      deployments: write
      id-token: write
    outputs:
      deployment_id: ${{ steps.create_deploy.outputs.deployment_id }}
    steps:
      - name: Create GitHub deployment
        id: create_deploy
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          DEPLOY_ID=$(gh api \
            --method POST \
            /repos/${{ github.repository }}/deployments \
            -f ref="${{ github.sha }}" \
            -f environment="production" \
            -f description="Workers deploy via Actions" \
            -F auto_merge=false \
            -F required_contexts='[]' \
            --jq '.id')
          echo "deployment_id=$DEPLOY_ID" >> "$GITHUB_OUTPUT"

      - name: Mark deployment in_progress
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh api \
            --method POST \
            /repos/${{ github.repository }}/deployments/${{ steps.create_deploy.outputs.deployment_id }}/statuses \
            -f state="in_progress" \
            -f log_url="${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

---

## 2. Post Final Status After Wrangler Deploy

```yaml
      - name: Deploy to Cloudflare Workers
        id: wrangler
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          command: deploy --env production

      - name: Mark deployment success
        if: success()
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh api \
            --method POST \
            /repos/${{ github.repository }}/deployments/${{ steps.create_deploy.outputs.deployment_id }}/statuses \
            -f state="success" \
            -f environment_url="https://my-worker.example.com" \
            -f description="Deployed $(echo '${{ steps.wrangler.outputs.deployment-url }}' | head -c 120)"

      - name: Mark deployment failure
        if: failure()
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh api \
            --method POST \
            /repos/${{ github.repository }}/deployments/${{ steps.create_deploy.outputs.deployment_id }}/statuses \
            -f state="failure" \
            -f log_url="${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

---

## 3. Workers Webhook Handler for `deployment` Events

A Workers route can receive `deployment` webhooks and coordinate external systems
(e.g., warm caches, run smoke tests) before posting the final status.

```typescript
// src/deploy-hook.ts
import { Octokit } from "@octokit/rest";

export interface Env {
  GITHUB_WEBHOOK_SECRET: string;
  GITHUB_APP_TOKEN: string;
}

async function verifySignature(req: Request, secret: string): Promise<boolean> {
  const sig = req.headers.get("x-hub-signature-256") ?? "";
  const body = await req.text();
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const expected = "sha256=" + Array.from(new Uint8Array(mac))
    .map(b => b.toString(16).padStart(2, "0")).join("");
  return sig === expected;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (!(await verifySignature(req.clone(), env.GITHUB_WEBHOOK_SECRET))) {
      return new Response("Forbidden", { status: 403 });
    }

    const event = req.headers.get("x-github-event");
    if (event !== "deployment") return new Response("ignored", { status: 200 });

    const payload = await req.json<{ deployment: { id: number }; repository: { full_name: string } }>();
    const octokit = new Octokit({ auth: env.GITHUB_APP_TOKEN });
    const [owner, repo] = payload.repository.full_name.split("/");

    // Run smoke test or readiness probe here
    await octokit.repos.createDeploymentStatus({
      owner, repo,
      deployment_id: payload.deployment.id,
      state: "success",
      environment_url: "https://my-worker.example.com",
      description: "Smoke tests passed",
    });

    return new Response("ok");
  },
};
```

---

## 4. Deactivate Old Deployments on New Deploy

GitHub keeps all deployment statuses visible unless you explicitly mark prior
deployments `inactive`. Automate this with a pre-deploy step:

```typescript
// scripts/deactivate-old-deployments.ts
import { Octokit } from "@octokit/rest";

const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });
const [owner, repo] = (process.env.GITHUB_REPOSITORY ?? "").split("/");
const environment = process.env.DEPLOY_ENV ?? "production";

const { data: deployments } = await octokit.repos.listDeployments({
  owner, repo, environment, per_page: 10,
});

for (const d of deployments) {
  const { data: statuses } = await octokit.repos.listDeploymentStatuses({
    owner, repo, deployment_id: d.id, per_page: 1,
  });
  if (statuses[0]?.state === "success") {
    await octokit.repos.createDeploymentStatus({
      owner, repo, deployment_id: d.id, state: "inactive",
    });
  }
}
```

```yaml
      - name: Deactivate old deployments
        run: npx tsx scripts/deactivate-old-deployments.ts
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          DEPLOY_ENV: production
```

---

## Anti-patterns

- **Skipping `required_contexts: []`**: Without it, the deployment creation will wait
  for required status checks that may never arrive, blocking the deploy.
- **Using the same deployment record for retries**: Each workflow run should create a
  new deployment record; reusing IDs obscures retry history.
- **Posting `success` from a step before confirming Wrangler exit code**: Always gate
  the success status on `if: success()` with Wrangler as a prior step.
- **Leaking the `GITHUB_TOKEN` to Workers source**: Pass it only via env or secrets,
  never embed in wrangler.toml vars.

---

## Gotchas

- `auto_merge: false` is required when `required_contexts` is an empty array; otherwise
  the API returns 409 on branches that have merge conflicts.
- The `environment_url` field is only shown when `state` is `success` or `in_progress`.
  It is silently ignored on `failure` responses.
- GitHub caps visible deployment statuses per record at 100; older ones are truncated in
  the UI but remain queryable via the API.
- `deployment_status` webhooks fire asynchronously — a Workers handler may receive the
  event seconds after the API call; design for idempotent status updates.

---

## Verification

```bash
# List recent deployments and their statuses
gh api /repos/{owner}/{repo}/deployments \
  -F environment=production \
  --jq '.[] | {id, sha: .sha[0:7], created_at} '

# Check statuses for a specific deployment
gh api /repos/{owner}/{repo}/deployments/{id}/statuses \
  --jq '.[] | {state, created_at, environment_url}'
```

Expected: latest record shows `state: success` and a populated `environment_url`.

---

## Related

- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-oidc-cloudflare-deploy.md`
- `github-environments-deployment-protection-rules.md`
- `github-custom-deployment-protection-rules.md`
- `github-webhook-signing-verification.md`

---

## Sources

- https://docs.github.com/en/rest/deployments/deployments
- https://docs.github.com/en/rest/deployments/statuses
- https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#deployment
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
