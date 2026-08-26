# penetration-testing-scope

**Issue:** Defining and managing penetration test scope for a SaaS application to satisfy compliance requirements and produce actionable results
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Penetration tests are required by PCI DSS (Req 11.4), ISO 27001 (A.8.8), SOC 2 (CC7.1), and many enterprise customer security questionnaires. Poorly scoped tests generate low-value reports that satisfy box-ticking but miss real vulnerabilities. Common failures: scope too narrow (only unauthenticated endpoints), too broad (production systems during business hours), or missing agreed rules of engagement.

## Pattern / Solution
**Scope definition document — required before test begins:**

```markdown
## Penetration Test Scope — [Product Name] — [Date]

### In Scope
- Web application: https://app.example.com (all authenticated and unauthenticated endpoints)
- API: https://api.example.com/v1/* (REST and GraphQL)
- Admin panel: https://admin.example.com
- Mobile app: iOS v2.x, Android v2.x (static and dynamic analysis)
- Infrastructure: AWS account ID 123456789 (VPC 10.0.0.0/16)
  - EC2 instances tagged env=staging
  - RDS cluster: rds-staging.cluster-xxx.eu-west-1.rds.amazonaws.com
- Authentication: OAuth 2.0 PKCE flow, API key auth, SSO (SAML 2.0)

### Out of Scope
- Production environment (test accounts in staging only)
- AWS management console (no lateral movement to other AWS accounts)
- Third-party services: Stripe, Intercom, Cloudflare (test against mocked endpoints only)
- Denial of service testing
- Social engineering / phishing of employees
- Physical security

### Test Accounts Provided
- Standard user: test-user@pentest.example.com
- Admin user: test-admin@pentest.example.com
- Multi-tenant: two isolated test organisations
```

**Rules of Engagement:**
- Testing window: weekdays 09:00–17:00 UTC (notify if outside window needed)
- Emergency stop contact: security@example.com + mobile number
- Data handling: all data from test environment destroyed within 30 days of report delivery
- Findings shared within 5 business days of test completion; critical findings notified immediately

**Standard test categories:**
```
OWASP Top 10 Web (2021):
  A01 Broken Access Control
  A02 Cryptographic Failures
  A03 Injection (SQL, NoSQL, LDAP, command)
  A04 Insecure Design
  A05 Security Misconfiguration
  A06 Vulnerable & Outdated Components
  A07 Auth & Session Management Failures
  A08 Software & Data Integrity Failures
  A09 Security Logging & Monitoring Failures
  A10 SSRF

Business logic:
  - Privilege escalation (standard → admin)
  - Tenant isolation bypass (access another tenant's data)
  - Insecure direct object reference
  - Rate limiting and brute force

Infrastructure:
  - Network segmentation (can staging reach production?)
  - Secrets in environment variables / metadata service
  - IAM privilege escalation paths
```

**Remediation SLA (recommend in contract with tester):**
- Critical (CVSS ≥9): Retest within 14 days of fix
- High (CVSS 7–8.9): Retest within 30 days
- Medium/Low: Included in next scheduled test

## Gotchas
- Never run authenticated pen tests against production with real customer data — a misconfigured test payload can corrupt or exfiltrate live data.
- Ensure your cloud provider's penetration testing policy is acknowledged (AWS has a formal notification process for certain test types).
- Report must specify CVSS scores and include evidence (screenshots, HTTP request/response) — "critical finding" without reproduction steps is not useful.
- Tester credentials must be revoked immediately after test completion.
- Annual cadence is the minimum; after significant architecture changes, trigger an unscheduled test.

## Related
- `bug-bounty-program-setup.md`
- `security-incident-response-plan.md`
- `pci-dss-v4-saas.md`
- `soc2-type2-controls-mapping.md`
