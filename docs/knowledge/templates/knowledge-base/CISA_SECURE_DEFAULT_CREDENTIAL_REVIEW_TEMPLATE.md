# CISA Secure-Default Credential Review Template

Use this record to assess product credential defaults against CISA Secure by Design manufacturer guidance. This is a review aid for voluntary secure-by-design practices, not a statement that every product is legally required to follow this exact model.

## Review metadata

- Product/service: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Deployment/installation model: `<cloud/appliance/on-premises/etc.>`

## Initial credential behavior

| Entry point | Credential behavior at first use | Unique per instance/account? | Forced secure setup? | Evidence |
| --- | --- | --- | --- | --- |
| Administrative login | `<behavior>` | `<yes/no>` | `<yes/no>` | `<reference>` |
| Local/service login | `<behavior>` | `<yes/no>` | `<yes/no>` | `<reference>` |
| Recovery/reset | `<behavior>` | `<yes/no>` | `<yes/no>` | `<reference>` |

## Review checks

- [ ] The product does not ship one reusable default password across installations, tenants, appliances, or accounts.
- [ ] Initial credentials are unique or the product requires secure credential establishment before authenticated functionality becomes exposed.
- [ ] Factory reset/reinstall does not restore a universal manufacturer credential.
- [ ] Test, support, manufacturing, rescue, and maintenance paths do not introduce reusable default passwords.
- [ ] Documentation does not treat customer hardening as the sole control for an insecure manufacturer-supplied default.
- [ ] Remote and administrative access paths receive the same secure-default review.

## Verification evidence

- Two clean-instance credential comparison: `<result>`
- Factory-reset/reinstall test: `<result>`
- Firmware/image/configuration search: `<reference/result>`
- Support/recovery-path review: `<result>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Sources

- CISA/FBI, Product Security Bad Practices update, January 17, 2025: https://www.cisa.gov/news-events/alerts/2025/01/17/cisa-and-fbi-release-updated-guidance-product-security-bad-practices
- CISA, Secure by Design manufacturer guidance on eliminating default passwords: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-335a
