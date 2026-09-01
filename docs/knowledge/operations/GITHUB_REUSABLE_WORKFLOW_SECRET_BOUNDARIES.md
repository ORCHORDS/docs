# GitHub Reusable Workflow Secret Boundaries

## Purpose

Reusable workflows can receive secrets from caller workflows, but secret propagation should be explicit and minimal. GitHub supports individually mapped secrets and `secrets: inherit`; the latter passes all secrets available to the caller across eligible organization or enterprise boundaries.

## Current GitHub behavior

A reusable workflow can declare named secrets under `on.workflow_call.secrets`. The caller passes matching values through `jobs.<job_id>.secrets`.

For same-organization or same-enterprise calls, the caller can use `secrets: inherit` to make all caller-accessible organization, repository, and environment secrets available to the called workflow without individually listing them in the called workflow's `on.workflow_call` definition.

Environment secrets have a separate boundary: `on.workflow_call` does not accept the `environment` keyword. If the called workflow sets an environment at the job level, that environment's secret takes precedence over a same-named secret passed by the caller.

## Governance pattern

1. Prefer explicit named secret mapping for deployment and high-impact workflows.
2. Use `secrets: inherit` only when the called workflow genuinely requires a broad and stable secret set.
3. Keep called workflow permissions and secret requirements documented together so operators understand both authority sources.
4. Avoid reusing the same secret name for caller-passed and environment-scoped secrets unless the precedence behavior is intentional.
5. Treat changes to a called workflow's secret consumption as security-relevant interface changes.
6. When chaining reusable workflows, pass only the secrets needed by the next hop; secrets are not automatically available to every nested workflow unless explicitly forwarded or inherited.
7. Rotate or revoke credentials if an unintended workflow obtained access, even if no use is observed.

## Environment boundary

Because a called workflow can attach an environment to its job, reviewers should inspect the called workflow itself when determining which secret value will be used. The caller's YAML alone may not reveal that an environment-level secret overrides a passed value.

## Least privilege

Separate secrets by purpose and destination. A reusable test workflow should not inherit production deployment credentials merely because both workflows live in the same organization.

Where OIDC can replace a long-lived credential, prefer short-lived federated identity over distributing static cloud secrets through reusable-workflow interfaces.

## Failure modes

- `secrets: inherit` can expose unrelated secrets to a workflow that only needs one credential.
- Assuming environment secrets can be passed through `workflow_call` can lead to unexpected values at runtime.
- Reusing the same secret name across caller and environment scopes can obscure which credential is active.
- Nested reusable workflows can silently lose required secrets if the intermediate workflow does not forward them.
- Auditing only the caller workflow misses secret use added later inside the reusable workflow.

## Sources

- GitHub Docs — Workflow syntax for GitHub Actions: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Docs — Reuse workflows: https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows
- GitHub Docs — Reusing workflow configurations: https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations

## Scope note

This article describes GitHub Actions reusable-workflow secret propagation. Organization policies, environments, OIDC trust, and external secret managers should be evaluated as separate control layers.