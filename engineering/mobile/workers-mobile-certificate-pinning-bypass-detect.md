# Detecting Certificate Pinning Bypass Attempts in Workers Mobile API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Attackers use tools like Frida or Charles Proxy to bypass your mobile app's certificate pinning, intercept API traffic, and reverse-engineer your mobile API. A Cloudflare Worker can enforce Mutual TLS (mTLS) by validating client certificate fingerprints against a KV allowlist and logging all rejected requests to D1 for incident analysis.

---

## Context
Cloudflare's mTLS feature allows you to require client certificates on specific Workers routes. When a request arrives, the `cf.tlsClientAuth` object on the `request.cf` property contains the client certificate's fingerprint and validity status. Storing approved fingerprints in KV gives you instant rotation without redeployment: add a new fingerprint before rotating the certificate, then remove the old one after the rollout completes. D1 stores rejected request metadata — IP, UA, timestamp, presented fingerprint — for security review and alerting. This pattern complements, but does not replace, server-side JWT validation.

---

## Setup / Config

```toml
# wrangler.toml
name = "mobile-api-secure"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "CERT_ALLOWLIST"
id = "<your-kv-namespace-id>"

[[d1_databases]]
binding = "DB"
database_name = "security-log"
database_id = "<your-d1-database-id>"

# mTLS is configured in the Cloudflare dashboard under SSL/TLS > Client Certificates
# and applied to routes via a WAF custom rule or Workers route.
```

Seed initial allowlist:

```bash
# SHA-256 fingerprint of your app's pinned certificate (colon-separated uppercase hex)
FINGERPRINT="AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"

npx wrangler kv key put \
  --namespace-id <id> \
  "cert:${FINGERPRINT}" \
  "{\"addedAt\":$(date +%s),\"label\":\"ios-release-v3.2\"}"
```

Create D1 rejection log table:

```bash
npx wrangler d1 execute security-log --command "
  CREATE TABLE IF NOT EXISTS rejected_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    ip TEXT,
    ua TEXT,
    presented_fingerprint TEXT,
    path TEXT,
    method TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_rr_ts ON rejected_requests (ts);
  CREATE INDEX IF NOT EXISTS idx_rr_fp ON rejected_requests (presented_fingerprint);
"
```

---

## Implementation — Worker

```typescript
// src/index.ts
export interface Env {
  CERT_ALLOWLIST: KVNamespace;
  DB: D1Database;
}

interface TlsClientAuth {
  certFingerprintSHA256?: string;
  certVerified?: string; // "SUCCESS" when Cloudflare verified the cert against your CA
  certIssuerDN?: string;
  certSubjectDN?: string;
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function logRejection(
  db: D1Database,
  ctx: ExecutionContext,
  opts: {
    ip: string;
    ua: string;
    fingerprint: string;
    path: string;
    method: string;
  }
): Promise<void> {
  ctx.waitUntil(
    db
      .prepare(
        'INSERT INTO rejected_requests (ts, ip, ua, presented_fingerprint, path, method) VALUES (?, ?, ?, ?, ?, ?)'
      )
      .bind(Date.now(), opts.ip, opts.ua, opts.fingerprint, opts.path, opts.method)
      .run()
  );
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cf = request.cf as (Record<string, unknown> & { tlsClientAuth?: TlsClientAuth }) | undefined;
    const tls = cf?.tlsClientAuth;

    const ip = request.headers.get('CF-Connecting-IP') ?? '';
    const ua = request.headers.get('User-Agent') ?? '';
    const url = new URL(request.url);

    // ── Step 1: Require that Cloudflare verified the cert against our CA ──
    if (!tls || tls.certVerified !== 'SUCCESS') {
      await logRejection(env.DB, ctx, {
        ip,
        ua,
        fingerprint: tls?.certFingerprintSHA256 ?? 'none',
        path: url.pathname,
        method: request.method,
      });
      return json(
        { error: 'Client certificate required', code: 'CERT_MISSING' },
        403
      );
    }

    // ── Step 2: Check fingerprint against KV allowlist ────────────────
    const fingerprint = tls.certFingerprintSHA256 ?? '';
    // KV key format: "cert:<FINGERPRINT>"
    const entry = await env.CERT_ALLOWLIST.get(`cert:${fingerprint}`);

    if (!entry) {
      await logRejection(env.DB, ctx, {
        ip,
        ua,
        fingerprint,
        path: url.pathname,
        method: request.method,
      });
      return json(
        { error: 'Certificate not in allowlist', code: 'CERT_REJECTED' },
        403
      );
    }

    // ── Step 3: Forward to your actual API handler ────────────────────
    // Attach verified fingerprint as a header for downstream handlers
    const proxied = new Request(request, {
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        'X-Client-Cert-Fingerprint': fingerprint,
        'X-Client-Cert-Subject': tls.certSubjectDN ?? '',
      }),
    });

    // Replace with your actual business logic or fetch to an origin
    return json({
      status: 'ok',
      message: 'Certificate validated',
      fingerprint,
    });
  },
};
```

