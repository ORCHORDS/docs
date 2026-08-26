# Client Certificate mTLS with Cloudflare Workers and Zero Trust

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to authenticate machine-to-machine API clients (IoT devices, internal services, CI/CD pipelines) without API keys that can be accidentally logged or leaked. You want the TLS handshake itself to prove client identity, with the Worker able to inspect the certificate's subject, issuer, and validity before executing business logic. Mutual TLS (mTLS) combined with Cloudflare Zero Trust provides defence-in-depth: unauthenticated connections are rejected at the network edge before touching your Worker.

## Context

Cloudflare mTLS works at two layers. First, Cloudflare Access / Zero Trust terminates the TLS handshake and enforces that the client certificate is signed by a CA you upload. Second, Cloudflare propagates certificate metadata to your Worker in the `cf.tlsClientAuth` object, allowing fine-grained subject/SAN inspection inside business logic. Cloudflare Workers with mTLS require a paid plan and mTLS certificate authorities configured in the Zero Trust dashboard.

## 1. Inspecting Client Certificate Metadata in the Worker

```typescript
// src/mtls.ts
export interface ClientCertInfo {
  verified: boolean;
  certPresented: boolean;
  subject: {
    cn: string | null;
    ou: string | null;
    o: string | null;
    l: string | null;
    st: string | null;
    country: string | null;
    serial: string | null;
  };
  issuer: {
    cn: string | null;
    ou: string | null;
    o: string | null;
  };
  fingerprint: string | null;
  notBefore: string | null;
  notAfter: string | null;
}

export function extractCertInfo(request: Request): ClientCertInfo {
  const cf = (request as any).cf ?? {};
  const tls = cf.tlsClientAuth ?? {};

  return {
    verified: tls.certVerified === "SUCCESS",
    certPresented: tls.certPresented === "1",
    subject: {
      cn: tls.certSubjectDN ? parseDNField(tls.certSubjectDN, "CN") : null,
      ou: tls.certSubjectDN ? parseDNField(tls.certSubjectDN, "OU") : null,
      o: tls.certSubjectDN ? parseDNField(tls.certSubjectDN, "O") : null,
      l: tls.certSubjectDN ? parseDNField(tls.certSubjectDN, "L") : null,
      st: tls.certSubjectDN ? parseDNField(tls.certSubjectDN, "ST") : null,
      country: tls.certSubjectDN ? parseDNField(tls.certSubjectDN, "C") : null,
      serial: tls.certSerial ?? null,
    },
    issuer: {
      cn: tls.certIssuerDN ? parseDNField(tls.certIssuerDN, "CN") : null,
      ou: tls.certIssuerDN ? parseDNField(tls.certIssuerDN, "OU") : null,
      o: tls.certIssuerDN ? parseDNField(tls.certIssuerDN, "O") : null,
    },
    fingerprint: tls.certFingerprintSHA256 ?? null,
    notBefore: tls.certNotBefore ?? null,
    notAfter: tls.certNotAfter ?? null,
  };
}

function parseDNField(dn: string, field: string): string | null {
  const match = dn.match(new RegExp(`(?:^|,)\\s*${field}=([^,]+)`));
  return match ? match[1].trim() : null;
}
```

## 2. Certificate-Based Authorization Middleware

```typescript
// src/auth.ts
import { ClientCertInfo, extractCertInfo } from "./mtls";

export interface AuthResult {
  allowed: boolean;
  clientId: string | null;
  reason: string;
}

interface Env {
  ALLOWED_CN_PREFIX: string;       // e.g. "device."
  ALLOWED_ORG: string;             // e.g. "Acme Corp"
  CERT_REVOCATION: KVNamespace;    // serial → "revoked"
}

export async function authorizeRequest(
  request: Request,
  env: Env
): Promise<AuthResult> {
  const cert = extractCertInfo(request);

  if (!cert.certPresented) {
    return { allowed: false, clientId: null, reason: "No client certificate presented" };
  }
  if (!cert.verified) {
    return { allowed: false, clientId: null, reason: "Certificate verification failed" };
  }

  // Check certificate expiry (belt-and-suspenders; Cloudflare also checks)
  if (cert.notAfter) {
    const expiry = new Date(cert.notAfter).getTime();
    if (expiry < Date.now()) {
      return { allowed: false, clientId: null, reason: "Certificate expired" };
    }
  }

  // Organisation check
  if (cert.subject.o !== env.ALLOWED_ORG) {
    return {
      allowed: false,
      clientId: null,
      reason: `Certificate organisation mismatch: ${cert.subject.o}`,
    };
  }

  // CN prefix check (e.g., all valid clients are "device.<uuid>")
  if (!cert.subject.cn?.startsWith(env.ALLOWED_CN_PREFIX)) {
    return {
      allowed: false,
      clientId: null,
      reason: `CN does not match required prefix: ${cert.subject.cn}`,
    };
  }

  // Revocation check via KV
  if (cert.subject.serial) {
    const revoked = await env.CERT_REVOCATION.get(cert.subject.serial);
    if (revoked) {
      return { allowed: false, clientId: null, reason: "Certificate has been revoked" };
    }
  }

  return {
    allowed: true,
    clientId: cert.subject.cn,
    reason: "ok",
  };
}
```

## 3. Main Worker Using mTLS Auth

