# GitHub Actions Ephemeral Just-in-Time (JIT) Runner Registration

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Self-hosted runners that stay permanently registered accumulate credentials, cached artifacts, and state that
persists across jobs from different contexts or contributors. When a runner is compromised or its token leaked,
the blast radius spans every future job on that runner. Just-in-time (JIT) runners solve this: each job gets a
brand-new runner that registers immediately before the job, runs exactly one job, and then deregisters itself —
leaving zero persistent credentials or shared state behind.

## Context

GitHub's JIT runner registration API (available since Actions Runner v2.316) allows creating a single-use
runner token via the REST API that self-registers the runner for exactly one job. Combined with container
orchestrators (Docker, Kubernetes, AWS ECS, Cloud Run) or a VM provisioning pipeline, this pattern creates
fully ephemeral execution environments. The controller — which holds the GitHub App or PAT with `administration`
scope — generates a JIT config blob that the runner container consumes at startup. After the job finishes the
runner automatically unregisters without needing a removal step.

---

## Generating a JIT Registration Config via the GitHub API

The JIT config API returns an encoded runner config object that the Actions Runner binary can consume directly
via `--jitconfig`. This requires either a GitHub App installation token or a fine-grained PAT with
`administration:write` on the target repository or organization.

```typescript
// src/runner-controller.ts — runs as a Worker or Node service
interface JitConfig {
  encoded_jit_config: string;
}

export async function createJitRunner(
  installationToken: string,
  org: string,
  labels: string[],
  runnerGroupId = 1,
): Promise<string> {
  const res = await fetch(
    `https://api.github.com/orgs/${org}/actions/runners/generate-jitconfig`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${installationToken}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "jit-runner-controller/1.0",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: `ephemeral-${crypto.randomUUID().slice(0, 8)}`,
        runner_group_id: runnerGroupId,
        labels,
        work_folder: "_work",
      }),
    },
  );

  if (!res.ok) {
    throw new Error(`JIT config API ${res.status}: ${await res.text()}`);
  }

  const { encoded_jit_config } = await res.json<JitConfig>();
  return encoded_jit_config;
}
```

---

## Docker-based Ephemeral Runner Container

The runner container receives the JIT config via an environment variable. The `--once` flag (implied by JIT
mode) tells the runner to exit after completing one job.

```dockerfile
# runner/Dockerfile
FROM ghcr.io/actions/actions-runner:latest

# Additional tooling for Workers CI
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*
RUN npm install -g wrangler@latest

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
```

```bash
#!/usr/bin/env bash
# runner/entrypoint.sh
set -euo pipefail

if [ -z "${ENCODED_JIT_CONFIG:-}" ]; then
  echo "ERROR: ENCODED_JIT_CONFIG is required" >&2
  exit 1
fi

# Self-register with the JIT config blob and run exactly one job
exec /path/to/project --jitconfig "$ENCODED_JIT_CONFIG"
# Container exits automatically after job completion; no cleanup needed
```

---

## Controller Workflow: Spawn Runner on Demand

A lightweight controller job runs on a GitHub-hosted runner to provision the JIT container before the actual
work job begins. The `needs` dependency ensures ordering.

```yaml
# .github/workflows/ephemeral-worker-deploy.yml
name: Deploy via Ephemeral JIT Runner

on:
  push:
    branches: [main]

jobs:
  provision-runner:
    runs-on: ubuntu-24.04
    outputs:
      runner-label: ${{ steps.jit.outputs.label }}
    steps:
      - name: Generate JIT config and launch container
        id: jit
        env:
          GH_TOKEN: ${{ secrets.RUNNER_CONTROLLER_TOKEN }}  # fine-grained PAT w/ administration:write
          ORG: ${{ github.repository_owner }}
        run: |
          LABEL="jit-$(uuidgen | cut -c1-8)"
          echo "label=$LABEL" >> "$GITHUB_OUTPUT"

          # Call JIT API to get encoded config
          JIT_CONFIG=$(gh api \
            --method POST \
            -H "Accept: application/vnd.github+json" \
            "/orgs/$ORG/actions/runners/generate-jitconfig" \
            -f "name=$LABEL" \
            -F runner_group_id=1 \
            -f "labels[]=$LABEL" \
            -f work_folder=_work \
            --jq '.encoded_jit_config')

          # Launch container (example using Docker on the GitHub-hosted runner)
          docker run -d \
            --name "$LABEL" \
            -e "ENCODED_JIT_CONFIG=$JIT_CONFIG" \
            --network host \
            ghcr.io/${{ github.repository }}/runner:latest

  deploy:
    needs: provision-runner
    runs-on: ${{ needs.provision-runner.outputs.runner-label }}
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Cloudflare Workers
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: wrangler deploy --env production
```

---

## Kubernetes-based JIT Runner with Actions Runner Controller

When using the Actions Runner Controller (ARC) on Kubernetes, JIT mode is the default for `EphemeralRunnerSet`
resources. Each pod is created per job and deleted on completion.

```yaml
# k8s/ephemeral-runner-set.yaml
apiVersion: actions.github.com/v1alpha1
kind: EphemeralRunnerSet
metadata:
  name: workers-jit-runners
  namespace: arc-runners
