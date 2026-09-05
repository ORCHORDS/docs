# FedRAMP Continuous Monitoring (ConMon) Evidence Collection

## Purpose
Operate the FedRAMP Rev. 5 continuous-monitoring programme and produce monthly / annual / significant-change evidence for the authorised cloud service.

## Procedure
1. Identify the SSP boundary, the Moderate (or High / Low) baseline controls in scope, and the FedRAMP-defined parameters (overrides).
2. Monthly:
   - Vulnerability scan with a FedRAMP-acceptable scanner (Nessus / Qualys); produce machine-readable results and human-readable narrative.
   - POA&M update: open items, severity, scheduled close date, residual risk; align to FedRAMP POA&M template.
   - Plan-of-action follow-up: confirm Critical / High remediation within SLA (Critical 30 days; High 90 days; Moderate 180 days).
3. Quarterly:
   - Significant-change assessment screening per NIST SP 800-37 Rev. 3; trigger full assessment when warranted.
   - Configuration / patch verification (CIS / SCAP where applicable).
4. Annual:
   - Annual assessment by an accredited 3PAO; deliver Security Assessment Report (SAR).
   - SSP refresh; SAR refresh; POA&M refresh.
   - Operating-system / database / application inventory refresh; track EOL / EoS software.
5. Continuous:
   - Capture supply-chain risk-management evidence (SR family, NIST SP 800-161 Rev. 2); align FedRAMP supply-chain tab.
   - Maintain FIPS 140-3 / NIST SP 800-131A:2024 cryptographic-module inventory.
   - Run incident response per US-CERT / FedRAMP timelines.
6. Submit monthly ConMon package to the JAB / PMO (or agency Authorising Official) per ConMon Strategy Guide.

## Source basis
- FedRAMP Rev. 5 baseline materials.
- NIST SP 800-53 Rev. 5; NIST SP 800-37 Rev. 3; NIST SP 800-161 Rev. 2.
- FedRAMP ConMon Strategy Guide; FIPS 140-3; NIST SP 800-131A:2024.
