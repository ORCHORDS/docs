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
| [NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) | Final, April 2025; supersedes Rev. 2 | Incident-response integration with risk management |
| [NIST SP 800-218 / SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) | Final | Secure software development |
| [NIST SP 800-218 Rev. 1 / SSDF 1.2](https://csrc.nist.gov/pubs/sp/800/218/r1/ipd) | Initial Public Draft, December 2025; monitored, not treated as final | Forward-looking SSDF changes |
| [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/) | Stable release, May 2025 | Application-security verification requirements |
| [SLSA 1.2](https://slsa.dev/spec/v1.2/) | Approved specification, November 2025 | Source and build supply-chain integrity |
| [OpenSSF OSPS Baseline v2026.02.19](https://baseline.openssf.org/versions/2026-02-19) | Current version as checked 2026-08-22 | Repository and software-project security controls |
| [GitHub Actions secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use) | Current online guidance as checked 2026-08-22 | Workflow least privilege, untrusted-code safety, and immutable action pinning |
| [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) | W3C Recommendation, latest Recommendation dated December 2024 | Accessibility |
| [CISA Secure by Design](https://www.cisa.gov/securebydesign) | Current guidance | Security ownership and secure defaults |
| [Semantic Versioning 2.0.0](https://semver.org/) | Stable | Versioning where semantic compatibility applies |
| [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) + [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) | Standards-track terminology | Normative requirement words |

## Reference-management rules

- Prefer final, primary, authoritative sources.
- Record draft standards as drafts and do not represent them as final.
- Re-check versioned references at least quarterly.
- Do not copy large portions of standards; link and summarize the intent.
- Practitioner forums may inform usability and maintainability decisions, but
  they are non-normative and must not override authoritative requirements.
- When a standard changes materially, open a documentation issue and assess
  every policy that cites it.
