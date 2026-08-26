# Workers mTLS Client Certificate Authentication

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to expose a Worker endpoint that only accepts requests from trusted clients (IoT devices, internal services, partner APIs) that present a valid TLS client certificate. Unauthenticated or impersonating callers must receive an immediate 403 before any business logic runs.

## Context

- Runtime: Cloudflare Workers (ES modules)
- mTLS termination: handled by Cloudflare edge — certificate details forwarded via `cf.tlsClientAuth`
- Certificate pinning: optional leaf-fingerprint check for extra assurance
- No external library required; all data arrives in the `cf` object on the incoming `Request`

---

## Section 1 — Understanding `cf.tlsClientAuth`

When mTLS is enabled on a zone, Cloudflare populates `request.cf.tlsClientAuth` with the following fields:

```typescript
interface TlsClientAuth {
  certPresented: '0' | '1';       // '1' when a cert was sent
  certVerified: string;            // 'SUCCESS' | 'FAILED:reason'
  certRevoked: '0' | '1';         // '1' when cert is on CRL
  certIssuerDN: string;            // Distinguished Name of the issuer CA
  certSubjectDN: string;           // Distinguished Name of the subject
  certIssuerDNRFC2253: string;
  certSubjectDNRFC2253: string;
  certNotBefore: string;           // 'Dec 10 00:00:00 2024 GMT'
  certNotAfter: string;
  certSerial: string;              // hex serial number
  certFingerprintSHA1: string;     // hex SHA-1 fingerprint
  certFingerprintSHA256: string;   // hex SHA-256 fingerprint (prefer this)
  certChain: string;               // PEM chain (if forwarded)
}
```

These fields are only populated when Cloudflare's **mTLS edge termination** is active for the hostname. Configure it in the Cloudflare dashboard under SSL/TLS → Client Certificates, or via the API.

---

## Section 2 — Basic mTLS Guard Middleware

```typescript
// src/mtls-guard.ts
export interface Env {
  // Optional: KV or D1 to look up allowed fingerprints dynamically
  ALLOWED_FINGERPRINTS?: string; // comma-separated SHA-256 list (secret/var)
}

/**
 * Returns a 403 Response if the client cert is absent, invalid, or revoked.
 * Returns null when the request is allowed to proceed.
 */
export function enforceMtls(
  request: Request,
  env: Env
): Response | null {
  const tls = (request.cf as any)?.tlsClientAuth;

  if (!tls) {
    // Not an mTLS-enabled hostname, or running locally — skip in dev
    if ((request.cf as any)?.httpProtocol === undefined) return null;
    return new Response('mTLS required', { status: 403 });
  }

  if (tls.certPresented !== '1') {
    return new Response('Client certificate not presented', { status: 403 });
  }

  if (tls.certVerified !== 'SUCCESS') {
    return new Response(
      `Client certificate verification failed: ${tls.certVerified}`,
      { status: 403 }
    );
  }

  if (tls.certRevoked === '1') {
    return new Response('Client certificate revoked', { status: 403 });
  }

  return null; // cert is valid
}
```

---

## Section 3 — Leaf Certificate Fingerprint Pinning

For high-security scenarios, validate the SHA-256 fingerprint of the leaf cert against an allowlist.

```typescript
// src/fingerprint-pin.ts

/**
 * Accepts a comma-separated list of allowed SHA-256 fingerprints.
 * Each fingerprint is the hex-encoded SHA-256 of the DER-encoded cert.
 *
 * Obtain a fingerprint:
 *   openssl x509 -in client.crt -noout -fingerprint -sha256
 *   (strip colons → lowercase hex)
 */
export function pinLeafFingerprint(
  request: Request,
  allowedFingerprints: string[]
): Response | null {
  const tls = (request.cf as any)?.tlsClientAuth;
  if (!tls?.certFingerprintSHA256) {
    return new Response('No certificate fingerprint available', { status: 403 });
  }

  const presented = tls.certFingerprintSHA256.toLowerCase().replace(/:/g, '');
  const normalized = allowedFingerprints.map(f =>
    f.toLowerCase().replace(/:/g, '')
  );

  if (!normalized.includes(presented)) {
    console.error(
      `[mtls] Rejected fingerprint: ${presented}. ` +
      `Allowed: ${normalized.join(', ')}`
    );
    return new Response('Certificate not in allowlist', { status: 403 });
  }

  return null; // pinned cert accepted
}
```

