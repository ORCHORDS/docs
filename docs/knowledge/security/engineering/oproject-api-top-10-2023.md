# owasp-api-top-10-2023

**Issue:** OWASP API Security Top 10 (2023)
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your API has endpoints. Users can access other users'
data. Bots buy all the tickets. Old API versions are
running in prod. You wish you had a security checklist.

## Root cause
**APIs have unique attack surfaces.** Follow OWASP.

**Source:** OWASP API Security:
https://owasp.org/www-project-api-security/

## The "OWASP API Top 10 2023" pattern

For the 10 API risks:
1. **API1:2023 - Broken Object Level Authorization (BOLA)**
2. **API2:2023 - Broken Authentication**
3. **API3:2023 - Broken Object Property Level Authorization**
4. **API4:2023 - Unrestricted Resource Consumption**
5. **API5:2023 - Broken Function Level Authorization**
6. **API6:2023 - Unrestricted Access to Sensitive Business Flows**
7. **API7:2023 - Server Side Request Forgery (SSRF)**
8. **API8:2023 - Security Misconfiguration**
9. **API9:2023 - Improper Inventory Management**
10. **API10:2023 - Unsafe Consumption of APIs**

The risks are the API risks.

## The "BOLA" pattern (API1)

For object level authorization:
- **Issue:** User can access other users' objects by ID
- **Example:** `/api/users/123` returns user 123 even
  when caller is user 456
- **Fix:** Check ownership in every endpoint

```typescript
// ❌ Bad
const user = await db.users.findOne({ id: params.id });
return user;

// ✅ Good
const user = await db.users.findOne({ id: params.id });
if (user.tenantId !== ctx.tenant.id) {
  return new Response("Forbidden", { status: 403 });
}
return user;
```

The check is in every endpoint.

## The "broken auth" pattern (API2)

For authentication:
- **Issue:** Auth tokens forgeable, brute-forceable
- **Fix:**
  - MFA via RADIUS
  - Cert-based
  - Password via LDAP/AD/IdP
  - Account lockout
  - Step-up auth

The auth is industry standard.

## The "BOPLA" pattern (API3)

For object property level:
- **Issue:** Excessive data exposure + mass assignment
- **Fix:**
  - Schema allowlist
  - Don't return all properties
  - DTO pattern
  - Validate inputs

The properties are explicit.

## The "resource consumption" pattern (API4)

For resource consumption:
- **Issue:** No rate limit, no size limit
- **Fix:**
  - Rate limit (token bucket)
  - Max request size
  - Max concurrent per user
  - Max per IP
  - Max CPU/memory per request

The consumption is bounded.

## The "BFLA" pattern (API5)

For function level:
- **Issue:** Admin endpoint accessible to user role
- **Fix:**
  - Role-based access
  - Default deny
  - Audit admin endpoints

The functions are role-gated.

## The "sensitive business flow" pattern (API6)

For business flows:
- **Issue:** Bot buys all tickets, scalpers win
- **Fix:**
  - CAPTCHA for high-value flows
  - Rate limit by user
  - Anomaly detection
  - Manual review

The flows are protected.

## The "SSRF" pattern (API7)

For SSRF:
- **Issue:** User-supplied URL fetched internally
- **Fix:**
  - Isolate fetching in network
  - Validate all URLs
  - Disable HTTP redirects
  - URL allowlist
  - Use a maintained URL parser
  - WAF SSRF rules

The SSRF is contained.

## The "security misconfig" pattern (API8)

For misconfig:
- **Issue:** Default configs, exposed debug, CORS
  wrong
- **Fix:**
  - Disable debug in prod
  - Strict CORS allowlist
  - No default credentials
  - Minimal permissions
  - Security headers

The config is locked down.

## The "inventory" pattern (API9)

For inventory:
- **Issue:** Old API versions in prod, no docs
- **Fix:**
  - API registry (e.g., Apigee, Kong, Cloudflare API Shield)
  - Versioned docs (OpenAPI)
  - Track all endpoints
  - Deprecate explicitly
  - Audit logs

The inventory is tracked.

## The "unsafe consumption" pattern (API10)

