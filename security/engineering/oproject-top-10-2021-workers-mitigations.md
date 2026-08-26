# OWASP Top 10 2021 — Cloudflare Workers Mitigations

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your team is conducting a security review of a Cloudflare Workers-based API or full-stack application and needs a structured mapping of the OWASP Top 10 2021 risks to Workers-specific controls. The Workers execution model (isolate-per-request, no persistent memory, limited OS surface) changes which risks are most critical and how mitigations are implemented compared to traditional server-side frameworks.

This article maps every A01–A10 category to the Workers context: where the risk is reduced by the platform, where it remains, and what code or configuration closes the gap.

## Context

The OWASP Top 10 2021 list is the most widely cited web application security standard. It represents the ten most prevalent and impactful web application security risks, derived from data contributed by hundreds of organisations. The 2021 edition introduced three new categories (A04, A08, A10) and significantly repositioned access control (up from A05 to A01) reflecting the frequency of IDOR and privilege escalation findings.

Cloudflare Workers' security properties that affect this mapping:
- **No persistent process memory**: Secrets cannot be left in memory across requests by accident. Each isolate is cold-started per-Worker-version deployment.
- **No file system**: Path traversal, file inclusion, and file-write vulnerabilities are structurally impossible.
- **No shell**: OS command injection (A03 subset) is not possible.
- **Outbound fetch only**: Network-layer SSRF is constrained by Workers' outbound fetch model.
- **V8 isolates**: Each request runs in a V8 isolate; traditional memory corruption exploits (buffer overflow, use-after-free) are not possible in JavaScript/TypeScript.

## A01: Broken Access Control

**Risk**: Functions execute at the wrong privilege level; users access other users' data (IDOR); missing function-level authorization checks; CORS misconfiguration.

**Workers-specific exposure**: High. Access control logic lives entirely in your Worker code. The platform provides no built-in RBAC. Every request arrives with user-supplied headers and cookies that must be validated.

**Mitigations**:

```typescript
// Enforce ownership before returning any resource
async function getItem(request: Request, env: Env): Promise<Response> {
  const userId = await validateJwt(request, env);          // A07 mitigation
  if (!userId) return Response.json({ error: 'unauthorized' }, { status: 401 });

  const { id } = getPathParams(request);                   // e.g., /api/items/:id

  const item = await env.DB
    .prepare('SELECT * FROM items WHERE id = ? AND owner_id = ?')
    .bind(id, userId)                                      // bind owner_id — IDOR prevention
    .first();

  if (!item) return Response.json({ error: 'not_found' }, { status: 404 }); // don't 403 — leaks existence
  return Response.json(item);
}
```

CORS must not use wildcard with credentials. See `cors-cloudflare-workers-mobile-preflight.md` for the full pattern.

**Platform reduction**: Low. Entirely code-dependent.

---

## A02: Cryptographic Failures

**Risk**: Sensitive data transmitted without encryption; weak or deprecated algorithms (MD5, SHA-1, RC4, DES); hardcoded secrets; improper certificate validation; insufficient key length.

**Workers-specific exposure**: Medium. Workers runs entirely over TLS (Cloudflare terminates TLS; plain HTTP is impossible to serve from Workers without a redirect). However, you can still use weak algorithms via the Web Crypto API or third-party libraries.

**Mitigations**:

```typescript
// WRONG — MD5 is not available in Web Crypto; but SHA-1 is and must be avoided
const digest = await crypto.subtle.digest('SHA-1', data);   // ❌ deprecated

// CORRECT — use SHA-256 minimum for integrity; use AES-GCM for encryption
const digest = await crypto.subtle.digest('SHA-256', data); // ✅

// Password hashing — use Argon2 via a WASM module, not native crypto
// (Workers does not have bcrypt or scrypt built in)
import { hash, verify } from '@node-rs/argon2';  // WASM-compatible build

// NEVER store secrets in wrangler.toml — use wrangler secret put
// NEVER log secrets — strip Authorization headers before logging
```

**Platform reduction**: Medium. TLS is enforced automatically. Weak crypto choices in code are still possible.

---

## A03: Injection

**Risk**: SQL injection, NoSQL injection, LDAP injection, OS command injection, template injection, SSTI.

**Workers-specific exposure**: Partial. SQL injection into D1 remains possible. OS command injection is impossible (no shell). Template injection depends on your templating library.

**Mitigations**:

