# CIS Critical Security Controls v8 Governance

## 1. Scope

This card governs ORCHORDS adoption of the **Center for Internet Security Critical Security Controls v8** (May 2021, current) as the actionable baseline that complements NIST CSF 2.0 and ISO/IEC 27001:2022.

## 2. Normative references

- CIS Critical Security Controls v8 (2021).
- Implementation Groups (IG1, IG2, IG3) — organisational maturity tiers.
- CIS Benchmarks (companion documents — not directly applicable to governance).
- ORCHORDS Security Control Matrix (internal SCM).

## 3. Implementation Group classification

| IG | Profile | Examples | ORCHORDS applicability |
| --- | --- | --- | --- |
| IG1 | Small organisations with limited assets | 56 safeguards | Mandatory for every team |
| IG2 | Mid-sized organisations with regulatory exposure | 130 safeguards (IG1 + 74) | Mandatory for production systems |
| IG3 | Sensitive-data organisations | 153 safeguards (IG2 + 23) | Mandatory for Tier 1 services |

## 4. The 18 control families

1. Inventory and Control of Enterprise Assets
2. Inventory and Control of Software Assets
3. Data Protection
4. Secure Configuration of Enterprise Assets and Software
5. Account Management
6. Access Control Management
7. Continuous Vulnerability Management
8. Audit Log Management
9. Email and Web Browser Protections
10. Malware Defenses
11. Data Recovery
12. Network Infrastructure Management
13. Network Monitoring and Defense
14. Security Awareness and Skills Training
15. Service Provider Management
16. Application Software Security
17. Incident Response Management
18. Penetration Testing

## 5. Safeguard ownership

| Safeguard group | Owner | Tracking system |
| --- | --- | --- |
| Inventory (CSC 1, 2) | Platform | `platform/inventory/*` |
| Data Protection (CSC 3) | Data Governance | `data-governance/policies` |
| Configuration (CSC 4) | Platform Security | CIS Benchmarks in cluster |
| Account Management (CSC 5, 6) | IAM | IAM platform dashboards |
| Vulnerability (CSC 7) | Security Engineering | Riskledger |
| Logging (CSC 8) | SRE | Datadog / Grafana |
| IR (CSC 17) | Security Operations | Incident tracker |

## 6. Audit cadence

- IG1 controls: monthly evidence collection.
- IG2 controls: weekly evidence collection plus quarterly internal audit.
- IG3 controls: weekly evidence collection plus monthly internal audit and annual external audit.

## 7. Gap remediation

- Any IG2 safeguard not implemented triggers a remediation ticket with a 90-day SLA.
- Any IG3 safeguard not implemented triggers an exception review by the CISO.
- A safeguard that cannot be implemented must be mapped to a compensating control and documented in the SCM.

## 8. Mapping to other frameworks

| CIS CSC v8 | NIST CSF 2.0 | ISO 27001:2022 |
| --- | --- | --- |
| CSC 1 | ID.AM-1, ID.AM-2 | A.5.9 |
| CSC 7 | ID.RA-1, DE.CM-8 | A.8.8 |
| CSC 8 | PR.PT-1, DE.AE-3 | A.8.15 |
| CSC 17 | RS.MA, RS.AN, RS.CO | A.5.24, A.5.25 |

## 9. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. A new CIS CSC major release (v9) or material change to NIST CSF triggers out-of-cycle updates.
