# vendor-security-assessment

**Issue:** Running a structured security assessment before onboarding a new vendor or sub-processor
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Third-party vendors are one of the top breach vectors. GDPR Art. 28, ISO 27001 A.5.19-5.22, SOC 2 CC9.2, and PCI DSS Req 12.8 all require due diligence on suppliers that access, process, or store organisational data. Without a repeatable process, vendor selection is ad hoc and leaves residual risks unmanaged.

## Pattern / Solution
**Tiered assessment model — match assessment depth to risk:**

| Vendor tier | Criteria | Assessment level |
|---|---|---|
| Critical | Processes Restricted data or has privileged system access | Full questionnaire + document review + contract review |
| High | Processes Confidential data; SaaS in the data path | Standard questionnaire + document review |
| Medium | Internal tool; limited data access | Abbreviated questionnaire |
| Low | No data access (e.g., office supplies) | No security assessment |

**Standard security questionnaire (abbreviated):**

```
Organisation
1. Do you have an information security policy reviewed in the last 12 months?
2. Do you hold ISO 27001, SOC 2 Type II, or equivalent certification? (Request report.)

Access Control
3. Is MFA enforced for all admin access to systems that will hold our data?
4. Do you conduct quarterly access reviews?

Data Handling
5. Where will our data be stored (country/region)?
6. Is our data isolated from other customers (logical or physical)?
7. What is your data retention and deletion policy for our data?

Breach & Incident
8. What is your breach notification timeline to customers?
9. Describe your last significant security incident and resolution.

Sub-processors
10. Will you share our data with any sub-processors? List them.
```

**Document requests (Critical/High tier):**
- Most recent SOC 2 Type II or ISO 27001 certificate + report
- Most recent penetration test executive summary (within 18 months)
- Data Processing Agreement (pre-signed or redlined)
- Sub-processor list

**Risk scoring and approval:**
```python
risk_factors = {
    "no_mfa_on_admin": 30,
    "no_certification": 20,
    "data_stored_outside_approved_regions": 25,
    "no_pen_test_in_24_months": 15,
    "breach_history_unresolved": 40,
}
# Score > 50 → escalate to CISO before approval
# Score > 80 → reject or require remediation before onboarding
```

**Ongoing monitoring:**
- Annual reassessment for Critical/High vendors.
- Monitor vendor's public breach disclosure and CVE advisories.
- Require 30-day notice before vendor adds new sub-processors.

## Gotchas
- A vendor's SOC 2 certificate does not automatically cover your use case — read the scope section of the report and the Complementary User Entity Controls (CUECs).
- Pen test reports must be recent; a 3-year-old report is not meaningful evidence.
- Contract SLAs and DPAs are legal controls, not security controls — do not use them as substitutes for technical assurance.
- "We use AWS so we're secure" is not an acceptable answer — the shared responsibility model means vendor must still secure their application layer.
- Free or open-source tools used in production (e.g., self-hosted analytics) still require vendor assessment if they process customer data under your responsibility.

## Related
- `gdpr-dpa-standard-contractual-clauses.md`
- `soc2-type2-controls-mapping.md`
- `iso-27001-annex-a-controls.md`
- `data-classification-policy.md`