```typescript
// D1 — ALWAYS use parameterised statements
// ❌ WRONG
const result = await env.DB.prepare(`SELECT * FROM users WHERE email = '${email}'`).all();

// ✅ CORRECT
const result = await env.DB
  .prepare('SELECT * FROM users WHERE email = ?')
  .bind(email)
  .all();

// Template injection — escape user content before inserting into HTML
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

// AI prompt injection — sanitise user input before inserting into LLM prompts
function buildPrompt(userInput: string): string {
  const sanitised = userInput
    .slice(0, 500)                              // length limit
    .replace(/[<>{}[\]]/g, '')                 // strip structural chars
    .trim();
  return `Answer only about our products. User asked: ${sanitised}`;
}
```

**Platform reduction**: High for OS command injection (impossible). Low for SQL and template injection.

---

## A04: Insecure Design

**Risk**: Missing security controls at the design stage; absence of threat modelling; business logic flaws; no rate limiting by design; trust boundaries not defined.

**Workers-specific exposure**: High. Insecure design is framework-agnostic — it's a process risk, not a code risk.

**Mitigations**:

```
Checklist for every new Workers route:
□ Threat model completed (STRIDE per data flow)
□ Authentication required? JWT / API key / session cookie validation added
□ Authorization required? Owner check on every resource fetch
□ Rate limiting applied? (Cloudflare v2 rule + Workers RateLimiter binding)
□ Input validated and size-bounded?
□ Secrets accessed only from env, never from request headers or query params
□ Sensitive response fields stripped for non-owner callers?
□ Audit log entry written for mutating operations?
```

Design-time controls that Workers' architecture uniquely enables:
- **Isolate boundary**: Each Worker is a separate trust boundary — split high-privilege operations (token issuance, admin APIs) into separate Workers with separate KV namespace bindings.
- **Service bindings**: Use Cloudflare Service Bindings for internal Worker-to-Worker calls instead of public HTTP. Traffic never leaves Cloudflare's network and cannot be intercepted.

**Platform reduction**: None. Design risk is entirely human-process.

---

## A05: Security Misconfiguration

**Risk**: Default credentials left enabled; unnecessary features enabled; missing security headers; verbose error messages revealing stack traces; open cloud storage buckets.

**Workers-specific exposure**: High. Security headers must be explicitly set; R2 buckets can be misconfigured as public; environment variables can be logged accidentally.

**Mitigations**:

```typescript
// Security headers middleware — wrap every response
function addSecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
  headers.set('X-Content-Type-Options',    'nosniff');
  headers.set('X-Frame-Options',           'DENY');
  headers.set('Referrer-Policy',           'strict-origin-when-cross-origin');
  headers.set('Permissions-Policy',        'camera=(), microphone=(), geolocation=()');
  headers.set('Content-Security-Policy',
    "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'");
  return new Response(response.body, { status: response.status, headers });
}

// Never expose stack traces to clients
try {
  return await businessLogic(request, env);
} catch (err) {
  // Log internally (to a logging Worker or R2), not to the response body
  console.error('[Worker error]', err instanceof Error ? err.message : String(err));
  return Response.json({ error: 'internal_server_error' }, { status: 500 });
}
```

R2 bucket access control: by default, R2 buckets are private. Do not bind an R2 bucket without an access check in the Worker that serves it.

**Platform reduction**: Medium. Workers has no "default credentials" concept, but header omission and verbose errors are code-level risks.

---

## A06: Vulnerable and Outdated Components

**Risk**: Using libraries with known CVEs; not tracking transitive dependencies; no SBOM; running outdated runtime versions.

**Workers-specific exposure**: High for npm dependencies bundled into your Worker. The Workers runtime itself is maintained by Cloudflare and automatically updated.

**Mitigations**:

```bash
# Audit direct and transitive dependencies
npm audit --production

# Generate an SBOM for your Worker bundle
npx @cyclonedx/cyclonedx-npm --output-format json --output-file sbom.json

# Pin the Workers compatibility date in wrangler.toml
# This controls which runtime APIs are available — keep it within 90 days of today
compatibility_date = "2026-07-01"

# Run Dependabot or Renovate on your Workers repo
# .github/dependabot.yml example:
# version: 2
# updates:
#   - package-ecosystem: "npm"
#     directory: "/"
#     schedule:
#       interval: "weekly"
#     open-pull-requests-limit: 10
```

Check `sbom-vulnerability-scanning.md` for the full pipeline with `grype` and Trivy.

**Platform reduction**: Medium. Runtime CVEs are Cloudflare's responsibility. Dependency CVEs are yours.

---

## A07: Identification and Authentication Failures

**Risk**: Weak passwords allowed; credential stuffing not mitigated; insecure session management; missing MFA; JWT algorithm confusion; account enumeration.

**Workers-specific exposure**: High. Session storage in KV must be implemented correctly. JWT validation is code-level. Workers has no built-in authentication layer.

**Mitigations**:

