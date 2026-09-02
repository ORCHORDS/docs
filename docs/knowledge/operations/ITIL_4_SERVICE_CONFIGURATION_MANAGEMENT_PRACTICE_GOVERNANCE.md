# ITIL 4 Service Configuration Management Practice Governance

## Purpose

Govern the ITIL 4 service configuration management practice so that accurate configuration information about services and infrastructure exists, is trustworthy when incident responders and change managers rely on it, and is maintained by the people who change the configuration.

## Scope

The practice applies to the studio's configuration management database (CMDB) or equivalent configuration registry, covering service topology, component records, and relationship data. It does not cover infrastructure-as-code file management (covered by deployment practices) or asset lifecycle finance (covered by asset management).

## Workflow

1. Define the configuration model scope: which service components, relationships, and attributes are in scope, and which are deliberately out of scope.
2. Record each configuration item (CI) with an identifier, owner, category, status, and relationships to other CIs.
3. Bind configuration updates to change records: a change that touches production must result in a configuration update within the agreed window.
4. Run reconciliation on a recurring cadence comparing discovered state against recorded state; every divergence becomes a correction task with an owner.
5. Audit a sample of CIs against reality each period to measure registry trustworthiness and find blind spots the discovery tool misses.
6. Publish trustworthiness metrics (completeness, accuracy, freshness) to the consumers who depend on the registry.
7. Review the configuration model when services are added, retired, or restructured.

## Controls and evidence

- CI record schema with mandatory attributes and relationship types.
- Change-to-configuration binding rule and the reconciliation window.
- Reconciliation run results with divergence counts, correction tasks, and closure times.
- Periodic audit results showing sampled CI accuracy and the trustworthiness metric trend.

## Validation

- Sample 10 CIs and confirm each matches discovered state within the freshness window.
- Confirm every production change in the sample period has a corresponding configuration update or a logged exception.
- Confirm divergence corrections close within the agreed window and the backlog trend is flat or falling.

## Failure correction

- **CI does not match reality** → correct the record, find the change that bypassed the binding rule, and close the enforcement gap.
- **Reconciliation backlog growing** → prioritize by service criticality, freeze non-essential changes to the worst-affected services, and add capacity until the backlog falls.
- **Discovery tool blind spot** → add the source to discovery or document a manual update procedure with an owner.

## Limitations

- The registry is a model, not the truth; drift between model and reality is expected and is why reconciliation and audit exist.
- Full relationship graphs for large estates are expensive to maintain; scope deliberately rather than exhaustively.
- Configuration management does not replace infrastructure-as-code; the registry records state, the pipeline enforces it.

## Scope note

This article is part of the operations leaf and pairs with change enablement and deployment management practices. Cross-reference: `itil-4-change-enablement-practice.md`, `deploy/cab-change-management.md`, and `IEEE_828_2012_CONFIGURATION_MANAGEMENT_GOVERNANCE.md`.

## Canonical sources

- AXELOS, *ITIL Foundation, ITIL 4 edition* (2019), service configuration management practice: https://www.axelos.com/certifications/itil-service-management
- ITIL 4 Practices — Service Configuration Management: https://www.axelos.com/certifications/itil-service-management/itil-4-practices
- IEEE Std 828-2012 — Configuration Management in Systems and Software Engineering: https://standards.ieee.org/ieee/828/4329/
- ISO/IEC 19770-1:2017 — IT asset management — Requirements: https://www.iso.org/standard/69022.html
- NIST SP 800-128 — Guide for Security-Focused Configuration Management of Information Systems: https://csrc.nist.gov/publications/detail/sp/800-128/final
