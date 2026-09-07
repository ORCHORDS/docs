# ISO/IEC 27031:2023 ICT Readiness for Business Continuity Governance

## 1. Scope

This card governs ORCHORDS adoption of ISO/IEC 27031:2023 ("Information and Communication Technology Readiness for Business Continuity") as the framework for ICT continuity planning across cloud-resident services, on-prem data centres, and SaaS dependencies.

## 2. Normative references

- ISO/IEC 27031:2023 (3rd edition).
- ISO 22301:2019 (Business Continuity Management Systems).
- NIST SP 800-34 Rev. 1 (Contingency Planning Guide).
- ORCHORDS Business Continuity Policy (internal).

## 3. Continuity lifecycle

1. **Plan**: define ICT continuity strategy and resource requirements.
2. **Implement**: build runbooks, roles, and tooling.
3. **Operate**: maintain procedures and integrate with change management.
4. **Test**: exercise plans on a defined cadence.
5. **Maintain**: improve based on incidents and tests.

## 4. ICT continuity roles

| Role | Responsibility |
| --- | --- |
| ICT Continuity Manager | Owns the program, reports to CISO. |
| Service Owner | Owns service-level runbooks and RTO/RPO targets. |
| Crisis Commander | Activates the runbook during a declared incident. |
| Recovery Lead | Coordinates recovery actions during an exercise or live event. |

## 5. RTO/RPO matrix

| Tier | RTO | RPO | Examples |
| --- | --- | --- | --- |
| Tier 1 | ≤ 15 min | ≤ 5 min | Payments, identity |
| Tier 2 | ≤ 1 hour | ≤ 15 min | Customer APIs |
| Tier 3 | ≤ 4 hours | ≤ 1 hour | Internal tools |
| Tier 4 | ≤ 24 hours | ≤ 4 hours | Reporting, batch jobs |

## 6. Key clauses (27031:2023)

- **Clause 6**: Planning — strategy, scope, and resource planning.
- **Clause 7**: Implementation — programmes, projects, controls.
- **Clause 8**: Operation — operational continuity, BCMS integration.
- **Clause 9**: Performance evaluation — exercises, internal audits, management review.
- **Clause 10**: Improvement — corrective actions, continual improvement.

## 7. Test types and cadence

| Test | Cadence | Description |
| --- | --- | --- |
| Tabletop | Quarterly | Walk through the runbook in a meeting. |
| Walk-through | Semi-annually | End-to-end read-through with cross-functional attendees. |
| Component | Semi-annually | Recover one service against the runbook. |
| Full simulation | Annually | Simulate a Tier 1 outage. |
| Crisis activation | Annually | Declare an actual exercise and activate the Crisis Commander. |

## 8. Supplier continuity

- Top 5 SaaS dependencies require a published BCP that meets our RTO/RPO.
- Quarterly review of vendor BCP tests; on-site audit annually for Critical vendors.
- Multi-cloud or dual-region deployment mandatory for Tier 1 services.

## 9. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. Material changes to the ORCHORDS business continuity policy or a Tier 1 incident trigger out-of-cycle updates.
