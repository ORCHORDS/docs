# iac-scanning-checkov-terraform-gates

**Issue:** Security controls that live only as cloud-console guardrails get bypassed the day someone provisions through Terraform. Infrastructure-as-code makes misconfiguration reproducible: one unencrypted RDS block, one `0.0.0.0/0` security group, or one public S3 bucket in a module is copied into every environment on the next apply. IaC scanning (Checkov, tfsec/Trivy IaC, KICS) turns static analysis of HCL/plan files into CI gates so the misconfiguration is caught in the pull request, not in the incident channel.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What to scan and when

1. **Scan the HCL source on every PR.** Code-stage scans (Checkov on `.tf` files) are fast and give developers feedback at commit time, catching obvious issues like missing encryption flags, wildcard IAM actions, and public access blocks.
2. **Scan the resolved plan before apply.** `terraform plan -out=tfplan` plus Checkov's plan scan evaluates interpolated values — variables, remote-state lookups, `count` expansion — which source scanning cannot; a compliant-looking variable can default to `0.0.0.0/0` only in the plan.
3. **Scan modules as a first-class artifact.** Checkov's graph framework evaluates whole resource graphs (e.g., "is this SG attached to something public?"), so scan the module tree, not isolated files; also run `terraform validate` first so parser errors do not masquerade as clean scans.
4. **Scan Kubernetes, serverless, and policy files with the same pipeline.** Checkov covers Helm, Kubernetes manifests, CloudFormation, ARM, Dockerfiles, and more — the point is one gate for all declarative infrastructure, not a Terraform-only tool.
5. **Run pre-commit hooks for fast inner-loop feedback.** Checkov's VS Code extension and pre-commit hook surface failures while writing; CI remains the enforcement point, the IDE is the teaching point.

## Gate policy that survives contact with reality

1. **Fail the build on HIGH/CRITICAL severities first, then tighten.** Starting with a hard gate on everything produces a wall of noise and gets the gate disabled; ratchet the threshold down as the backlog clears.
2. **Suppress with inline, attributed skip comments — never silent baselines.** `# checkov:skip=CKV_AWS_18:reason` keeps the exception next to the code, owned by the author, visible in review; global baseline files rot into "everything is allowed."
3. **Enforce severity AND check-IDs policy in config.** Put thresholds in `.checkov.yaml` (or equivalent) under review, so relaxing the gate is a PR, not a console click.
4. **Distinguish enforced checks from advisory ones by environment.** Prod may hard-fail on encryption and public-exposure checks while dev allows a tagged exception — encode that in policy, not in developer memory.
5. **Block `terraform apply` in CI on new findings, not just PR merges.** A plan between merge and apply can introduce drift (remote state changed meanwhile); re-scan at the apply step for anything not identical to the reviewed plan.
6. **Alert on check-ID churn.** New Checkov releases add checks; schedule a periodic run in report mode so newly-detected issues become a triaged backlog instead of a surprise red build on an unrelated PR.

## Common findings that matter most

1. **Public exposure class.** S3 buckets without public-access blocks, security groups with `0.0.0.0/0` on ports 22/3389/5432, RDS/ES publicly_accessible — these are the top real-world breach enablers and should be near-zero-tolerance.
2. **Encryption-at-rest class.** Unencrypted RDS/EBS/S3/KMS resources; remediation is cheap at creation time and painful after data exists, which is exactly why the gate belongs pre-apply.
3. **Logging and audit class.** CloudTrail multi-region enabled, S3 access logs, VPC flow logs, GuardDuty — the controls that make every other incident investigable.
4. **IAM over-privilege class.** Wildcard actions/resources in inline policies, missing constraints on assumable roles; pair the scanner with `aws iam simulate-principal-policy` or Access Analyzer for runtime grounding.
5. **Secrets in HCL.** Hardcoded keys in `provider` blocks or `default` values; move to environment-injected variables or secret managers and let the secret-pattern checks confirm none regress.
6. **Version-skew class.** Deprecated TLS versions on listeners, outdated engine versions — drift the scanner will catch even when the code "hasn't changed in months."

## Verification

1. **Plant a known bad resource** (public bucket, port-22-everywhere SG) in a branch and confirm the PR gate blocks merge with the expected check-ID.
2. **Verify plan-stage scanning catches interpolation** — set a variable default to an open CIDR only visible post-plan and confirm the apply gate, not just the code scan, fails.
3. **Attempt a silent suppression** (baseline file edit or threshold change) and confirm it requires review — the policy file diff should be the only path.
4. **Upgrade Checkov on a schedule and diff findings** to confirm new checks land in report mode first, then enforcement.
5. **Restore-sanity check:** fix the planted issue, confirm the gate passes, and record the check-ID ↔ runbook mapping for on-call.

**Source:** [Checkov docs](https://www.checkov.io/), [Terrateam: tfsec and Checkov with GitHub Actions](https://terrateam.io/blog/terraform-security-scanning-tfsec-checkov-github-actions), [AWS blog: automated security checks of Terraform scripts](https://aws.amazon.com/blogs/infrastructure-and-automation/save-time-with-automated-security-checks-of-terraform-scripts/).
