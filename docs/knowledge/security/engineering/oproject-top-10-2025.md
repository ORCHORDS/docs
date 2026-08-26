# owasp-top-10-2025

**Issue:** OWASP Top 10 2025 — what changed, what to know
**Date:** 2026-08-09
**Status:** documented

## Symptom
The OWASP Top 10 changed in 2025. You're still using
the 2021 list. The 2025 list has new categories. You
miss a critical risk. You get breached.

## Root cause
**The OWASP Top 10 is updated.** Use the 2025 list.

**Source:** OWASP Top 10 2025:
https://owasp.org/Top10/2025/

## The "OWASP Top 10 2025" list

1. **A01:2025 — Broken Access Control** (3.73%)
2. **A02:2025 — Security Misconfiguration** (3.00%, up from #5)
3. **A03:2025 — Software Supply Chain Failures** (new, expanded)
4. **A04:2025 — Cryptographic Failures** (3.80%, down from #2)
5. **A05:2025 — Injection** (down from #3)
6. **A06:2025 — Insecure Design** (down from #4)
7. **A07:2025 — Authentication Failures** (#7, renamed)
8. **A08:2025 — Software or Data Integrity Failures** (#8)
9. **A09:2025 — Security Logging & Alerting Failures** (#9)
10. **A10:2025 — Mishandling of Exceptional Conditions** (new)

The list is the standard.

## The "A01 Broken Access Control" pattern

For A01 (the #1 risk):
- **Least privilege:** Default deny
- **Deny by default:** For new features
- **Tenant isolation:** Always
- **Ownership check:** Every resource
- **SSRF prevention:** New in 2025

**KB refs:**
- `multi-tenant-data-isolation.md`
- `feature-cookbook-permission-modeling.md`
- `feature-cookbook-permission-modeling-detail.md`

## The "A02 Security Misconfiguration" pattern

For A02 (moved to #2):
- **No defaults:** Remove default accounts
- **Latest security features:** Enabled
- **No verbose errors:** Stack traces hidden
- **Security headers:** All of them
- **Updated software:** Patched

**KB refs:**
- `security-headers-comprehensive.md`
- `security-headers-deep-dive.md`

## The "A03 Software Supply Chain" pattern

For A03 (new, expanded):
- **Pin versions:** `package-lock.json`
- **Audit:** `npm audit`, `cargo audit`
- **SBOM:** Software Bill of Materials
- **Sign:** Sigstore, Cosign
- **Dependabot:** Automated updates
- **Reproducible builds:** Bit-for-bit

**KB refs:**
- `dependabot-config.md`
- `pat-self-merge-workaround.md`
- `dependency-upgrade-strategies.md`

## The "A04 Cryptographic Failures" pattern

For A04:
- **TLS 1.3:** Modern
- **Argon2id:** For passwords
- **AES-256-GCM:** At rest
- **Never MD5/SHA1:** For security
- **Random IV/nonce:** Each operation
- **Key rotation:** Every 90 days

**KB refs:**
- `password-storage-argon2.md`
- `encryption-at-rest-detail.md`
- `jwt-best-practices.md`

## The "A05 Injection" pattern

For A05:
- **Parameterized queries:** Always
- **Output encoding:** Always
- **Allow-list:** For column/table names
- **ORM:** Drizzle, Prisma
- **No string concat:** Ever

**KB refs:**
- `sql-injection-prevention-detail.md`
- `sql-injection-deep-dive.md`
- `xss-prevention-detail.md`
- `xss-deep-dive.md`

## The "A06 Insecure Design" pattern

For A06:
- **Threat modeling:** At design time
- **Security requirements:** Per feature
- **Rate limiting:** Always
- **Defense in depth:** Multiple layers
- **Secure defaults:** Out of the box

**KB refs:**
- `feature-cookbook-rate-limiting.md`
- `feature-cookbook-rate-limiting-detail.md`
- `safe-deploy-checklist.md`

## The "A07 Authentication Failures" pattern

For A07 (renamed):
- **Multi-factor:** Always for important
- **Passkeys/WebAuthn:** Modern
- **Rate limit login:** 5 attempts
- **No default creds:** Enforced
- **Session timeout:** Per security req

**KB refs:**
- `feature-cookbook-auth.md`
- `password-storage-argon2.md`
- `totp-mfa-implementation.md`
- `webauthn-passkey-flow.md`

## The "A08 Integrity Failures" pattern

For A08:
- **Verify signatures:** On updates
- **SRI:** For scripts
- **Trusted Types:** For DOM
- **Verify CI artifacts:** Sigstore
- **Verify webhooks:** HMAC

**KB refs:**
- `feature-cookbook-webhook-detail.md`
- `feature-cookbook-webhook.md`

## The "A09 Logging & Alerting Failures" pattern

For A09:
- **Log security events:** Always
- **Alert:** Real-time
- **Audit log:** Immutable
- **Don't log secrets:** Redact
- **Centralize:** SIEM

**KB refs:**
- `audit-log-as-product.md`
- `audit-log-security.md`
- `audit-log-mandatory.md`
- `feature-cookbook-incident-response.md`

## The "A10 Exceptional Conditions" pattern

For A10 (new):
- **Don't leak errors:** To user
- **Don't fail open:** For security
- **Handle timeouts:** Gracefully
- **Handle panics:** Catch + alert
- **Don't fail closed in unsafe state:** Default to safe

```ts
try {
  return await doRiskyThing();
} catch (err) {
  // Don't leak the error to the user
  logEvent('error', 'error', { error: String(err) });

  // Don't fail open
  if (isSecurityCritical) {
    return new Response('Service unavailable', { status: 503 });
  }

  // Fail safe
  return fallback();
}
```

The error is handled.

## The "OWASP 2021 vs 2025" pattern

For changes:
| 2021 | 2025 |
|---|---|
| A01: Broken Access Control | A01: Broken Access Control |
| A02: Cryptographic Failures | A02: Security Misconfiguration |
| A03: Injection | A03: **Software Supply Chain** (new) |
| A04: Insecure Design | A04: Cryptographic Failures |
| A05: Security Misconfiguration | A05: Injection |
| A06: Vulnerable Components | (merged into A03) |
| A07: Auth Failures | A06: Insecure Design |
| A08: Integrity Failures | A07: Authentication Failures |
| A09: Logging Failures | A08: Integrity Failures |
| A10: SSRF | A09: Logging Failures |
| | A10: **Mishandling of Exceptional Conditions** (new) |

The categories changed.

## The "OWASP compliance" pattern

For compliance:
- **OWASP ASVS:** Application Security Verification Standard
- **OWASP SAMM:** Software Assurance Maturity Model
- **OWASP Top 10:** Awareness (what we use)
- **NIST SSDF:** Secure Software Development Framework

For most apps, the **Top 10** is the minimum bar.

## Verification
- **Test:** Each A is covered
- **Test:** Code review per A
- **Live:** Monitor for A's
- **Audit:** Annual review

## Gotchas
- **The "2021 list" anti-pattern.** Use 2025.
- **The "checklist theater" anti-pattern.** Real defense.
- **The "no logging" anti-pattern.** Always log.

## Related
- `security/` (25 entries)
- `compliance/` (9 entries)
- OWASP: https://owasp.org/Top10/2025/
- OWASP ASVS: https://owasp.org/www-project-application-security-verification-standard/
