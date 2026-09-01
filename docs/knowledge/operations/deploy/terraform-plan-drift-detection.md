# Terraform Plan Drift Detection Cadence

**Issue:** Terraform state drifts from real infrastructure whenever someone makes an out-of-band change, and a team that only runs `terraform plan` during scheduled releases may not notice drift for weeks. By the time the next apply runs, the plan may either silently restore drifted resources or refuse to apply because of cross-resource dependencies that have shifted. A regular drift-detection cadence catches out-of-band changes earlier and creates the operational muscle memory to handle drift deliberately rather than as a fire.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What Drift Detection Is And Is Not

A drift-detection run is `terraform plan -refresh-only` invoked on a schedule. The `-refresh-only` flag tells Terraform to query the current state of every resource from the provider and update the state file in memory without producing a plan for changes. The output is the diff between what the providers report and what the state file believes; the diff is the drift report. The state file is updated in memory but not committed unless the operator follows up with `terraform apply -refresh-only`, which is the deliberate step that records the drift into state.

This distinction matters operationally. A continuous drift scan that updates state automatically turns Terraform into a passive observer; an out-of-band change is silently accepted, and the next configuration-driven apply will not roll it back. A continuous drift scan that does not update state surfaces drift as a report and forces a human decision. Most teams should choose the latter; the former is appropriate only when the system of record is the provider, not the Terraform configuration.

## Setting The Cadence

The right cadence depends on the rate of out-of-band changes, not on the rate of declared changes. A development environment with many engineers may produce drift multiple times per day; a tightly governed production environment may produce drift monthly. Run drift detection hourly for development, daily for staging, and weekly for production. Each cadence should be a CI job that runs `terraform plan -refresh-only` against the relevant workspace and posts the output to a Slack channel or equivalent.

A subtle point: the cadence must be tight enough that drift is detected before the next planned change. If a production workspace is drifted for three weeks and then an engineer runs a planned change, the plan will mix declared changes with drift and become unreviewable. Run drift detection at half the cadence of planned changes so the team never combines the two. For a production environment with weekly planned changes, daily drift detection gives a comfortable buffer.

## Drift Reports And Triage

Drift reports should be machine-readable and human-actionable. The CI job should parse the plan output and emit a structured event that lists every drifted resource, the field that drifted, and the direction (provider reports a value that differs from state). The event should be tagged with severity based on the resource kind and the field; a drifted IAM policy is a high-severity event that warrants immediate page, a drifted tag is a low-severity event that warrants batch remediation.

Triage procedure: review the drift report within 24 hours of detection. For each drifted resource, decide whether the drift is intentional (e.g., a managed rotation of a secret) or accidental. If intentional, update the configuration so the drift is no longer drift. If accidental, restore the resource to its declared state by running `terraform apply` with the original configuration; the plan will show the drift-to-declared change and the apply will roll it back.

## Drift Detection Versus Compliance Scanning

Drift detection at the Terraform level is distinct from compliance scanning at the cloud-provider level. A compliance scanner like AWS Config or Azure Policy can detect that a resource violates a rule without reference to Terraform; Terraform drift detection tells you that the resource disagrees with the declared configuration. The two are complementary: a resource can be compliant with policy and drifted from configuration, or vice versa. Use both, and correlate their outputs so the team can see when a single change produces both a drift report and a compliance alert.

The combined dashboard should answer two questions per resource: is it declared? is it compliant? A resource that is declared and compliant is healthy. A resource that is declared but non-compliant requires a configuration update. A resource that is not declared but compliant is an unmanaged resource that may need to be imported or removed. A resource that is not declared and non-compliant is shadow infrastructure that needs immediate investigation.

## Failure Modes

The most damaging failure is drift detection that triggers an automatic `terraform apply`. A misconfigured automation can revert an emergency out-of-band change that an operator made to mitigate an incident. Drift reports should always be human-reviewed before any apply; the pipeline should post the report and stop. The same caution applies to `terraform apply -refresh-only`, which records drift into state but does not change real infrastructure; an automatic refresh-only is harmless but trains the team to ignore drift reports.

A second failure is drift detection that runs without proper credentials. A scan that fails to refresh any resource produces an empty drift report that falsely indicates no drift. Configure the drift job to fail loudly when the refresh fails, and validate at least one resource per run to ensure the refresh actually happened. A scheduled job that silently produces empty drift reports is worse than no drift detection at all.

A third failure is drift detection ignored during incident response. Operators making emergency out-of-band changes will sometimes mark the drift as expected, then forget to update the configuration. The drift report pile grows, and eventually a planned change fails because the configuration does not match the live state. Use the drift report as part of the post-incident review checklist and require the incident commander to update the configuration within a defined window.

## Canonical sources

1. https://developer.hashicorp.com/terraform/cli/commands/plan
2. https://developer.hashicorp.com/terraform/tutorials/state/refresh