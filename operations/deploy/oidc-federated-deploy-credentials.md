# oidc-federated-deploy-credentials

**Issue:** Deploy pipelines that authenticate to cloud providers with long-lived credentials — an AWS access key in GitHub Secrets, a GCP service-account JSON in a variable, a Cloudflare API token pasted into a CI setting — duplicate a secret across two systems, never get rotated on schedule, and give whichever workflow (or compromised dependency executing inside a workflow) that finds them whatever the key can do, for as long as the key lives. GitHub's own security-hardening docs frame the fix as deleting the duplication entirely: configure an OIDC trust relationship, let each workflow job mint a short-lived, job-scoped token, and exchange it for cloud credentials that expire when the job ends. This article covers the token-exchange mechanics, concrete AWS and GCP setups, how to scope trust policies so a token from the wrong repo/branch/environment is worthless, and the gotchas (the July 2026 `sub` claim format change, self-hosted runners, reusable workflows). For OIDC used to *sign artifacts* rather than to authenticate deploys, see supply-chain-security-sbom-signing.md — same issuer, different purpose.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The problem with long-lived deploy credentials

1. **Two copies of a hot secret.** The classic pattern stores cloud credentials as GitHub secrets that were created at the cloud provider — GitHub's docs call out exactly this duplication. Every copy is another place to leak from: secret-scanning-2026.md catches some of these, but a credential exfiltrated at runtime from a step's environment never touches a scanner.
2. **Rotation is toil that does not happen.** Long-lived keys should rotate every 90 days; in practice the key created for the v1 pipeline in 2023 is still active because three services quietly depend on it. `image-pull-secrets-rotation.md` documents the same rot for registry creds.
3. **Blast radius is the key's lifetime and scope.** A static key leaked in CI logs (or printed by a misconfigured `set -x`) is valid until someone notices. The OIDC alternative yields tokens that "expire automatically" at job end — typically ~1 hour — so a leaked token is a curiosity, not an incident.
4. **Attribution and scoping are lies.** Everything deployed with the shared key appears as one identity, so audit logs cannot distinguish a prod deploy from a staging one, and the least-privilege boundary is whatever the key can touch — usually everything.

## How the exchange actually works

1. **The CI platform is the identity provider.** GitHub's OIDC provider (`https://token.actions.githubusercontent.com`) issues a JWT unique to each workflow job when a step requests it (`permissions: id-token: write`, fetched via the toolkit's `getIDToken()` or the official login actions).
2. **The JWT's claims are the trust decision.** The cloud provider validates the token against your preconfigured trust conditions: issuer (`iss`), subject (`sub` — encodes repo, environment, ref), audience (`aud`), plus claims like `repository`, `ref`, and `environment`. No claim match, no credentials.
3. **The exchange yields job-limited cloud creds.** AWS maps it via `sts:AssumeRoleWithWebIdentity`; GCP maps it via Workload Identity Federation exchanging the external token for short-lived Google credentials. Either way, what the workflow holds expires with the job — no secret was ever stored, so none needs rotating.
4. **The trust policy is the new perimeter.** Security now lives in one reviewable place: the cloud-side role trust / pool attribute conditions. That policy deserves the same code review rigor as IAM permissions themselves.

## AWS pattern

1. **Create the IAM OIDC provider once per org.** Register `token.actions.githubusercontent.com` with a thumbprint; then create one role per deploy target whose trust policy looks like:

```json
{
  "Effect": "Allow",
  "Principal": { "Federated": "arn:aws:iam::ACCOUNT:oidc-provider/token.actions.githubusercontent.com" },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub": "repo:ORG/REPO:environment:production"
    }
  }
}
```

2. **Consume it with the official action.** `aws-actions/configure-aws-credentials` with `role-to-assume` and the OIDC `id-token: write` permission does the exchange in one step; no `aws-access-key-id` secret anywhere.
3. **One role per environment, not per org.** The `sub` condition above binds the role to a GitHub *environment*, so prod-deploy authority lives only in workflows that actually target the `production` environment — which is where deployment-approval-workflow.md reviewers and environment secrets already sit.
4. **Version the trust policy in Terraform.** The provider thumbprint and role conditions drift exactly like the rest of IAM; manage it with the same modules structure as terraform-modules-structure.md.