```typescript
// JWT validation — always verify algorithm explicitly
async function validateJwt(request: Request, env: Env): Promise<string | null> {
  const auth = request.headers.get('Authorization');
  if (!auth?.startsWith('Bearer ')) return null;

  const token = auth.slice(7);
  const [headerB64, payloadB64, sigB64] = token.split('.');
  if (!headerB64 || !payloadB64 || !sigB64) return null;

  const header = JSON.parse(atob(headerB64));

  // Reject 'none' algorithm and RS256 if you only use HS256
  if (header.alg !== 'EdDSA') return null;  // whitelist a single algorithm

  // ... verify signature with env.JWT_PUBLIC_KEY (see jwt-best-practices.md)
  const payload = JSON.parse(atob(payloadB64));
  if (payload.exp < Math.floor(Date.now() / 1000)) return null;

  return payload.sub;
}

// Prevent account enumeration on login
// Return the same error and take the same time whether username or password is wrong
async function login(username: string, password: string, env: Env): Promise<boolean> {
  const user = await env.DB
    .prepare('SELECT password_hash FROM users WHERE username = ?')
    .bind(username)
    .first<{ password_hash: string }>();

  // Always run the hash comparison — even for non-existent users — to prevent timing attacks
  const dummyHash = '$argon2id$v=19$m=65536,t=3,p=4$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
  const hash = user?.password_hash ?? dummyHash;
  const valid = await verifyArgon2(hash, password);

  return !!user && valid;
}
```

**Platform reduction**: Low. Auth is entirely code-dependent.

---

## A08: Software and Data Integrity Failures

**Risk**: Insecure deserialization; CI/CD pipeline compromise; untrusted auto-updates; unsigned software components; dependency confusion attacks.

**Workers-specific exposure**: Medium. Workers is deployed via Wrangler CLI or the Cloudflare API. CI/CD pipeline integrity is critical because a compromised pipeline can push malicious Worker code to production.

**Mitigations**:

```yaml
# .github/workflows/deploy.yml — sign and verify the Worker bundle before deployment
- name: Generate bundle hash
  run: |
    wrangler deploy --dry-run --outdir dist/
    sha256sum dist/index.js | tee bundle.sha256

- name: Sign bundle hash
  run: |
    echo "$SIGNING_PRIVATE_KEY" | gpg --import
    gpg --detach-sign --armor bundle.sha256

- name: Verify signature before deploy
  run: gpg --verify bundle.sha256.asc bundle.sha256

- name: Deploy Worker
  run: wrangler deploy
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

For deserialization: Workers commonly deserialize JSON from KV, D1, or request bodies. Always validate the schema of deserialized data before trusting it:

```typescript
import { z } from 'zod';

const UserSchema = z.object({
  id:    z.string().uuid(),
  email: z.string().email().max(254),
  role:  z.enum(['user', 'admin']),
});

const raw = JSON.parse(await env.KV.get(`user:${userId}`) ?? '{}');
const user = UserSchema.parse(raw);  // throws ZodError on invalid data
```

**Platform reduction**: Low for CI/CD (your pipeline). High for runtime deserialization (type-safe JS helps).

---

## A09: Security Logging and Monitoring Failures

**Risk**: Insufficient logging of security events; no alerting on suspicious activity; logs not protected from tampering; log injection.

**Workers-specific exposure**: High. Workers' `console.log` output goes to Cloudflare's Workers Logs (Logpush), which must be explicitly configured. By default, production Workers discard `console` output.

**Mitigations**:

```typescript
// Structured security event logging
interface SecurityEvent {
  type:       'auth_failure' | 'rate_limited' | 'input_rejected' | 'acl_violation';
  userId?:    string;
  ip:         string;
  path:       string;
  timestamp:  string;
  details:    string;
}

async function logSecurityEvent(event: SecurityEvent, env: Env): Promise<void> {
  // Prevent log injection — strip newlines from all string fields
  const safe: SecurityEvent = {
    ...event,
    details: event.details.replace(/[\r\n]/g, ' ').slice(0, 500),
    userId:  event.userId?.replace(/[\r\n]/g, ''),
  };

  // Write to an R2 bucket for tamper-evident storage
  const key = `logs/${safe.timestamp.slice(0, 10)}/${crypto.randomUUID()}.json`;
  await env.AUDIT_LOGS.put(key, JSON.stringify(safe));

  // Also emit to console for Logpush → SIEM integration
  console.log(JSON.stringify(safe));
}
```

Configure Logpush (in `wrangler.toml` or Terraform) to forward logs to your SIEM:

```toml
# wrangler.toml (requires Cloudflare Logpush configuration via API)
[logpush]
enabled = true
```

**Platform reduction**: Low. Logging infrastructure must be deliberately configured.

---

## A10: Server-Side Request Forgery (SSRF)

**Risk**: User-controlled URLs passed to `fetch()`; metadata endpoint access (`169.254.169.254`); internal service enumeration; DNS rebinding.

**Workers-specific exposure**: Reduced but present. Workers runs in Cloudflare's network; there is no EC2 metadata endpoint at `169.254.169.254`. However, Workers can still be directed to fetch internal Cloudflare services or internal infrastructure accessible from the edge network.

**Mitigations**:

```typescript
import { URL } from 'url';

