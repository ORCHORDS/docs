# Cloudflare mTLS Client Certificates Terraform

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Machine-to-machine API endpoints on example project (example.com) must reject unauthenticated
callers before the request reaches a Worker.  API tokens in headers are
revocable but can leak through logs; mTLS (mutual TLS) client certificates
provide a cryptographically stronger identity assertion at the TLS handshake
level and can be enforced at Cloudflare's edge via WAF rules, eliminating
unauthenticated requests from ever reaching Worker code.

## Context

Cloudflare mTLS works as follows:

1. A CA certificate is uploaded to the Cloudflare account.
2. Client certificates are issued by that CA (self-managed or via Cloudflare's
   Managed Headers API) and distributed to API consumers.
3. A WAF custom rule uses the `cf.tls_client_auth.*` fields to reject requests
   that do not present a valid certificate signed by the uploaded CA.
4. Workers can additionally inspect `request.cf.tlsClientAuth` to perform
   fine-grained per-certificate access control.

Terraform resources involved:
- `cloudflare_authenticated_origin_pulls_certificate` — for origin-pull mTLS
- `cloudflare_mtls_certificate` — for client-facing mTLS CA upload
- `cloudflare_ruleset` (WAF) — for enforcement rule

---

## 1. Generating a Self-Managed CA and Client Certificate

```bash
# Generate a private CA (do once; store the CA key in Vault)
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -subj "/CN=example project-API-CA/O=orchords" \
  -out ca.crt

# Issue a client certificate for a specific service
openssl genrsa -out client-ingest.key 2048
openssl req -new -key client-ingest.key \
  -subj "/CN=example project-ingest-service/O=orchords" \
  -out client-ingest.csr
openssl x509 -req -in client-ingest.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out client-ingest.crt -days 365 -sha256

# Verify
openssl verify -CAfile ca.crt client-ingest.crt
```

---

## 2. Uploading the CA to Cloudflare via Terraform

```hcl
# infra/cloudflare_mtls.tf

resource "cloudflare_mtls_certificate" "example project_api_ca" {
  account_id   = var.cloudflare_account_id
  name         = "example project-api-ca"
  certificates = file("${path.module}/certs/ca.crt")
  ca           = true
}

output "mtls_ca_id" {
  value     = cloudflare_mtls_certificate.example project_api_ca.id
  sensitive = false
}
```

The `ca = true` flag marks this certificate as a CA bundle used for client
authentication validation, not as a server certificate.

---

## 3. WAF Rule Enforcing mTLS on API Routes

```hcl
resource "cloudflare_ruleset" "mtls_enforcement" {
  zone_id     = var.zone_id
  name        = "mTLS enforcement for example project API"
  description = "Block requests without a valid client certificate on /api/internal/*"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules {
    action      = "block"
    description = "Reject requests without a valid client certificate"
    enabled     = true
    expression  = <<-EOT
      (http.request.uri.path matches "^/api/internal/") and
      not (
        cf.tls_client_auth.cert_verified eq true and
        cf.tls_client_auth.cert_issuer_dn contains "example project-api-ca"
      )
    EOT

    action_parameters {
      response {
        status_code  = 403
        content_type = "application/json"
        content      = "{\"error\":\"Client certificate required\"}"
      }
    }
  }
}
```

---

## 4. Enabling mTLS on the Zone

mTLS enforcement requires the zone's mTLS feature to be enabled.  This is
managed via the Cloudflare API (no Terraform resource as of mid-2026):

```bash
# Enable mTLS on the zone for the relevant hostname
curl -s -X PUT \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/tls_client_auth" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"value": "on"}' | jq '.result'

# Bind the uploaded CA to the hostname
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/certificate_authorities/hostname_associations" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"hostnames\": [\"api.example.com\"],
    \"mtls_certificate_id\": \"${MTLS_CA_ID}\"
  }" | jq '.result'
```

Wrap these calls in a Terraform `null_resource` with `local-exec` until a
native resource is available:

