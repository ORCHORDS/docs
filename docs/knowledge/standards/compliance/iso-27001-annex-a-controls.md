# iso-27001-annex-a-controls

**Issue:** Selecting and implementing ISO 27001:2022 Annex A controls for a SaaS company's Statement of Applicability (SoA)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ISO 27001:2022 restructured Annex A to 93 controls across 4 themes (Organisational, People, Physical, Technological). Certification requires a Statement of Applicability justifying which controls are included or excluded. SaaS companies commonly over-exclude controls to reduce scope and fail audits, or include all controls with no implementation evidence.

## Pattern / Solution
**The 4 control themes and control count:**

| Theme | Controls | Key focus |
|---|---|---|
| Organisational (5.x) | 37 | Policies, roles, supplier relations, threat intelligence |
| People (6.x) | 8 | Screening, training, disciplinary process, remote work |
| Physical (7.x) | 14 | Physical security, clear desk, equipment disposal |
| Technological (8.x) | 34 | Access control, crypto, vulnerability management, SDLC |

**High-priority controls for a cloud-native SaaS (frequently audited):**

```
5.23 — Information security for use of cloud services
  → Cloud security policy, CSP selection criteria, shared responsibility matrix

5.30 — ICT readiness for business continuity
  → BCP linked to ISMS scope; tested annually

8.2 — Privileged access rights
  → Quarterly PAM review; just-in-time access logs

8.8 — Management of technical vulnerabilities
  → Vulnerability scan cadence (weekly automated + quarterly manual)
  → Patch SLA: Critical ≤7 days, High ≤30 days

8.23 — Web filtering
  → DNS-level filtering or proxy logs showing enforcement

8.28 — Secure coding
  → SAST/DAST in CI pipeline; developer training records

8.34 — Protection of information systems during audit testing
  → Pen test scope agreement; production data masking for test environments
```

**Statement of Applicability template row:**
```
| Control | Title | Included? | Justification | Implementation status |
| 8.8 | Vuln management | Yes | Cloud SaaS requires continuous patching | Implemented — Snyk + Dependabot |
| 7.4 | Physical security monitoring | Partial | Co-lo DC managed by AWS | Covered by AWS SOC2 / ISO cert |
```

**Exclusion justification must be risk-based.** "Not applicable" is only valid when the control's threat is genuinely absent (e.g., "no on-premises servers" for physical media controls). Convenience exclusions fail UKAS/DAkkS certification bodies.

## Gotchas
- ISO 27001:2022 added 11 new controls not in the 2013 version — check that your SoA reflects the 2022 Annex A, not the old one.
- Certification scope must be defined precisely; auditors will test boundary controls — if you exclude a system, demonstrate the boundary is enforced.
- Controls map to risks in the risk treatment plan; every included control must trace back to at least one accepted risk.
- Internal audits must cover the full scope at least once per certification cycle (3 years); many teams skip physical controls for cloud-only setups and get flagged.
- Supplier/cloud provider certifications cover their scope, not yours — document the residual controls you own under the shared responsibility model.

## Related
- `iso-27001-compliance.md`
- `soc2-type2-controls-mapping.md`
- `vendor-security-assessment.md`
- `privacy-by-design-checklist.md`
