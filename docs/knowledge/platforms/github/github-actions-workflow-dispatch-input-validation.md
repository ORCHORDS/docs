# GitHub Actions Workflow Dispatch Input Validation

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A `workflow_dispatch` trigger exposes free-form text inputs that operators pass directly to shell commands or Wrangler CLI flags. Without validation, a team member entering `; rm -rf dist` as an environment name causes command injection, or a non-existent D1 database name wastes 20 minutes before the deploy fails. A production gate that expects a specific semantic version is trivially bypassed by entering `latest` via `gh workflow run` because the GitHub REST API accepts any string for any input regardless of the declared `choice` type.

## Context

`workflow_dispatch` inputs support four types (`string`, `boolean`, `choice`, `environment`) and an optional `required` flag. Type enforcement is applied in the GitHub web UI only. The `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` REST endpoint accepts arbitrary strings for every input field. Validation must therefore happen inside the workflow itself — a dedicated `validate` job that downstream deploy jobs declare in their `needs:` list is the standard pattern. Validated values are forwarded as job outputs so the rest of the pipeline never touches raw user input.

## Input schema design

Define inputs with the narrowest type and the smallest valid option set. Use `choice` instead of `string` wherever the valid set is bounded at authoring time.

```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: "Target deployment environment"
        type: choice
        options: [staging, production]
        required: true
        default: staging

      worker_name:
        description: "Cloudflare Worker name (lowercase alphanumeric and hyphens)"
        type: string
        required: true

      image_tag:
        description: "Release tag to deploy (semver, e.g. 1.2.3 or v1.2.3)"
        type: string
        required: true

      dry_run:
        description: "Print plan without deploying"
        type: boolean
        default: false
```

## Validation job pattern

Run a dedicated `validate` job first. Every deploy job lists it under `needs:`. If validation fails, downstream jobs are skipped, not run with invalid data.

```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    outputs:
      worker_name: ${{ steps.check.outputs.worker_name }}
      image_tag: ${{ steps.check.outputs.image_tag }}
    steps:
      - name: Validate and sanitize inputs
        id: check
        env:
          WORKER_NAME: ${{ github.event.inputs.worker_name }}
          IMAGE_TAG: ${{ github.event.inputs.image_tag }}
          ENVIRONMENT: ${{ github.event.inputs.environment }}
        run: |
          set -euo pipefail

          # Worker name: 1-63 chars, lowercase a-z0-9 and hyphens, no leading/trailing hyphen
          if [ ! "$WORKER_NAME" =~ ^[a-z0-9?$ ]]; then
            echo "::error::worker_name '$WORKER_NAME' is invalid. Must be 1-63 lowercase alphanumeric/hyphen characters."
            exit 1
          fi

          # Semver: optional leading v, then X.Y.Z with optional pre-release suffix
          if [[ ! "$IMAGE_TAG" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
            echo "::error::image_tag '$IMAGE_TAG' is not a valid semver string (expected X.Y.Z or vX.Y.Z)."
            exit 1
          fi

          # Validate environment against allowed set (defense-in-depth vs choice type bypass)
          if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
            echo "::error::environment '$ENVIRONMENT' is not allowed. Choose staging or production."
            exit 1
          fi

          # Normalize: strip leading 'v' from tag for downstream consistency
          CLEAN_TAG="${IMAGE_TAG#v}"

          echo "worker_name=${WORKER_NAME}" >> "$GITHUB_OUTPUT"
          echo "image_tag=${CLEAN_TAG}" >> "$GITHUB_OUTPUT"

  deploy:
    needs: validate
    if: needs.validate.result == 'success'
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment }}
    steps:
      - uses: actions/checkout@v4

      - name: Deploy Worker
        if: github.event.inputs.dry_run != 'true'
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
          WORKER: ${{ needs.validate.outputs.worker_name }}
          TAG: ${{ needs.validate.outputs.image_tag }}
        run: |
          echo "Deploying worker '$WORKER' at tag '$TAG'"
          npx wrangler deploy --name "$WORKER" --compatibility-date 2026-08-01

      - name: Dry-run summary
        if: github.event.inputs.dry_run == 'true'
        run: |
          echo "DRY RUN: would deploy ${{ needs.validate.outputs.worker_name }} @ ${{ needs.validate.outputs.image_tag }}"
```

## TypeScript validation script

For rules that outgrow bash, a TypeScript validation script invoked from the step keeps logic testable.

