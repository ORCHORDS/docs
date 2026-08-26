# Cloudflare Access mTLS Client Certificate Validation in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need machine-to-machine authentication where clients present an X.509 certificate instead of a browser cookie or JWT — IoT devices, internal services, CI/CD pipelines. Cloudflare Access **mTLS authentication** terminates the TLS handshake, validates the client cert against your CA, and forwards cert attributes in request headers to downstream Workers. Workers must re-validate those headers and enforce fine-grained policy (common name, OU, serial number) before processing requests.

---

## Context

Cloudflare Access mTLS works at the Cloudflare network edge:

1. Client connects with a mutual TLS handshake.
2. Cloudflare validates the client cert against a CA bundle uploaded to your Zero Trust organization.
3. If validation passes, Cloudflare forwards cert metadata in headers: `Cf-Client-Cert-Issuer`, `Cf-Client-Cert-Subject-Dn`, `Cf-Client-Cert-Serial-Number`, `Cf-Client-Cert-Verified`.
4. Your Worker reads these headers to implement application-level policy.

Workers cannot re-perform TLS handshake inspection — they only see the headers Cloudflare populates. The critical protection: these headers are **stripped from incoming requests** by Cloudflare so clients cannot spoof them. Only Cloudflare itself can set `Cf-Client-Cert-*` headers.

This pattern differs from `workers-mtls-certificates.md` (outbound mTLS — Workers calling external services with a client cert). This article covers *inbound* mTLS where Workers validate requests from cert-authenticated clients.

---

## Uploading a CA Bundle to Zero Trust

```bash
# Upload your internal CA to Cloudflare Zero Trust
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/certificates" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "internal-iot-ca",
    "certificate": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
    "associated_hostnames": ["iot-api.example.com"]
  }'
```

---

## Access Policy Configuration (Terraform)

```hcl
# Configure an Access application requiring mTLS
resource "cloudflare_access_application" "iot_api" {
  account_id       = var.cf_account_id
  name             = "IoT API"
  domain           = "iot-api.example.com"
  type             = "self_hosted"
  session_duration = "24h"
}

resource "cloudflare_access_policy" "mtls_only" {
  application_id = cloudflare_access_application.iot_api.id
  account_id     = var.cf_account_id
  name           = "mTLS client cert required"
  precedence     = 1
  decision       = "allow"

  include {
    certificate = true  # Requires a valid mTLS client cert
  }
}

resource "cloudflare_access_mutual_tls_certificate" "iot_ca" {
  account_id           = var.cf_account_id
  name                 = "internal-iot-ca"
  certificate          = file("ca.pem")
  associated_hostnames = ["iot-api.example.com"]
}
```

---

## Reading Cert Headers in a Worker

```typescript
// src/mtls-auth.ts
interface CertClaims {
  verified: boolean;
  subject: string;
  issuer: string;
  serialNumber: string;
  commonName: string | null;
  organizationalUnit: string | null;
}

function parseCertHeaders(request: Request): CertClaims {
  const verified = request.headers.get("Cf-Client-Cert-Verified") === "SUCCESS";
  const subject = request.headers.get("Cf-Client-Cert-Subject-Dn") ?? "";
  const issuer = request.headers.get("Cf-Client-Cert-Issuer-Dn") ?? "";
  const serialNumber = request.headers.get("Cf-Client-Cert-Serial-Number") ?? "";

  // Parse Distinguished Name components from Subject DN
  // Format: "CN=device-001, OU=sensors, O=Acme Corp, C=US"
  const parseDN = (dn: string) => {
    const map = new Map<string, string>();
    for (const part of dn.split(",")) {
      const [key, ...rest] = part.trim().split("=");
      if (key && rest.length) map.set(key.trim(), rest.join("=").trim());
    }
    return map;
  };

  const subjectMap = parseDN(subject);

  return {
    verified,
    subject,
    issuer,
    serialNumber,
    commonName: subjectMap.get("CN") ?? null,
    organizationalUnit: subjectMap.get("OU") ?? null,
  };
}
```

---

## Policy Enforcement in the Worker Handler

```typescript
interface Env {
  REVOKED_SERIALS: KVNamespace; // serial number → revocation reason
  ALLOWED_OU: string; // "sensors" — set as Worker env var
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cert = parseCertHeaders(request);

    // 1. Reject if Cloudflare did not validate the cert
    if (!cert.verified) {
      return new Response(
        JSON.stringify({ error: "Client certificate required" }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      );
    }

    // 2. Check against revocation list in KV
    if (cert.serialNumber) {
      const revocationReason = await env.REVOKED_SERIALS.get(cert.serialNumber);
      if (revocationReason) {
        return new Response(
          JSON.stringify({ error: "Certificate revoked", reason: revocationReason }),
          { status: 403, headers: { "Content-Type": "application/json" } }
        );
      }
    }

    // 3. Enforce Organizational Unit policy
    if (cert.organizationalUnit !== env.ALLOWED_OU) {
      return new Response(
        JSON.stringify({
          error: "Certificate OU not authorized",
          got: cert.organizationalUnit,
          expected: env.ALLOWED_OU,
        }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    }

    // 4. Attach cert identity to downstream context
    const enrichedRequest = new Request(request, {
      headers: {
        ...Object.fromEntries(request.headers),
        "X-Device-Id": cert.commonName ?? "unknown",
        "X-Cert-OU": cert.organizationalUnit ?? "",
      },
    });

    return handleDeviceRequest(enrichedRequest, env, cert);
  },
};

async function handleDeviceRequest(
  request: Request,
  env: Env,
  cert: CertClaims
): Promise<Response> {
  return Response.json({
    message: "Authenticated",
    deviceId: cert.commonName,
    ou: cert.organizationalUnit,
  });
}
```

