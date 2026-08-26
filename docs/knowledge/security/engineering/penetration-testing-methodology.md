# Penetration Testing Methodology

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your organization runs quarterly vulnerability scans and annual compliance
audits but has never conducted a structured penetration test. Automated
scanners find known CVEs and misconfigurations, but they miss business
logic flaws, chained vulnerabilities, and attack paths that require human
reasoning. You need a methodology to scope, execute, and report
penetration tests systematically.

## Context

Penetration testing simulates real-world attacks against your systems to
identify exploitable vulnerabilities before adversaries do. Unlike
automated scanning, penetration testing includes manual exploitation,
attack chaining, and business logic testing. The three primary
methodologies — PTES, OWASP WSTG, and NIST SP 800-115 — cover different
scopes. A mature testing program blends PTES's lifecycle management with
OWASP's technical depth and MITRE ATT&CK's threat intelligence.

## Methodologies

### PTES (Penetration Testing Execution Standard)

The most comprehensive methodology for general-purpose enterprise
penetration testing. Seven phases:

1. **Pre-engagement interactions** — scope, rules of engagement, legal
   agreements, emergency contacts, timeline, and deliverables.
2. **Intelligence gathering** — passive and active reconnaissance. OSINT,
   DNS enumeration, technology fingerprinting, social engineering
   reconnaissance.
3. **Threat modeling** — identify attack surfaces, prioritize targets based
   on business impact, map threat actors to assets.
4. **Vulnerability analysis** — automated scanning (Nessus, Nuclei, Burp)
   combined with manual testing. Correlate findings across tools.
5. **Exploitation** — attempt to exploit identified vulnerabilities. Prove
   impact with controlled exploitation — data access, privilege
   escalation, lateral movement.
6. **Post-exploitation** — determine the value of compromised systems.
   Assess data exposure, persistence mechanisms, and further attack paths.
7. **Reporting** — executive summary, technical findings, risk ratings,
   evidence (screenshots, logs), and remediation recommendations.

### OWASP Web Security Testing Guide (WSTG)

Focused on web application testing. Covers 12 categories:

| Category | Focus |
|---|---|
| Information gathering | Fingerprinting, application mapping |
| Configuration and deployment | TLS, HTTP headers, error handling |
| Identity management | Registration, account provisioning, enumeration |
| Authentication | Credentials, multi-factor, password policies |
| Authorization | Path traversal, privilege escalation, IDOR |
| Session management | Cookies, tokens, fixation, CSRF |
| Input validation | SQLi, XSS, command injection, SSRF, file upload |
| Error handling | Stack traces, error codes, information leakage |
| Cryptography | Weak algorithms, key management, transport layer |
| Business logic | Workflow bypass, price manipulation, race conditions |
| Client-side | DOM XSS, clickjacking, WebSocket, postMessage |
| API testing | REST/GraphQL, rate limiting, mass assignment |

### NIST SP 800-115

Government-oriented. Focuses on planning, execution, and post-testing
activities. Less technically prescriptive but strong on governance, rules
of engagement, and reporting requirements.

## Testing types

| Type | Access | Knowledge | Best for |
|---|---|---|---|
| **Black box** | External only | No internal knowledge | Simulating an external attacker |
| **Gray box** | Authenticated | Partial knowledge (credentials, docs) | Realistic insider or compromised account |
| **White box** | Full access | Source code, architecture docs | Maximum coverage, code-assisted testing |

## Common tools (2026)

| Phase | Tools |
|---|---|
| Reconnaissance | Amass, Subfinder, Shodan, theHarvester |
| Scanning | Nmap, Nuclei, Nessus, Masscan |
| Web testing | Burp Suite Pro, OWASP ZAP, Caido |
| Exploitation | Metasploit, SQLMap, custom scripts |
| Post-exploitation | BloodHound (AD), Impacket, Cobalt Strike |
| Reporting | PlexTrac, AttackForge, Dradis |

## Scoping checklist

- [ ] Define in-scope and out-of-scope systems (IPs, domains, apps).
- [ ] Agree on testing window (dates, hours, time zones).
- [ ] Define rules of engagement (no DoS, no social engineering unless
  explicitly approved, no production data destruction).
- [ ] Obtain written authorization (signed by someone with authority).
- [ ] Exchange emergency contacts (both sides).
- [ ] Define severity rating system (CVSS, custom risk matrix).
- [ ] Agree on communication channels during the test.
- [ ] Define deliverables and timeline for the report.

## Anti-patterns

- **Scan-and-report** — running Nessus/Nuclei and repackaging the output
  as a "penetration test report." Automated scanning is not penetration
  testing. A pentest includes manual exploitation, attack chaining, and
  business logic testing.
- **No scope agreement** — testing without written scope and authorization
  is illegal in most jurisdictions, even if the client verbally agreed.
- **Testing in production without safeguards** — exploitation in
  production risks service disruption. Use staging environments where
  possible; when production testing is necessary, avoid destructive
  techniques and DoS-like payloads.
- **Findings without business context** — "XSS on the About page" and
  "XSS on the payment form" have vastly different business impact. Rate
  findings by exploitability and business impact, not just CVSS.

## Gotchas

- **Cloud shared infrastructure** — penetration testing AWS, Azure, or GCP
  resources may require notifying the cloud provider. AWS allows testing
  without notification for most services; Azure and GCP have notification
  requirements.
- **Rate limiting and WAF** — web application firewalls and rate limiting
  may block scanning tools. Coordinate with the client to whitelist
  testing IPs or test from behind the WAF for a realistic assessment.
- **Credential testing scope** — brute-force and password spray attacks
  may lock out real accounts. Use dedicated test accounts or coordinate
  lockout thresholds.
- **Retesting** — a pentest without a retest cycle is incomplete. Schedule
  a focused retest 30-60 days after remediation to verify fixes.

## Verification

- Penetration tests are conducted at least annually and after significant
  architecture changes.
- Scope, rules of engagement, and authorization are documented before
  testing begins.
- Findings are rated by exploitability and business impact.
- Remediation is tracked with owners and deadlines.
- Retesting confirms that critical and high findings are fixed.
- Pentest reports are retained for compliance evidence.

## Related

- `documentation/docs/policies/security/owasp-top-10-2025.md`
- `documentation/docs/policies/security/owasp-api-top-10-2023.md`
- `documentation/docs/policies/testing/security-testing-automation-pipeline.md`
- `documentation/docs/policies/security/waf-rules-configuration.md`

## Source URLs (verified 2026-08-16)

- PTES standard — http://www.pentest-standard.org/
- OWASP WSTG — https://owasp.org/www-project-web-security-testing-guide/
- OWASP penetration testing methodologies — https://owasp.org/www-project-web-security-testing-guide/stable/3-The_OWASP_Testing_Framework/1-Penetration_Testing_Methodologies
- HackerDNA 2026 methodology — https://hackerdna.com/blog/web-application-penetration-testing
- NIST SP 800-115 — https://csrc.nist.gov/publications/detail/sp/800-115/final
