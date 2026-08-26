# eu-cyber-resilience-act-product-security-lifecycle

**Issue:** A product with digital elements has no documented vulnerability, update, support, and evidence lifecycle for potential EU Cyber Resilience Act obligations.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Product security cannot be retrofitted from a CVE feed alone. The Cyber Resilience Act creates lifecycle responsibilities for covered products and supply-chain actors; applicability and timing require legal analysis, while engineering needs durable vulnerability, update, SBOM, support, and evidence processes.

**Source:** [Regulation (EU) 2024/2847](https://eur-lex.europa.eu/eli/reg/2024/2847/oj) and [European Commission CRA overview](https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act).

## Fix

- obtain scope determination from qualified counsel;
- maintain product/component inventory, ownership, support period, and security-update plan;
- operate a vulnerability intake, triage, coordinated-disclosure, remediation, and customer-communication process;
- generate and protect technical/security documentation and SBOM evidence;
- test update/rollback and end-of-support procedures;
- track regulatory milestones separately from technical delivery assumptions.

## Verification

- A reported vulnerability has an owner, triage record, fix/mitigation path, and communication decision.
- Component inventory and SBOM can be produced for a release.
- A security update is tested, deployable, and reversible.
- Scope and evidence gaps have owned remediation plans.

## Related

- `security/sbom-vulnerability-scanning.md`
- `security/exploit-prioritized-vulnerability-triage.md`