```hcl
resource "null_resource" "mtls_hostname_bind" {
  triggers = {
    ca_id    = cloudflare_mtls_certificate.example project_api_ca.id
    hostname = "api.example.com"
  }

  provisioner "local-exec" {
    command = <<-EOT
      curl -sf -X POST \
        "https://api.cloudflare.com/client/v4/zones/${var.zone_id}/certificate_authorities/hostname_associations" \
        -H "Authorization: Bearer ${var.cloudflare_api_token}" \
        -H "Content-Type: application/json" \
        -d '{"hostnames":["api.example.com"],"mtls_certificate_id":"${cloudflare_mtls_certificate.example project_api_ca.id}"}'
    EOT
  }
}
```

---

## 5. Worker-Side Certificate Inspection

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tlsAuth = (request.cf as any)?.tlsClientAuth;

    if (!tlsAuth?.certVerified || tlsAuth.certVerified !== "SUCCESS") {
      return new Response(JSON.stringify({ error: "mTLS verification failed" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    }

    const commonName = tlsAuth.certSubjectDNCommonName as string;
    // Fine-grained: only allow specific service identities
    const allowedCNs = ["example project-ingest-service", "example project-scheduler"];
    if (!allowedCNs.includes(commonName)) {
      return new Response(JSON.stringify({ error: "Certificate CN not authorized" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    }

    // proceed with request
    return new Response("OK");
  },
};
```

---

## 6. Testing mTLS Enforcement

```bash
# Request without a client certificate — expect 403
curl -s -o /dev/null -w "%{http_code}" \
  https://api.example.com/api/internal/ping
# Expected: 403

# Request with a valid client certificate — expect 200
curl -s -o /dev/null -w "%{http_code}" \
  --cert client-ingest.crt \
  --key  client-ingest.key \
  https://api.example.com/api/internal/ping
# Expected: 200

# Request with an expired or wrong-CA certificate — expect 403
curl -s -o /dev/null -w "%{http_code}" \
  --cert other-ca-client.crt \
  --key  other-ca-client.key \
  https://api.example.com/api/internal/ping
# Expected: 403
```

---

## Anti-patterns

- Do not use Cloudflare's mTLS for user-facing browser traffic — browsers do
  not support client certificates in the standard UX flow.  mTLS is for
  machine-to-machine API calls only.
- Do not store the CA private key in the repository or as a plain-text
  Terraform variable.  Store it in Vault; reference via Vault Provider or a
  `data` source.
- Do not rely solely on the WAF rule without the Worker-side CN check — the WAF
  ensures the cert is CA-signed, but the Worker must enforce which specific
  service identities are authorised.

## Gotchas

- Cloudflare terminates TLS before the Worker receives the request; the Worker
  sees `cf.tlsClientAuth` fields, not the raw certificate.  You cannot inspect
  the full certificate DER in a Worker.
- Hostname association (step 4) must be re-applied after the CA is rotated to a
  new `cloudflare_mtls_certificate` resource — the association is by CA ID, not
  by content.
- The `cf.tls_client_auth.cert_issuer_dn` WAF field is a string that contains
  the full distinguished name; use `contains` rather than `eq` because the DN
  format includes commas and can vary.

## Verification

```bash
# Confirm CA is uploaded
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/mtls_certificates" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" | jq '[.result[] | {name, id, ca}]'

# Confirm hostname association
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/certificate_authorities/hostname_associations" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" | jq '.result'
```

## Related

- `cloudflare-access-jwt-workers-validation.md`
- `cloudflare-waf-custom-ruleset-terraform.md`
- `terraform-cloudflare-rate-limiting-rules.md`
- `vault-cloudflare-workers-dynamic-secrets.md`
- `ssl-tls-certificate-management.md`

## Sources

- https://developers.cloudflare.com/api-shield/security/mtls/
- https://developers.cloudflare.com/api-shield/security/mtls/configure/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/mtls_certificate
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