```typescript
// src/index.ts
import { authorizeRequest } from "./auth";

interface Env {
  ALLOWED_CN_PREFIX: string;
  ALLOWED_ORG: string;
  CERT_REVOCATION: KVNamespace;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const authResult = await authorizeRequest(request, env);

    if (!authResult.allowed) {
      // Log denial for audit
      console.log(JSON.stringify({
        event: "mtls_denied",
        reason: authResult.reason,
        ip: request.headers.get("CF-Connecting-IP"),
        timestamp: new Date().toISOString(),
      }));

      return new Response(
        JSON.stringify({ error: "Unauthorized", reason: authResult.reason }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      );
    }

    // Inject verified client identity as a trusted header for downstream logic
    const modifiedRequest = new Request(request, {
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        "X-Client-Id": authResult.clientId!,
        "X-Cert-Verified": "true",
      }),
    });

    return handleBusinessLogic(modifiedRequest, env);
  },
};

async function handleBusinessLogic(request: Request, env: Env): Promise<Response> {
  const clientId = request.headers.get("X-Client-Id")!;
  // ... application logic scoped to clientId
  return Response.json({ message: "OK", clientId });
}
```

## 4. Certificate Revocation Management

```typescript
// Revoke a certificate by serial number
export async function revokeCertificate(
  serial: string,
  reason: string,
  env: Env
): Promise<void> {
  await env.CERT_REVOCATION.put(serial, JSON.stringify({
    revokedAt: new Date().toISOString(),
    reason,
  }), {
    // Auto-expire KV entry after cert's natural expiry (or 2 years max)
    expirationTtl: 2 * 365 * 24 * 3600,
  });
}

// Admin endpoint to revoke
// POST /admin/revoke  { "serial": "ABCD1234", "reason": "device_decommissioned" }
```

## 5. Wrangler Configuration for mTLS

```toml
# wrangler.toml
name = "mtls-api"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "CERT_REVOCATION"
id = "YOUR_KV_NAMESPACE_ID"

[[d1_databases]]
binding = "DB"
database_name = "api-db"
database_id = "YOUR_D1_ID"

[vars]
ALLOWED_CN_PREFIX = "device."
ALLOWED_ORG = "Acme Corp"
```

```bash
# Upload your CA certificate to Cloudflare mTLS
wrangler mtls-certificate upload --ca --name "device-ca" --cert ca.pem

# Associate with a hostname in Zero Trust or via API
```

## Anti-patterns

- **Trusting `X-Client-Cert-*` headers without mTLS enforcement.** If mTLS is not enforced at the Cloudflare edge, any caller can spoof these headers. Use `cf.tlsClientAuth` which is set by Cloudflare itself.
- **Skipping revocation checks because "TLS verified the cert".** Certificate verification confirms the CA chain, not whether the certificate was revoked after issuance.
- **Using client CN as a primary key without collision checking.** If your CA can issue duplicate CNs, build the unique key from serial + issuer fingerprint.
- **Storing the full certificate PEM in KV.** Store only the serial and fingerprint; the raw PEM is large and unnecessary for revocation checks.
- **Not logging cert metadata on auth failure.** Denied requests should log the presented CN, issuer, and serial for incident response.

## Gotchas

- `cf.tlsClientAuth` is populated only when Cloudflare terminates TLS with mTLS enforcement enabled; if the route bypasses Cloudflare (e.g., direct-to-origin), the field is absent.
- `certVerified === "SUCCESS"` means chain verification succeeded; it does not imply the certificate is not expired — check `certNotAfter` separately.
- The `cf.tlsClientAuth.certSubjectDN` format is RFC 2253 distinguished name, reversed from RFC 1779; parse with care for multi-valued RDNs.
- Cloudflare's mTLS currently supports RSA and ECDSA client certificates; DSA certificates are rejected at the edge.
- Worker mTLS requires the hostname to have an mTLS CA uploaded; routes without a CA association will pass `certPresented = "0"` regardless of whether the client sends a cert.

## Verification

```bash
# Test with a valid client certificate
curl --cert client.pem --key client.key https://api.example.com/resource

# Test with no certificate — expect 401
curl https://api.example.com/resource

# Test with a revoked serial in KV
wrangler kv key put --namespace-id=NAMESPACE_ID "REVOKED_SERIAL" '{"revokedAt":"2026-01-01T00:00:00Z","reason":"test"}'
curl --cert revoked-client.pem --key revoked-client.key https://api.example.com/resource
# Expect 401 with reason "Certificate has been revoked"
```

## Related

- `cloudflare-zero-trust-mtls-service-auth.md`
- `spiffe-workload-identity-and-short-lived-mtls.md`
- `oauth-mutual-tls-certificate-bound-token-validation.md`
- `service-binding-zero-trust-workers.md`
- `tls-certificate-lifecycle-management.md`

## Sources

- Cloudflare mTLS documentation — https://developers.cloudflare.com/api-shield/security/mtls/
- Cloudflare Workers `cf` object reference — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- RFC 5280 Internet X.509 PKI Certificate — https://datatracker.ietf.org/doc/html/rfc5280
- RFC 8705 OAuth 2.0 mTLS — https://datatracker.ietf.org/doc/html/rfc8705
- Cloudflare Zero Trust mTLS rules — https://developers.cloudflare.com/cloudflare-one/identity/devices/mutual-tls/
