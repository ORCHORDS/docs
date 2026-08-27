# Dependency Inventory Review

## Trigger

Run this review on a defined cadence and when significant releases, dependency changes, supplier changes, or vulnerability events affect a product.

## Inputs

- Current dependency inventory or SBOM
- Build and release metadata
- Supported-version policy
- Vulnerability findings
- Supplier/component provenance where available

## Procedure

1. Identify the software/build version being reviewed.
2. Obtain the current component inventory or SBOM and confirm it maps to that version.
3. Review direct and transitive dependencies where the inventory provides them.
4. Identify unsupported, end-of-life, unknown-provenance, or unexpectedly introduced components.
5. Correlate the inventory with vulnerability monitoring and outstanding remediation work.
6. Investigate differences between declared inventory and the actual build/deployment evidence.
7. Assign owners and deadlines for material gaps.
8. Preserve the inventory, findings, evidence, and decisions for the review record.

## Escalation

Escalate components with critical vulnerabilities, unknown provenance, unsupported status, or unexplained build/inventory mismatches according to security and release governance.

## Completion criteria

- Reviewed inventory is tied to a known software version.
- Material discrepancies are resolved or explicitly accepted.
- High-risk findings have an accountable owner and due date.
- Evidence is retained for the next review.

## Source basis

- NIST — Software Security in Supply Chains: Software Bill of Materials (SBOM)
- NIST SP 800-218 — Secure Software Development Framework (SSDF)
