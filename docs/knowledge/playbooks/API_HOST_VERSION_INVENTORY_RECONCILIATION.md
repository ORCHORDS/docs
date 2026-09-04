# API Host and Version Inventory Reconciliation

## Trigger
Run on a regular cadence, before version retirement, after infrastructure changes, and when an unknown or legacy API endpoint is discovered.

## Inputs
- Documented API host/version inventory.
- DNS, gateway, deployment, cloud-service, and API-management inventories available to the organization.
- Version ownership and retirement records.

## Procedure
1. Collect the documented list of API hosts, environments, network audiences, owners, and deployed versions.
2. Independently enumerate API exposure from authoritative infrastructure sources such as DNS, gateways, deployments, or API-management configuration.
3. Reconcile discovered hosts against the documented inventory and investigate every unmatched item.
4. For each active version, confirm owner, support status, security-maintenance approach, and intended retirement state.
5. Identify beta, staging, test, partner, and legacy hosts that have broader exposure than intended.
6. Review nonproduction data sources and determine whether production-origin data is present.
7. If production data is used outside production, verify production-equivalent protection or remove the data dependency.
8. Close or formally retain obsolete endpoints and update inventory evidence.

## Escalation
Escalate unknown public hosts, unowned versions, unsupported exposed versions, or nonproduction endpoints carrying real data without equivalent protection.

## Evidence
- Reconciled host/version inventory.
- Discovery-source snapshots or exports.
- Retirement decisions and owners.
- Exposure/data findings and remediation evidence.

## Completion criteria
Every discovered API host and version is documented, owned, intentionally exposed, and either supported or governed by a concrete retirement decision.

## Source basis
- OWASP API9:2023 Improper Inventory Management: https://owasp.org/API-Security/editions/2023/en/0xa9-improper-inventory-management/