For unsafe consumption:
- **Issue:** Trust 3rd-party API blindly
- **Fix:**
  - Evaluate provider posture
  - Validate all responses
  - Allowlist redirects
  - Timeouts
  - Limit resources
  - Zero trust

The 3rd-party is not trusted.

## The "OWASP API checklist" pattern

For a checklist:
- [ ] BOLA check on every object endpoint
- [ ] MFA + lockout on auth
- [ ] DTO + schema allowlist
- [ ] Rate limit + size limit
- [ ] Role-based access
- [ ] CAPTCHA on sensitive flows
- [ ] SSRF: URL allowlist, no redirects
- [ ] CORS allowlist, no debug in prod
- [ ] API registry + OpenAPI docs
- [ ] 3rd-party validation + zero trust

The checklist is comprehensive.

## The "API1: BOLA detection" pattern

For BOLA detection:
- **Test:** Try to access other user's data
- **Tools:** Burp Suite, OWASP ZAP
- **Pattern:** Random ID fuzzing
- **Fix:** 100% of object endpoints checked

The BOLA is tested.

## The "API4: rate limit" pattern

For rate limit:
```typescript
// Token bucket per user
const limit = new TokenBucket({
  userId: ctx.user.id,
  capacity: 100,        // 100 requests
  refillRate: 10 / 60,  // 10 per minute
});
if (!limit.tryConsume()) {
  return new Response("Too Many Requests", { status: 429 });
}
```

The limit is per user.

## The "API6: CAPTCHA" pattern

For sensitive flows:
- **Use:** Cloudflare Turnstile
- **Trigger:** After N attempts
- **Verify:** Server-side
- **Fallback:** Manual review

The flow is gated.

## The "API7: SSRF allowlist" pattern

For SSRF allowlist:
```typescript
const ALLOWED_HOSTS = new Set([
  "api.trusted-partner.com",
  "cdn.example.com",
]);

const url = new URL(input.url);
if (!ALLOWED_HOSTS.has(url.hostname)) {
  throw new Error("URL not allowed");
}

const response = await fetch(url, {
  redirect: "manual",  // Don't follow redirects
  signal: AbortSignal.timeout(5000),
});
```

The URL is allowlisted.

## The "API8: CORS" pattern

For CORS:
- **Whitelist:** Specific origins
- **No wildcards:** For credentials
- **Preflight:** Cached
- **Headers:** Only needed

The CORS is locked.

## The "API10: 3rd-party trust" pattern

For 3rd-party:
- **Evaluate:** Security posture (SOC 2, ISO 27001)
- **Validate:** All responses
- **Zero trust:** Treat as untrusted
- **Monitor:** Continuous

The trust is conditional.

## The "OWASP API + OWASP Web" comparison

| OWASP API | OWASP Web (2021) |
|---|---|
| API1: BOLA | A01: Broken Access Control |
| API2: Broken Auth | A07: Auth Failures |
| API3: BOPLA | A03: Injection (data) |
| API4: Resource Consumption | A05: Misconfig |
| API5: BFLA | A01: Broken Access Control |
| API6: Sensitive Flows | (new) |
| API7: SSRF | A10: SSRF |
| API8: Misconfig | A05: Misconfig |
| API9: Inventory | (new) |
| API10: Unsafe Consumption | A06: Vuln Components |

The mapping is partial.

## Verification
- **Test:** All 10 categories tested
- **Tool:** OWASP ZAP, Burp Suite
- **Audit:** Quarterly
- **Live:** Monitor BOLA attempts

## Gotchas
- **The "BOLA" anti-pattern.** Check every endpoint.
- **The "no rate limit" anti-pattern.** Always limit.
- **The "trust 3rd-party" anti-pattern.** Zero trust.

## Related
- `security/owasp-top-10-2025.md`
- `security/csrf-deep-dive.md`
- `security/xss-deep-dive.md`
- `security/sql-injection-deep-dive.md`
- `security/security-headers-deep-dive.md`
- OWASP API: https://owasp.org/www-project-api-security/
- OWASP API Top 10: https://owasp.org/API-Security/