```typescript
// scripts/validate-dispatch.ts
import { appendFileSync } from "node:fs";

const WORKER_RE = /^a-z0-9?$/;
const SEMVER_RE = /^v?(\d+)\.(\d+)\.(\d+)(-[\w.]+)?$/;
const ALLOWED_ENVS = new Set(["staging", "production"]);

interface Inputs {
  workerName: string;
  imageTag: string;
  environment: string;
}

function validate({ workerName, imageTag, environment }: Inputs): void {
  const errors: string[] = [];

  if (!WORKER_RE.test(workerName)) {
    errors.push(`worker_name "${workerName}" fails pattern ${WORKER_RE}`);
  }

  if (!SEMVER_RE.test(imageTag)) {
    errors.push(`image_tag "${imageTag}" is not semver`);
  }

  if (!ALLOWED_ENVS.has(environment)) {
    errors.push(`environment "${environment}" not in allowed set`);
  }

  if (errors.length) {
    errors.forEach((e) => console.error(`::error::${e}`));
    process.exit(1);
  }

  const tag = imageTag.replace(/^v/, "");
  const out = process.env.GITHUB_OUTPUT!;
  appendFileSync(out, `worker_name=${workerName}\n`);
  appendFileSync(out, `image_tag=${tag}\n`);
  console.log(`Validated: worker=${workerName} tag=${tag} env=${environment}`);
}

validate({
  workerName: process.env.INPUT_WORKER_NAME ?? "",
  imageTag: process.env.INPUT_IMAGE_TAG ?? "",
  environment: process.env.INPUT_ENVIRONMENT ?? "",
});
```

Call from the workflow:

```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - name: Validate inputs (TypeScript)
        env:
          INPUT_WORKER_NAME: ${{ github.event.inputs.worker_name }}
          INPUT_IMAGE_TAG: ${{ github.event.inputs.image_tag }}
          INPUT_ENVIRONMENT: ${{ github.event.inputs.environment }}
        run: npx tsx scripts/validate-dispatch.ts
```

## Restricting authorized dispatchers for production

Workflow dispatch is available to any user with write access. Add an actor allowlist for production gating:

```yaml
      - name: Enforce production dispatch allowlist
        if: github.event.inputs.environment == 'production'
        env:
          ACTOR: ${{ github.actor }}
        run: |
          ALLOWED=("alice" "bob" "deploy-bot[bot]")
          for user in "${ALLOWED[@]}"; do
            [[ "$ACTOR" == "$user" ]] && exit 0
          done
          echo "::error::$ACTOR is not authorized to dispatch production deployments."
          exit 1
```

## Anti-patterns

- Interpolating `${{ github.event.inputs.worker_name }}` directly into a `run:` shell script — the expression is substituted before the shell sees it, enabling injection from API callers.
- Relying on the UI `choice` type to prevent unexpected values — the REST and CLI dispatch endpoints ignore declared input types.
- Treating `required: true` as a validator — it only blocks empty submissions in the web UI, not API calls that omit the key entirely (which yields an empty string in the workflow).
- Re-using raw inputs in subsequent `${{ }}` expressions after a validation step has run — the expression is evaluated at parse time before any runtime check can gate it.

## Gotchas

- `boolean` inputs arrive as the string `"true"` or `"false"` in `github.event.inputs`, not as YAML booleans. Test with `== 'true'` in bash, not bare truthiness.
- `workflow_dispatch` inputs are capped at 10 inputs and 10,000 characters per value as of 2026. Exceeding limits causes silent truncation or a 422 error at dispatch time.
- If the `validate` job is skipped rather than failed, downstream jobs with `needs: validate` are also skipped by default. Add `if: needs.validate.result == 'success'` explicitly to enforce a hard gate.
- Validated outputs forwarded via `needs.validate.outputs` still reach downstream jobs as untrusted strings in expressions. Use env vars inside `run:` steps, not `${{ needs.validate.outputs.worker_name }}` directly in shell commands.

## Verification

```bash
# Dispatch with an invalid worker name via CLI (bypasses UI type check)
gh workflow run deploy.yml \
  --field worker_name="../../etc/passwd" \
  --field image_tag="not-a-version" \
  --field environment="staging"

# Check the most recent run result
gh run list --workflow=deploy.yml --limit=1 --json conclusion,status,jobs
# Expected: conclusion=failure at validate job, deploy job=skipped
```

## Related

- `github-actions-workflow-dispatch.md`
- `github-actions-environment-protection.md`
- `github-actions-security-hardening.md`
- `github-actions-stop-commands-untrusted-output.md`
- `github-actions-pull-request-target-poisoning.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#workflow_dispatch
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
- https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/security-hardening-for-github-actions
- https://securitylab.github.com/research/github-actions-preventing-pwn-requests/
