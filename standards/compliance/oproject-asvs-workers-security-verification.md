# OWASP ASVS Compliance on Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

The example project platform must demonstrate measurable security assurance to enterprise customers and regulators. Without a structured verification framework, security controls are ad hoc and evidence for audits is scattered. OWASP ASVS 4.0 provides a testable, tiered checklist that maps directly to Cloudflare Workers primitives.

## Context

The OWASP Application Security Verification Standard (ASVS) 4.0 defines three assurance levels: L1 (opportunistic), L2 (standard), and L3 (advanced). Anonymous social platforms handling user-generated content and pseudonymous identities are expected to meet L2 at minimum. Cloudflare Workers' edge runtime imposes constraints—no raw filesystem, no long-lived process memory—that map some ASVS controls cleanly and require creative solutions for others. The controls most relevant to example project fall under chapters V2 (Authentication), V3 (Session), V5 (Validation), V8 (Data Protection), and V14 (Configuration).

## V2 / V3 – Authentication and Session Token Controls

ASVS V2.9 requires session tokens to be at least 128 bits of entropy. Workers KV is used as the session store; tokens are generated with `crypto.getRandomValues` and bound to `CF-Connecting-IP` for L2 fixation resistance.

```typescript
// worker/session.ts
export interface SessionPayload {
  userId: string;
  ipHash: string;
  createdAt: number;
  expiresAt: number;
}

const TOKEN_BYTES = 32; // 256 bits – satisfies ASVS V2.9.1

export async function createSession(
  kv: KVNamespace,
  userId: string,
  clientIp: string,
): Promise<string> {
  const raw = crypto.getRandomValues(new Uint8Array(TOKEN_BYTES));
  const token = btoa(String.fromCharCode(...raw))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");

  const ipHash = await hashIp(clientIp);
  const payload: SessionPayload = {
    userId,
    ipHash,
    createdAt: Date.now(),
    expiresAt: Date.now() + 30 * 60 * 1000, // 30-min idle (ASVS V3.3.1)
  };

  await kv.put(`session:${token}`, JSON.stringify(payload), {
    expirationTtl: 1800,
  });
  return token;
}

export async function validateSession(
  kv: KVNamespace,
  token: string,
  clientIp: string,
): Promise<SessionPayload | null> {
  const raw = await kv.get(`session:${token}`, "json");
  if (!raw) return null;

  const session = raw as SessionPayload;
  if (Date.now() > session.expiresAt) {
    await kv.delete(`session:${token}`);
    return null;
  }

  // ASVS V3.4.3 – bind session to origin IP hash
  const ipHash = await hashIp(clientIp);
  if (ipHash !== session.ipHash) return null;

  return session;
}

async function hashIp(ip: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(ip),
  );
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}
```

## V5 – Input Validation and Output Encoding

ASVS V5.1.1 requires all inputs to be validated against a positive allow-list before processing. On Workers, this is enforced at the request boundary using a typed schema validator before any D1 query is executed.

```typescript
// worker/validators.ts
export interface PostInput {
  body: string;
  topicId: string;
}

const MAX_BODY_CHARS = 2000;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function validatePostInput(raw: unknown): PostInput {
  if (typeof raw !== "object" || raw === null) {
    throw new Response("Invalid payload", { status: 400 });
  }
  const { body, topicId } = raw as Record<string, unknown>;

  if (typeof body !== "string" || body.length === 0 || body.length > MAX_BODY_CHARS) {
    throw new Response("body: 1–2000 chars required", { status: 422 });
  }
  if (typeof topicId !== "string" || !UUID_RE.test(topicId)) {
    throw new Response("topicId: valid UUID required", { status: 422 });
  }

  // ASVS V5.2.1 – strip HTML before storage; rendering layer re-escapes
  const sanitisedBody = body
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return { body: sanitisedBody, topicId };
}
```

## V8 – Data Protection Controls

ASVS V8.1.1 requires sensitive data to be identified and classified. V8.3.4 prohibits caching sensitive responses. Workers response headers must explicitly prevent downstream proxy caching of authenticated endpoints.

```typescript
// worker/security-headers.ts
export function applySecurityHeaders(response: Response, isAuthenticated: boolean): Response {
  const headers = new Headers(response.headers);

  // ASVS V14.4.1 – security headers baseline
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  headers.set(
    "Content-Security-Policy",
    "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'",
  );
  headers.set("Permissions-Policy", "geolocation=(), camera=(), microphone=()");

  if (isAuthenticated) {
    // ASVS V8.3.4 – no caching for authenticated content
    headers.set("Cache-Control", "no-store, no-cache, must-revalidate, private");
    headers.set("Pragma", "no-cache");
  } else {
    headers.set("Cache-Control", "public, max-age=60, s-maxage=300");
  }

  // ASVS V14.4.6 – HSTS on all responses
  headers.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload");

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
```

## V9 / V14 – TLS and Dependency Configuration

ASVS V9.1.1 mandates TLS 1.2+ and V14.2.1 requires only actively-maintained components. In `wrangler.toml`, minimum TLS is enforced at the zone level; a CI step checks npm advisories.

```typescript
// scripts/asvs-dep-audit.ts  (runs in CI, not on Workers runtime)
import { execSync } from "node:child_process";

interface AuditResult {
  metadata: { vulnerabilities: { high: number; critical: number } };
}

function runAudit(): void {
  const raw = execSync("npm audit --json", { encoding: "utf8" });
  const result: AuditResult = JSON.parse(raw);
  const { high, critical } = result.metadata.vulnerabilities;
  if (high > 0 || critical > 0) {
    console.error(`ASVS V14.2.1 FAIL – ${critical} critical, ${high} high advisories`);
    process.exit(1);
  }
  console.log("ASVS V14.2.1 PASS – no high/critical advisories");
}

runAudit();
```

## Anti-patterns

- Storing raw session tokens in `Cache-Control: public` responses violates V3.4.1 and exposes tokens to shared CDN caches.
- Using `Math.random()` for token generation fails V2.9.1 (not cryptographically random).
- Skipping output encoding before inserting user content into HTML responses violates V5.3.1 and opens XSS vectors.

## Gotchas

- Workers `crypto.getRandomValues` is synchronous and uses the Web Crypto API; it does not require `node:crypto`. Mixing Node.js crypto polyfills with the built-in can produce subtle compatibility failures in test environments.
- `Cache-Control: no-store` only prevents the Cloudflare edge cache when the response passes through a Worker that sets the header before returning. Responses that bypass the Worker (e.g., direct asset serves from Pages) need their own cache rules.

## Verification

```bash
# Run ASVS-aligned automated checks
npm run test -- --reporter=verbose

# Dependency audit (ASVS V14.2.1)
npm audit --audit-level=high

# Confirm security headers on a live endpoint
curl -si https://example project.example.com/api/health \
  | grep -E "strict-transport|x-content-type|content-security"

# Verify session token entropy (token must decode to >=32 bytes)
TOKEN=$(curl -s -X POST https://example project.example.com/api/session | jq -r .token)
echo -n "$TOKEN" | base64 --decode | wc -c
```

## Related

- `compliance/gdpr-consent-management-cloudflare-workers.md`
- `compliance/nist-800-53-control-families.md`
- `compliance/pci-dss-4.md`

## Sources

- https://owasp.org/www-project-application-security-verification-standard/
- https://github.com/OWASP/ASVS/releases/tag/v4.0.3
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