---

## Revoking a Certificate (Soft Revocation via KV)

Cloudflare does not support CRL or OCSP at the Access mTLS level. Implement soft revocation using KV — revoked serial numbers are checked on every request.

```typescript
// Admin endpoint to revoke a certificate
async function revokeCertificate(
  serialNumber: string,
  reason: string,
  kv: KVNamespace
): Promise<void> {
  await kv.put(serialNumber, reason, {
    metadata: { revokedAt: new Date().toISOString() },
  });
}

// Admin endpoint to reinstate a certificate
async function reinstateCertificate(
  serialNumber: string,
  kv: KVNamespace
): Promise<void> {
  await kv.delete(serialNumber);
}
```

---

## Integration Testing with a Self-Signed Client Cert

```bash
# Generate a test CA and client cert for local testing
openssl genrsa -out ca.key 4096
openssl req -new -x509 -days 365 -key ca.key -out ca.pem \
  -subj "/CN=Test CA/O=Acme Corp/C=US"

openssl genrsa -out device-001.key 2048
openssl req -new -key device-001.key -out device-001.csr \
  -subj "/CN=device-001/OU=sensors/O=Acme Corp/C=US"
openssl x509 -req -days 90 -in device-001.csr \
  -CA ca.pem -CAkey ca.key -CAcreateserial -out device-001.crt

# Test against a Workers dev tunnel (mTLS headers injected manually for local tests)
curl --cert device-001.crt --key device-001.key \
  --cacert ca.pem https://iot-api.example.com/data \
  -v 2>&1 | grep -E "(< HTTP|Cf-Client)"
```

---

## Anti-patterns

- **Trusting `Cf-Client-Cert-Verified` without also checking the Common Name**: `Verified: SUCCESS` only means the cert chains to *a* trusted CA in your bundle — not that the specific device is authorized. Always enforce CN or OU policy.
- **Forwarding `Cf-Client-Cert-*` headers to origin services**: downstream services should not re-validate these headers because they never received the TLS context. Pass an application-level identity token instead.
- **Using Cloudflare KV as the sole revocation store without a TTL-based invalidation strategy**: KV has eventual consistency with up to 60s of lag on globally distributed reads. A revoked cert may still pass checks for up to 60 seconds. For instant revocation, use a Durable Object as the authoritative store.
- **Uploading intermediate CA certs instead of the root CA**: Cloudflare Access requires the root CA or the full chain. Uploading only the intermediate results in `FAILED` verification for certs signed by that intermediate.

---

## Gotchas

- `Cf-Client-Cert-Verified` values are `SUCCESS`, `FAILED`, or absent (when mTLS was not attempted). An absent header is not the same as `FAILED` — guard for both.
- Cloudflare Access mTLS is available on **Zero Trust** plans. It is not available on standard Cloudflare DNS-only accounts or Workers.dev subdomains.
- The cert headers are populated only when the request passes through a Cloudflare Access application with mTLS enabled. Workers deployed on `workers.dev` do not receive these headers.
- Cert header names changed between Access generations: `Cf-Client-Cert-Subject-Dn` (current) vs older `Cf-Access-Client-Certificate-*` headers. Verify which generation your Zero Trust org is on.
- When using Workers Service Bindings, cert headers are **not** forwarded across service binding hops. Read and extract identity in the outermost Worker, then pass it as a custom header to inner services.

---

## Verification

```bash
# List mTLS CAs in your Zero Trust account
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/certificates" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '[.result[] | {name, id, associated_hostnames}]'

# Test with a valid client cert (should return 200)
curl --cert device-001.crt --key device-001.key \
  https://iot-api.example.com/data

# Test without cert (should return 401 from Access, not reaching Worker)
curl https://iot-api.example.com/data -v 2>&1 | grep "< HTTP"

# Check soft revocation — add serial to KV and retry
wrangler kv:key put --binding=REVOKED_SERIALS "12:AB:34:CD" "decommissioned"
curl --cert device-001.crt --key device-001.key https://iot-api.example.com/data
```

---

## Related

- `workers-mtls-certificates.md`
- `cloudflare-access-jwt-validation.md`
- `cloudflare-access-zero-trust-service-tokens.md`
- `zero-trust-access.md`
- `zero-trust-device-posture.md`

---

## Sources

- https://developers.cloudflare.com/cloudflare-one/identity/devices/access-integrations/mutual-tls-authentication/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
- https://developers.cloudflare.com/workers/examples/auth-with-headers/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/certificates/