spec:
  ephemeralRunnerSpec:
    githubConfigUrl: "https://github.com/my-org"
    githubConfigSecret: arc-controller-secret
    runnerScaleSetName: workers-jit
    template:
      spec:
        containers:
          - name: runner
            image: ghcr.io/my-org/runner:latest
            resources:
              requests:
                cpu: "1"
                memory: "2Gi"
              limits:
                cpu: "2"
                memory: "4Gi"
            env:
              - name: CLOUDFLARE_API_TOKEN
                valueFrom:
                  secretKeyRef:
                    name: cloudflare-secrets
                    key: api-token
```

---

## Security Considerations for JIT Runners

```typescript
// Validate that only expected workflows can request a JIT runner
// by inspecting the OIDC token before issuing the JIT config.
export async function validateWorkflowOidc(
  oidcToken: string,
  allowedRepos: string[],
): Promise<void> {
  const [, payloadB64] = oidcToken.split(".");
  const payload = JSON.parse(atob(payloadB64 + "=="));

  if (!allowedRepos.includes(payload.repository)) {
    throw new Error(`Unauthorized repository: ${payload.repository}`);
  }

  if (payload.ref !== "refs/heads/main") {
    throw new Error(`JIT runners allowed only on main branch, got: ${payload.ref}`);
  }
}
```

---

## Anti-patterns

- **Using a long-lived runner registration token instead of JIT** — registration tokens (`/runners/registration-token`)
  do not expire after one job; a leaked token can register unlimited runners until manually revoked.
- **Sharing JIT configs between jobs** — a JIT config blob is single-use and non-transferable. Generating one
  config and passing it to multiple container instances causes only one to succeed; others silently fail to register.
- **Persisting the runner work directory across jobs** — mount the `_work` folder inside the ephemeral container's
  writable layer, not on a host volume, to ensure complete isolation.
- **Controller job on a self-hosted runner** — the controller that calls the JIT API must run on a trusted
  GitHub-hosted runner to avoid circular trust dependencies.

---

## Gotchas

- JIT config blobs are valid for **60 minutes** from generation. Containers that take longer than that to start
  (e.g. large image pulls) will fail to register. Pre-pull images to avoid cold-start latency.
- The `generate-jitconfig` API requires `administration:write` at the **org or repo level**, not the weaker
  `actions` scope. Fine-grained PATs must explicitly grant this.
- Actions Runner Controller's `EphemeralRunnerSet` requires ARC controller version ≥ 0.9.0 for JIT mode.
- GitHub imposes a limit of **1 000 registered runners** per organization. Ephemeral runners that fail to
  deregister (e.g. due to host crash) count against this limit until their 30-day auto-cleanup runs.

---

## Verification

```bash
# Confirm no persistent runners accumulate
gh api /orgs/MY_ORG/actions/runners --jq '.runners[] | {name, status, busy}'

# Check that runner count does not grow between deploys
BEFORE=$(gh api /orgs/MY_ORG/actions/runners --jq '.total_count')
gh workflow run ephemeral-worker-deploy.yml
sleep 120
AFTER=$(gh api /orgs/MY_ORG/actions/runners --jq '.total_count')
[ "$BEFORE" -eq "$AFTER" ] && echo "Cleanup verified" || echo "Runner leak detected"
```

---

## Related

- `github-actions-self-hosted-runners.md`
- `self-hosted-runners-docker-official-image.md`
- `github-runner-group-repository-workflow-access-boundary.md`
- `github-actions-github-token-permission-minimization.md`

---

## Sources

- https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-just-in-time-runners
- https://docs.github.com/en/rest/actions/self-hosted-runners#create-configuration-for-a-just-in-time-runner-for-an-organization
- https://github.com/actions/runner/blob/main/docs/adrs/0276-ephemeral-runners.md
- https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners-with-actions-runner-controller/deploying-runner-scale-sets-with-actions-runner-controller
