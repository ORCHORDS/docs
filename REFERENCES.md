---
title: "Standards and Guidance Register"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Standards and Guidance Register

This register records external guidance used to modernize ORCHORDS public
policies. Inclusion means the source informs policy design; it does **not**
mean ORCHORDS is certified against it.

## Current normative and reference sources

| Source | Current status used here | Use |
|---|---|---|
| [NIST Cybersecurity Framework 2.0](https://www.nist.gov/cyberframework) | Final | Enterprise cybersecurity governance and outcomes |
| [NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) | Final, April 2025 | Incident-response integration with risk management |
| [NIST SP 800-218 / SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) | Final | Secure software development |
| [NIST SP 800-218 Rev. 1 / SSDF 1.2](https://csrc.nist.gov/pubs/sp/800/218/r1/ipd) | Draft; monitored, not treated as final | Forward-looking SSDF changes |
| [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/) | Stable | Application-security verification requirements |
| [SLSA 1.2](https://slsa.dev/spec/v1.2/) | Approved | Source and build supply-chain integrity |
| [OpenSSF OSPS Baseline](https://baseline.openssf.org/) | Versioned public baseline | Repository and software-project security controls |
| [GitHub Actions secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use) | Current online guidance | Workflow least privilege and immutable action pinning |
| [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) | W3C Recommendation | Accessibility |
| [CISA Secure by Design](https://www.cisa.gov/securebydesign) | Current guidance | Security ownership and secure defaults |
| [Semantic Versioning 2.0.0](https://semver.org/) | Stable | Versioning where semantic compatibility applies |
| [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) + [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) | Standards-track terminology | Normative requirement words |

## Reference-management rules

- Prefer final, primary, authoritative sources.
- Record draft standards as drafts and do not represent them as final.
- Re-check versioned references at least quarterly.
- Do not copy large portions of standards; link and summarize the intent.
- When a standard changes materially, open a documentation issue and assess
  every policy that cites it.
