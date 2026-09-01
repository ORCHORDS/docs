# GitHub Reusable Workflow OIDC Trust

## Purpose

Reusable workflows can centralize deployment logic, but cloud access should be granted only when the expected reusable workflow actually performed the job. GitHub Actions OIDC exposes claims that let receiving services distinguish the caller repository from the reusable workflow implementation.

## Trust claims

For jobs that run through a reusable workflow, GitHub includes `job_workflow_ref` and `job_workflow_sha` claims. The caller repository and triggering ref remain represented by the normal repository and workflow claims.

Where the cloud provider supports custom claims, trust can require a specific reusable workflow path or repository. Where only the OIDC subject is available, GitHub allows subject customization to include `job_workflow_ref`.

## Governance pattern

1. Identify deployments that are intended to run only through approved reusable workflows.
2. Bind receiving cloud roles to the expected caller scope and reusable workflow identity.
3. Prefer immutable workflow references, such as a commit SHA, for high-risk reusable deployment workflows.
4. Keep caller permissions minimal; nested reusable workflows cannot elevate `GITHUB_TOKEN` permissions beyond the caller's grant.
5. Test claim changes before removing previous trust rules.
6. Review trust whenever the reusable workflow repository, file path, ownership, or reference strategy changes.
7. Record the reusable workflow SHA in deployment evidence where reproducibility matters.

## Caller versus called workflow

Do not confuse the caller's `workflow_ref` with `job_workflow_ref`. The caller context identifies the workflow that initiated the job; `job_workflow_ref` identifies the reusable workflow that supplied the called job definition.

A cloud trust condition that checks only the caller repository does not prove that the approved reusable workflow was used.

## Re-run behavior

GitHub documents different behavior for reusable workflows referenced by mutable refs when re-running all jobs versus re-running failed or individual jobs. For deterministic security-sensitive deployments, pinning the called workflow to a commit SHA avoids ambiguity about which reusable workflow content should execute.

## Failure modes

- Trusting every workflow in an organization when only one deployment workflow is intended broadens access unnecessarily.
- Checking only the caller repository fails to enforce centralized reusable-workflow policy.
- Referencing reusable deployment workflows by mutable branches or tags can change trusted deployment code without changing the caller.
- Assuming a nested reusable workflow can increase token permissions is incorrect; permissions can only stay the same or become more restrictive.

## Sources

- GitHub Docs — Using OpenID Connect with reusable workflows: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows
- GitHub Docs — OpenID Connect reference: https://docs.github.com/en/actions/reference/security/oidc
- GitHub Docs — Reusing workflow configurations: https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations

## Scope note

Receiving cloud providers differ in supported OIDC claims and trust-policy syntax. Verify the provider's current OIDC capabilities before relying on a custom claim.