---

## Section 4 — Full Worker Entry Point

```typescript
// src/index.ts
import { enforceMtls } from './mtls-guard';
import { pinLeafFingerprint } from './fingerprint-pin';

export interface Env {
  ALLOWED_FINGERPRINTS: string; // set via wrangler secret
  REQUIRE_PIN: string;           // 'true' | 'false'
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Step 1: basic mTLS validation
    const mtlsError = enforceMtls(request, env);
    if (mtlsError) return mtlsError;

    // Step 2: optional fingerprint pinning
    if (env.REQUIRE_PIN === 'true') {
      const pins = env.ALLOWED_FINGERPRINTS.split(',').map(s => s.trim());
      const pinError = pinLeafFingerprint(request, pins);
      if (pinError) return pinError;
    }

    // Step 3: expose cert metadata to downstream handlers
    const tls = (request.cf as any)?.tlsClientAuth;
    const clientId = tls?.certSubjectDN ?? 'unknown';
    console.log(`[mtls] Authenticated client: ${clientId}`);

    const url = new URL(request.url);
    return new Response(
      JSON.stringify({ ok: true, client: clientId, path: url.pathname }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  },
};
```

---

## Section 5 — wrangler.toml Configuration

```toml
# wrangler.toml
name = "mtls-api"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[vars]
REQUIRE_PIN = "true"

# ALLOWED_FINGERPRINTS is a secret — do not put it in wrangler.toml
# Set with: wrangler secret put ALLOWED_FINGERPRINTS
```

Upload your CA certificate in the dashboard (SSL/TLS → Client Certificates → Upload Certificate Authority).

---

## Anti-patterns

- Checking only `certPresented` without also checking `certVerified` — a cert can be presented but invalid.
- Storing fingerprints in `[vars]` — use `wrangler secret put` so they are encrypted at rest.
- Using SHA-1 fingerprints for pinning — SHA-256 only.
- Skipping the revoked check — a compromised cert on a CRL is not automatically blocked unless you check `certRevoked`.
- Assuming `cf.tlsClientAuth` is always present in unit tests — mock it explicitly.

## Gotchas

- `certFingerprintSHA256` from Cloudflare uses colon-separated uppercase hex; normalize before comparing.
- mTLS must be enabled per-hostname in the Cloudflare dashboard; it is not on by default.
- `certChain` is only populated if you enable "Send Client Certificate Chain" in the mTLS settings.
- During local `wrangler dev`, `request.cf` is a stub and `tlsClientAuth` will be absent; guard your dev path.
- Certificate rotation requires updating `ALLOWED_FINGERPRINTS` before the old cert expires.

## Verification

```bash
# Generate a self-signed test client cert
openssl req -x509 -newkey rsa:2048 -keyout client.key -out client.crt \
  -days 365 -nodes -subj "/CN=test-client/O=orchords"

# Get the SHA-256 fingerprint (strip colons, lowercase)
openssl x509 -in client.crt -noout -fingerprint -sha256 \
  | awk -F= '{print $2}' | tr -d ':' | tr '[:upper:]' '[:lower:]'

# Test with client cert
curl --cert client.crt --key client.key https://api.example.com/secure

# Test without client cert (should get 403)
curl https://api.example.com/secure

# Verify the Worker sees the right cert fields
curl --cert client.crt --key client.key \
  https://api.example.com/secure | jq .
```

## Related

- `documentation/docs/policies/cloudflare/workers-smart-placement-auto-performance.md`
- `documentation/docs/policies/cloudflare/workers-d1-alarms-scheduled-mutations.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/ssl/client-certificates/
- https://developers.cloudflare.com/api-shield/security/mtls/
