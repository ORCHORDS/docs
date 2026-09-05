---
title: Terraform Version Governance (HashiCorp / OpenTofu)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: HashiCorp Terraform (https://developer.hashicorp.com/terraform); OpenTofu (https://opentofu.org/); Terraform Registry; Terraform Cloud / Enterprise
---

# Terraform Version Governance (HashiCorp / OpenTofu)

## Scope

This card governs how `orchords-docs` evaluates Terraform and OpenTofu versions. It is the reference input for any KB card that cites infrastructure-as-code (IaC), Terraform module authoring, Terraform Cloud / Enterprise, or state management.

## Why this card exists

Terraform ships frequent minor releases; OpenTofu is the Linux Foundation fork after HashiCorp's 2023 license change to BSL. The two ecosystems now diverge: HashiCorp Terraform 1.x is BSL-licensed; OpenTofu 1.x is MPL-licensed. Modules written for one may or may not work on the other. A KB card that cites "Terraform" without binding to the version, license, and module-source policy produces a configuration that breaks on first dependency update.

## Version support matrix

| Version | First release | License | Notes |
|---|---|---|---|
| Terraform 1.0.x | June 2021 | BSL (since 1.18) | legacy |
| Terraform 1.5.x | September 2023 | BSL | check, moved, import |
| Terraform 1.6.x | October 2023 | BSL | removed-state, test mocking |
| Terraform 1.7.x | January 2024 | BSL | moved blocks, removed |
| Terraform 1.8.x | May 2024 | BSL | resource graph improvements |
| Terraform 1.9.x | May 2025 | BSL | test framework, output values |
| Terraform 1.10.x | November 2025 (planned) | BSL | upcoming |
| OpenTofu 1.6.x | January 2024 | MPL-2.0 | OpenTofu fork initial |
| OpenTofu 1.7.x | November 2024 | MPL-2.0 | registry state encryption |
| OpenTofu 1.8.x | April 2025 | MPL-2.0 | dynamic block iteration |
| OpenTofu 1.9.x | August 2025 | MPL-2.0 | improvements |

References: `https://developer.hashicorp.com/terraform`, `https://opentofu.org/`.

## License policy

- HashiCorp Terraform 1.x is Business Source License (BSL) since 1.18. The license allows non-competitive use; competing commercial use requires a license.
- OpenTofu is MPL-2.0 (open-source).
- The KB reference card declares the license per project. Default for new projects: OpenTofu.

## State management

| Backend | Status |
|---|---|
| Local | development only |
| S3 | production |
| Azure Storage | production |
| GCS | production |
| HashiCorp Consul | legacy |
| Terraform Cloud | managed; OSS-friendly plan |
| OpenTofu state backend | OpenTofu native |

Policy:

- State is encrypted at rest.
- State lock is enabled (DynamoDB for S3, native locks for others).
- State versioning is enabled.
- State is stored in a separate account/subscription than the resources.
- No secrets in state.

## Module sourcing

| Source | Trust level |
|---|---|
| HashiCorp / OpenTofu verified module | high |
| Internal module (first-party) | high |
| Trusted third-party module (e.g., terraform-aws-modules) | medium |
| Untrusted third-party module | low; review required |

Policy:

- Internal modules preferred for sensitive workloads.
- Third-party modules reviewed via PR; SBOM-equivalent (`terraform-graph`); pinned to commit SHA.
- Module tag pinning is forbidden; commit-SHA pinning is required.

## Mandatory pre-flight (before adopting a new Terraform configuration)

1. The version is within the support matrix.
2. The license is documented.
3. The state backend is configured (encryption, locking, versioning).
4. The module source policy is documented.
5. CI / CD is wired (`terraform plan` on PR, `terraform apply` on merge).
6. State pull / push is restricted to the CI runner.

## CI / CD pipeline

1. PR pipeline: `terraform fmt -check`, `terraform validate`, `terraform plan` (output as PR comment).
2. Merge pipeline: `terraform apply` with explicit environment.
3. Drift detection: `terraform plan -detailed-exitcode` (cron job).

## Mandatory pre-flight (before adopting a new Terraform module)

1. Source is verified (commit SHA).
2. License is documented.
3. Provider version constraints are pinned.
4. Variable validation is wired.
5. Output values are documented.

## Observability

- `terraform_apply_duration_seconds` (histogram).
- `terraform_plan_resource_count` (gauge, per workspace).
- `terraform_drift_detected_count` (counter, per workspace).
- `terraform_state_lock_wait_seconds` (histogram).

## Sources

- HashiCorp Terraform: `https://developer.hashicorp.com/terraform`
- OpenTofu: `https://opentofu.org/`
- Terraform Registry: `https://registry.terraform.io/`
- OpenTofu Registry: `https://search.opentofu.org/`
- HashiCorp BSL FAQ: `https://www.hashicorp.com/license-faq`
- Terraform style guide: `https://developer.hashicorp.com/terraform/language/style`