---

## Integration / Testing — Allowlist Rotation Procedure

```bash
# ── Rotation procedure ─────────────────────────────────────────────────
# 1. Generate new certificate and extract fingerprint
openssl req -x509 -newkey rsa:4096 -keyout client-new.key -out client-new.crt \
  -days 365 -nodes -subj "/CN=orchords-mobile"

NEW_FP=$(openssl x509 -in client-new.crt -noout -fingerprint -sha256 \
  | sed 's/SHA256 Fingerprint=//' | tr '[:lower:]' '[:upper:]')

# 2. Add new fingerprint to allowlist BEFORE rolling out new app build
npx wrangler kv key put --namespace-id <id> \
  "cert:${NEW_FP}" \
  "{\"addedAt\":$(date +%s),\"label\":\"ios-release-v3.3\"}"

# 3. Roll out new app binary (both old and new fingerprints are active)
# 4. After rollout is ≥ 95% complete, remove old fingerprint
OLD_FP="AA:BB:CC:..."
npx wrangler kv key delete --namespace-id <id> "cert:${OLD_FP}"

# ── Test with curl ─────────────────────────────────────────────────────
# Accepted request
curl --cert client-new.crt --key client-new.key \
  https://mobile-api-secure.<subdomain>.workers.dev/health

# Rejected request (no cert)
curl https://mobile-api-secure.<subdomain>.workers.dev/health
# Expected: {"error":"Client certificate required","code":"CERT_MISSING"}

# Rejected request (unknown cert)
openssl req -x509 -newkey rsa:2048 -keyout rogue.key -out rogue.crt -days 1 -nodes
curl --cert rogue.crt --key rogue.key \
  https://mobile-api-secure.<subdomain>.workers.dev/health
# Expected: {"error":"Certificate not in allowlist","code":"CERT_REJECTED"}
```

---

## Anti-patterns
- **Checking only `certVerified` without a fingerprint allowlist** — any certificate signed by your CA passes `certVerified`; compromised certs stay valid until revocation propagates.
- **Blocking the response on D1 logging** — always use `ctx.waitUntil()` for security logging; a slow DB write must not delay the 403 response.
- **Using MD5 or SHA-1 fingerprints** — use SHA-256 only; older hash algorithms are broken for certificate identity.
- **Storing fingerprints in Worker source code** — KV rotation avoids redeployment; hardcoded fingerprints require a code push during a security incident.

---

## Gotchas
- `request.cf` is not available in local `wrangler dev` without `--remote`; test mTLS enforcement with `wrangler dev --remote`.
- Cloudflare mTLS enforcement at the network edge (WAF rule) happens before the Worker receives the request; if the WAF rule is not set, Workers still receives cert-less requests and must enforce via `tlsClientAuth`.
- The `certFingerprintSHA256` value uses uppercase hex with colon separators — normalize consistently when seeding KV.
- iOS `URLSession` certificate pinning and Cloudflare mTLS are complementary: iOS validates the server cert; mTLS validates the client cert.

---

## Verification

```bash
# Query recent rejections from D1
npx wrangler d1 execute security-log --command \
  "SELECT ts, ip, ua, presented_fingerprint, path FROM rejected_requests ORDER BY ts DESC LIMIT 20;"

# Count rejections by fingerprint in the last 24 hours
npx wrangler d1 execute security-log --command "
  SELECT presented_fingerprint, COUNT(*) as attempts
  FROM rejected_requests
  WHERE ts > $(( $(date +%s) - 86400 )) * 1000
  GROUP BY presented_fingerprint
  ORDER BY attempts DESC;
"
```

---

## Related
- `workers-flutter-d1-rest-api.md`
- `workers-mobile-api-versioning-accept-header.md`

---

## Sources
- Cloudflare Mutual TLS — https://developers.cloudflare.com/api-shield/security/mtls/
- Cloudflare Workers request.cf object — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- OWASP Mobile Top 10 — https://owasp.org/www-project-mobile-top-10/