const ALLOWED_FETCH_HOSTS = new Set([
  'api.github.com',
  'hooks.stripe.com',
]);

async function safeFetch(userSuppliedUrl: string): Promise<Response> {
  let parsed: URL;
  try {
    parsed = new URL(userSuppliedUrl);
  } catch {
    throw new Error('Invalid URL');
  }

  // Only allow HTTPS
  if (parsed.protocol !== 'https:') {
    throw new Error('Only HTTPS URLs are allowed');
  }

  // Block private and link-local IP ranges
  const host = parsed.hostname;
  if (
    host === 'localhost' ||
    host === '127.0.0.1' ||
    host.startsWith('169.254.') ||         // link-local
    host.startsWith('10.')  ||             // RFC 1918
    host.startsWith('192.168.') ||         // RFC 1918
    /^172\.(1[6-9]|2\d|3[01])\./.test(host) // 172.16–31
  ) {
    throw new Error('Private IP addresses are not allowed');
  }

  // Allowlist — only fetch from known-good hosts
  if (!ALLOWED_FETCH_HOSTS.has(host)) {
    throw new Error(`Host ${host} is not in the allowed list`);
  }

  return fetch(parsed.toString(), { redirect: 'error' }); // disable redirect-following
}
```

See `ssrf-url-fetch-guard.md` and `outbound-url-policy-ssrf-and-dns-rebinding-resistance.md` for the full DNS rebinding mitigation.

**Platform reduction**: Medium. The metadata endpoint attack surface is absent. DNS rebinding and internal service enumeration remain possible.

---

## Verification Checklist

Run this checklist before every production deployment:

```
Security Review Checklist — OWASP Top 10 2021

A01 Access Control
  □ Every route enforces authentication before accessing data
  □ Resource fetches bind owner_id in D1 query (IDOR prevention)
  □ CORS allowlist is explicit, not wildcard-with-credentials

A02 Cryptographic Failures
  □ No MD5, SHA-1, DES, RC4 in production code (grep check)
  □ Secrets via wrangler secret put, not wrangler.toml
  □ Passwords hashed with Argon2, not SHA-256

A03 Injection
  □ All D1 queries use parameterised binding (.bind())
  □ HTML output escapes user content
  □ AI prompts sanitise and length-limit user input

A04 Insecure Design
  □ Threat model reviewed for new routes
  □ Rate limiting rule or Workers RateLimiter binding applied

A05 Security Misconfiguration
  □ Security headers middleware applied (CSP, HSTS, X-Frame-Options)
  □ Errors return generic messages, not stack traces

A06 Vulnerable Components
  □ npm audit passes (no critical/high CVEs)
  □ compatibility_date within 90 days

A07 Authentication Failures
  □ JWT algorithm explicitly whitelisted
  □ Token expiry checked
  □ Account enumeration timing mitigated

A08 Software Integrity
  □ CI/CD pipeline deploys only signed, reviewed code
  □ Incoming JSON validated with Zod schema before use

A09 Logging and Monitoring
  □ Auth failures logged with user IP and path
  □ Logpush configured to forward to SIEM
  □ Log injection prevented (newline stripping)

A10 SSRF
  □ User-supplied URLs validated against allowlist
  □ Private IP ranges blocked before fetch()
  □ redirect: 'error' set on all outbound fetches
```

## Related

- `owasp-api-top-10-2023.md` — API-specific risks beyond the web application top 10
- `owasp-asvs-5-control-baseline.md` — ASVS verification standard mapped to Workers
- `sql-injection-prevention-d1-workers.md` — parameterised D1 queries in depth
- `ssrf-url-fetch-guard.md` — full SSRF prevention implementation
- `jwt-best-practices.md` — A07 JWT validation patterns
- `security-headers-comprehensive.md` — A05 full header set with CSP
- `sbom-vulnerability-scanning.md` — A06 dependency tracking pipeline

## Sources

- OWASP Top 10 2021 — owasp.org/Top10
- Cloudflare Workers Runtime API Documentation — developers.cloudflare.com/workers
- OWASP Application Security Verification Standard 4.0
- NIST SP 800-53 Rev 5 — Security and Privacy Controls for Information Systems
- CWE Top 25 Most Dangerous Software Weaknesses 2024 — cwe.mitre.org/top25
