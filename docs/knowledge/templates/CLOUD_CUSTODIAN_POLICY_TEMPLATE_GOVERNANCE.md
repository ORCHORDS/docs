# Cloud Custodian Policy Template Governance

## Purpose

Cloud Custodian (CNCF Sandbox project) is a stateless rules engine that evaluates cloud-resource inventories against YAML policies and produces actions such as notify, tag, stop, snapshot, delete, or invoke a Lambda. A reusable Cloud Custodian policy template captures the policy skeleton — filter pattern, action set, mode (ephemeral or periodic), and resource type — so that teams can adopt a baseline policy and specialize only the differentiating fields (tags, regions, schedules, escalation chains). Without a template, organizations reinvent the same policy grammar and drift across teams.

The template must remain generic: it MUST NOT embed real account identifiers, role ARNs, notification channel IDs, or specific resource tags that identify individual customers.

## Scope

This template applies to Cloud Custodian policies authored against AWS, Azure, GCP, or Kubernetes inventories (the four resource types Cloud Custodian natively supports). It does not cover Cloud Custodian c7n-org (the organizational multi-account orchestrator) or the c7n-policies catalog as primary sources, although the catalog may be referenced. The template does not address Terraform Sentinel, OPA, AWS Config rules, or Azure Policy; those policies have different grammars and require their own templates.

## Workflow

1. Open the template and complete the header with the policy identifier, the resource type, the policy owner, the policy version, the date, and the severity.
2. Define the `policies` block with:
   - `name`: human-readable policy name.
   - `resource`: the Cloud Custodian resource type (for example `ec2`, `s3`, `iam-role`, `azure.vm`, `kubernetes.deployment`).
   - `mode`: `{ "type": "cloudtrail" }` for event-driven, `{ "type": "periodic", "schedule": "rate(24 hours)", "execution-options": {...} }` for scheduled, or pull-based modes.
   - `filters`: one or more value or JMESPath filters selecting the in-scope resources.
   - `actions`: notify (with role and template), tag, snapshot, stop, delete, or invoke Lambda with explicit `execution-options` for cross-account roles.
3. Validate the policy locally with `custodian validate <policy>.yml` before committing.
4. Run the policy in dry-run mode (`--dryrun`) against a single account or subscription first to confirm the resource set.
5. Promote the policy to enforcement mode and route notifications through the documented escalation chain.
6. Record the policy in the policy catalog with owner, severity, schedule, and last-run timestamp.

## Controls and evidence

- Header records owner, version, severity, last-reviewed date.
- Policy block is validated by `custodian validate`.
- Dry-run output references the resource set evaluated.
- Enforcement logs reference the policy identifier, action taken, and resource affected.
- Policy catalog entry includes the cross-account role or scope config used.

## Validation

- `custodian validate` exits 0 for the policy file.
- Dry-run output identifies the expected resource set against a known-good test account or subscription.
- Enforcement logs reference the policy by name and severity.
- Notifications reach the documented escalation chain (for example a Slack channel or PagerDuty service).
- The policy is recorded in the central catalog with a freshness date.

## Failure correction

Common defects include policies that reference roles the executing account does not have permission to assume, filters that match zero resources (silent failure), and missing action scopes (for example `ec2:StopInstances` without `ec2:DescribeInstances`). Corrective actions include adding the missing IAM scope, fixing the filter pattern, and adding a metric that flags zero-result runs as suspect.

## Limitations

- The template does not address Cloud Custodian c7n-org multi-account orchestration; a separate template is required.
- It does not cover Cloud Custodian Lambda-layer deployment; the deployment topology is captured in a separate runbook.
- It does not substitute for an IaC policy review; policies that create resources (for example auto-remediation that provisions tags) should be reviewed against the IaC pipeline.
- It does not address Cloud Custodian's policy-pack or rules-file conventions; teams that use those should document the convention separately.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **platforms** (Cloud Custodian deployment), **operations** (notification routing and policy catalog maintenance), **security** (remediation actions and IAM scope), and **engineering** (policy testing in CI). The template should be used together with those sibling-leaf articles.

## Canonical sources

- Cloud Custodian documentation (CNCF Sandbox): https://cloudcustodian.io/docs/
- Cloud Custodian GitHub repository (CNCF Sandbox): https://github.com/cloud-custodian/cloud-custodian
- Cloud Custodian c7n-org documentation (multi-account orchestration): https://cloudcustodian.io/docs/orgtools/c7n-org.html

Sources were verified on September 1, 2026.