## GCP pattern

1. **Workload Identity Pool + provider, no service account keys.** Create a pool, add a provider whose issuer is GitHub's, and let `google-github-actions/auth` exchange the workflow token. Google's guidance is explicit that Workload Identity Federation is preferred over service account keys because it "eliminates long-lived credentials" via the trust relationship.
2. **Constrain with attribute conditions.** An attribute condition like `assertion.repository == 'ORG/REPO'` (optionally `&& assertion.ref == 'refs/heads/main'`) on the provider restricts which workflows can federate at all — the GCP-side equivalent of the AWS `sub` check.
3. **Map attributes to service-account impersonation.** Attribute mappings bind the external token's `sub` to a Google identity allowed to impersonate the deploy service account; grant that impersonation per project/environment so staging pipelines cannot touch prod projects.
4. **Never fall back to a JSON key "temporarily."** The temp key becomes the permanent key. If a tool cannot use federated creds, put that tool behind a wrapper (Cloud Build, a self-hosted runner with workload identity) instead of downgrading the whole pipeline.

## Scoping trust correctly (this is where setups go wrong)

1. **Pin the `sub` claim to the narrowest stable identity.** `repo:ORG/REPO:environment:production` beats `repo:ORG/REPO:ref:refs/heads/main` when deploys are gated by environments, and both massively beat `repo:ORG/REPO:*` — the wildcard means any workflow in the repo, including one a compromised PR sneaked onto a non-protected branch, can assume prod.
2. **Know the July 2026 `sub` format change.** GitHub documents that repositories created after July 15, 2026 use a new *immutable* `sub` format based on owner/repository IDs rather than names. Trust conditions written against the old string format will not match tokens from new repos (and renames no longer break trust in the new format). Audit existing conditions before onboarding post-July-2026 repos.
3. **Use custom properties for attribute-based access.** Admins can surface repository custom properties as `repo_property_*` claims, enabling ABAC trust conditions ("every repo with property `deploy-tier=prod`") instead of maintaining hardcoded repo allow lists — the scalable version of scoping when you have dozens of pipelines.
4. **Reusable workflows rewrite the `sub`.** A job calling a reusable workflow gets a `sub` of the form `repo:CALLER...` + `job_workflow_ref` pointing at the called workflow. If your org centralizes deploys in reusable pipelines (github-actions-self-hosted.md), trust `job_workflow_ref` pinned to a tag, or the trust policy will silently stop matching.
5. **Set the audience where the provider allows.** Default audiences (`sts.amazonaws.com`, GCP's) are fine; custom audiences help when multiple clouds trust the same issuer — an AWS condition on `aud` prevents a GCP-intended token from being replayed elsewhere.

## Gotchas and failure modes

1. **Self-hosted runners without OIDC egress.** Keyless exchange requires the runner to reach the issuer and the cloud STS; locked-down self-hosted runners that cannot fetch the OIDC token will fail the login step — decide deliberately between opening that egress and keeping key-based auth for those runners only, scoped to a low-privilege role.
2. **`id-token: write` is per-job.** Forgetting the `permissions:` block is the number-one setup failure; the login action fails with an opaque 403 rather than "you forgot permissions."
3. **A trusted pipeline still runs third-party actions.** Federation removes the *stored* secret, not supply-chain risk inside the job — a malicious action with `id-token: write` can mint a valid token for its own job. Keep pinning actions by digest/SHA (the discipline in secret-scanning-2026.md and dependency-update-strategy.md contexts) and grant the permission only on jobs that authenticate.
4. **Federated creds still obey IAM.** Short-lived does not mean narrow. The exchanged role's permission policy is what caps damage — least-privilege review of deploy roles is unchanged homework, now more valuable because the credential half is solved.
5. **Dependabot rides the same rail for registries.** Dependabot supports OIDC for AWS CodeArtifact, Azure DevOps Artifacts, and JFrog Artifactory, which removes static registry credentials (and their rate limits) from dependency-update workflows — the same pattern applied to pulls rather than pushes.
