# Application Security Portfolio Assurance Review

## Trigger
Run on a regular governance cadence, after major portfolio changes, after acquisitions/migrations, and when management cannot demonstrate required application-security coverage.

## Inputs
- Application/API inventory with owners and business/data context.
- Common risk model and risk-tier definitions.
- Application-security policy/baseline controls.
- Required design/testing/operational assurance by risk tier.
- Findings, exception, testing, and retirement data.

## Procedure
1. Reconcile the application/API inventory with active deployment, exposure, CMDB, cloud, gateway, or other authoritative portfolio sources.
2. Assign or verify accountable owners and current business/data criticality for each system in scope.
3. Apply the common risk model and confirm risk-tier assignments are current and internally consistent.
4. For each risk tier, document the required assurance depth, such as threat/design review, code/dependency testing, dynamic/penetration testing, operational monitoring, and review cadence.
5. Sample applications from each tier and verify required baseline controls and assurance activities have current evidence.
6. Identify overdue testing, missing baseline controls, open high-risk findings, and exceptions that exceed their intended review/expiry dates.
7. Confirm reusable security controls/libraries/patterns are available for common requirements and identify duplicated bespoke controls creating avoidable inconsistency.
8. Review whether security activities cover requirements/design, development, testing, rollout, operations/change management, and retirement according to organizational policy.
9. Review stale/superseded systems and confirm retirement candidates are removed from exposure or have an explicit retirement plan.
10. Produce portfolio-level coverage metrics and escalate material assurance gaps according to risk tier.

## Escalation
Escalate unowned or unknown active applications, high-risk systems without required assurance evidence, overdue high-risk exceptions, and material portfolio blind spots that prevent management visibility.

## Evidence
- Reconciled application/API inventory.
- Risk-tier assignment evidence.
- Tier-specific assurance requirements.
- Sample application evidence by tier.
- Coverage, findings, and exception metrics.
- Retirement candidate decisions.

## Completion criteria
The active application/API portfolio is owned, risk-tiered, covered by a common security baseline, and able to demonstrate the required assurance depth and management visibility for each tier.

## Source basis
- OWASP Top 10:2025 — Establishing a Modern Application Security Program: https://owasp.org/Top10/2025/0x03_2025-Establishing_a_Modern_Application_Security_Program/
- OWASP Top 10 project page: https://owasp.org/www-project-top-ten/
