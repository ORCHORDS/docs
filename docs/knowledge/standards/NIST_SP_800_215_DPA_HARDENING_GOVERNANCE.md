# NIST SP 800-215 Guide to DPA Hardening Governance

## 1. Scope

This card governs ORCHORDS adoption of NIST Special Publication 800-215 ("Guide to Data Protection and Auditing for Information Systems") for the hardening and auditing of Data Processing Applications (DPAs). It applies to organisations that process regulated data through transactional systems, data warehouses, and analytical platforms.

## 2. Normative references

- NIST SP 800-215 (2024) — Guide to DPA Hardening and Auditing.
- NIST SP 800-53 Rev. 5 — Security and Privacy Controls.
- ISO/IEC 27001:2022 — ISMS.
- PCI DSS v4.0 — for payment-data DPAs.

## 3. Core principles

1. **Security in depth** — every DPA receives controls at host, network, application, and data layers.
2. **Least privilege** — DPA accounts are role-based, time-bound, and tagged with tenant context.
3. **Verifiable audit** — every state change and data movement produces an immutable audit record.
4. **Encrypt by default** — at rest, in transit, and during processing where technically feasible.

## 4. Hardening control families

| Family | Controls | Owner |
| --- | --- | --- |
| Identity & access | MFA on all human access; service accounts with workload identity (SPIFFE/SPIRE) and short TTL | IAM |
| Network segmentation | DPA VLAN/segment; default-deny egress; approved egress allow-list | NetEng |
| Data protection | Field-level encryption for PII/PHI/PCI; TDE for data-at-rest; tokenization where applicable | Data Eng |
| Logging | Audit events shipped to SIEM with WORM retention; correlation ID across services | SRE |
| Vulnerability management | Daily SCA, weekly DAST, monthly authenticated scan; SLA: critical ≤ 24 h | AppSec |
| Backup and recovery | DPA backups encrypted, immutable, restored quarterly in tabletop drills | Backup Eng |
| Secrets management | No static secrets in DPA; secret values retrieved from Vault at runtime | Security Eng |

## 5. Auditing cadence

- Continuous: control-plane audit log streams to SIEM with 400-day retention.
- Daily: automated compliance scan comparing running config to codified baseline.
- Quarterly: auditor-led review of access logs, change tickets, and exception register.
- Annual: third-party penetration test and DPA attestation renewal.

## 6. Exceptions

Documented in `policies/exceptions/dpa/<system-id>.md`. All exceptions expire within 90 days and require Security Council approval.

## 7. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. NIST SP 800-215 revisions and regulatory changes (PCI DSS, HIPAA, GDPR) trigger out-of-cycle updates.
