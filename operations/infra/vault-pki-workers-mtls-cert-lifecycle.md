# Vault PKI Certificate Lifecycle for Cloudflare Workers mTLS

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case**: You need Cloudflare Workers to authenticate to upstream services (or to each other) using short-lived mutual TLS client certificates, issued programmatically by HashiCorp Vault's PKI secrets engine, with automatic rotation before expiry — without ever storing long-lived certificate material in Workers secrets.

**Context**: Cloudflare Workers support mTLS via the `connect()` API with a `mTLS` option that accepts a certificate ID provisioned in the Cloudflare dashboard or API. Vault PKI can issue leaf certificates with TTLs as short as minutes. Bridging the two requires: (1) Vault issuing certs on demand, (2) uploading them to Cloudflare as mTLS client certificates, (3) binding the certificate ID to the Worker. A cron-based rotation Worker or external CI job handles renewal before TTL expiry.

---

## Vault PKI Engine Bootstrap

```bash
# Enable PKI engine with a 90-day max TTL for intermediate CA
vault secrets enable -path=pki_int pki
vault secrets tune -max-lease-ttl=2160h pki_int

# Generate intermediate CSR
vault write pki_int/intermediate/generate/internal \
  common_name="workers-mtls-int.internal" \
  ttl=2160h \
  key_type=ec key_bits=256

# Sign with root CA (stored in pki_root path)
vault write pki_root/root/sign-intermediate \
  csr=@int.csr \
  format=pem_bundle ttl=2160h | \
  jq -r .data.certificate > signed_int.pem

vault write pki_int/intermediate/set-signed certificate=@signed_int.pem

# Create a role for Workers leaf certs — short TTL
vault write pki_int/roles/workers-client \
  allowed_domains="workers.internal" \
  allow_subdomains=true \
  max_ttl=4h \
  generate_lease=true \
  key_type=ec key_bits=256 \
  no_store=false
```

## Issuing a Leaf Certificate from Vault

```typescript
// workers-cert-issuer/src/index.ts
// A privileged internal Worker (or CI job) issues and uploads certs

interface VaultCertResponse {
  data: {
    certificate: string;
    private_key: string;
    issuing_ca: string;
    serial_number: string;
    expiration: number;
  };
}

async function issueCertFromVault(
  vaultAddr: string,
  vaultToken: string,
  role: string
): Promise<VaultCertResponse["data"]> {
  const res = await fetch(`${vaultAddr}/v1/pki_int/issue/${role}`, {
    method: "POST",
    headers: {
      "X-Vault-Token": vaultToken,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      common_name: `worker-client.workers.internal`,
      ttl: "4h",
      format: "pem",
    }),
  });
  if (!res.ok) throw new Error(`Vault issue failed: ${res.status}`);
  const body = (await res.json()) as VaultCertResponse;
  return body.data;
}
```

## Uploading Certificate to Cloudflare mTLS Store

```typescript
// Upload the Vault-issued cert to Cloudflare as a client certificate
interface CFMtlsCert {
  id: string;
  expires_on: string;
  status: string;
}

async function uploadMtlsCert(
  accountId: string,
  apiToken: string,
  certPem: string,
  keyPem: string
): Promise<string> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/mtls_certificates`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: `vault-workers-client-${Date.now()}`,
        certificates: certPem,
        private_key: keyPem,
        ca: false,
      }),
    }
  );
  const json = (await res.json()) as { result: CFMtlsCert; success: boolean };
  if (!json.success) throw new Error("CF mTLS upload failed");
  return json.result.id;
}
```

## Worker Using mTLS Certificate for Upstream Requests

```typescript
// production-worker/src/index.ts
export interface Env {
  MTLS_CERT_ID: string; // Bound via wrangler.toml or Terraform
  UPSTREAM_URL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Cloudflare resolves MTLS_CERT_ID to the cert material at runtime
    const upstream = await fetch(env.UPSTREAM_URL, {
      // @ts-expect-error – Workers-specific mTLS option
      cf: {
        mtls: { certificateId: env.MTLS_CERT_ID },
      },
      headers: { "X-Forwarded-For": request.headers.get("CF-Connecting-IP") ?? "" },
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: upstream.headers,
    });
  },
};
```

## Rotation Cron Worker

```typescript
// cert-rotation-worker/src/index.ts
// Runs on a Cloudflare cron trigger every 3 hours to rotate before 4h TTL
export interface Env {
  VAULT_ADDR: string;
  VAULT_TOKEN: string; // Rotated separately via Vault AppRole
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  CERT_ID_KV: KVNamespace; // Stores current active cert ID
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const certData = await issueCertFromVault(env.VAULT_ADDR, env.VAULT_TOKEN, "workers-client");
    const newCertId = await uploadMtlsCert(
      env.CF_ACCOUNT_ID,
      env.CF_API_TOKEN,
      certData.certificate,
      certData.private_key
    );

    const oldCertId = await env.CERT_ID_KV.get("active_cert_id");

    // Update Worker binding via Cloudflare API (requires deploy or variable update)
    await updateWorkerBinding(env.CF_ACCOUNT_ID, env.CF_API_TOKEN, newCertId);

    // Store new cert ID; clean up old after grace period
    await env.CERT_ID_KV.put("active_cert_id", newCertId);
    await env.CERT_ID_KV.put("prev_cert_id", oldCertId ?? "");

    // Revoke old cert from Vault
    if (certData.serial_number) {
      await revokeVaultCert(env.VAULT_ADDR, env.VAULT_TOKEN, certData.serial_number);
    }
  },
};

async function updateWorkerBinding(accountId: string, apiToken: string, certId: string) {
  // Patch the worker's environment variable via Workers API
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/production-worker/settings`,
    {
      method: "PATCH",
      headers: { Authorization: `Bearer ${apiToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        bindings: [{ type: "plain_text", name: "MTLS_CERT_ID", text: certId }],
      }),
    }
  );
}

async function revokeVaultCert(vaultAddr: string, token: string, serial: string) {
  await fetch(`${vaultAddr}/v1/pki_int/revoke`, {
    method: "POST",
    headers: { "X-Vault-Token": token, "Content-Type": "application/json" },
    body: JSON.stringify({ serial_number: serial }),
  });
}
```

## Terraform: Binding mTLS Cert to Worker

```hcl
# terraform/workers-mtls.tf
resource "cloudflare_worker_script" "production" {
  account_id = var.cloudflare_account_id
  name       = "production-worker"
  content    = file("${path.module}/../dist/production-worker.js")

  plain_text_binding {
    name = "UPSTREAM_URL"
    text = var.upstream_url
  }

  # MTLS_CERT_ID is managed by the rotation worker; use a data source or
  # external to read the current value from state rather than hardcoding
  plain_text_binding {
    name = "MTLS_CERT_ID"
    text = data.external.current_cert_id.result["id"]
  }
}

data "external" "current_cert_id" {
  program = ["bash", "-c", <<-EOT
    echo "{\"id\": \"$(vault read -field=value secret/workers/active_cert_id)\"}"
  EOT
  ]
}
```

---

**Anti-patterns**:
- Storing the private key in Workers secrets long-term — use the rotation cron pattern so secrets are replaced every TTL cycle.
- Setting Vault role `max_ttl` longer than 24h for client certs — keeps revocation blast radius small.
- Skipping CRL distribution point config in Vault — upstream services need to check revocation status.
- Using RSA 2048 for leaf certs — EC P-256 is faster at TLS handshake on Workers' edge nodes.
- Binding `MTLS_CERT_ID` in `wrangler.toml` committed to git — this bakes a specific cert ID into source; use environment-level secrets or the API instead.

**Gotchas**:
- Cloudflare deletes uploaded mTLS client certificates 24h after their `expires_on` timestamp — you cannot re-use the cert object after that.
- The Workers mTLS binding (`cf.mtls`) is only available to outbound `fetch()` calls, not inbound request validation — that is handled by Cloudflare Access or mutual TLS on the zone.
- Vault AppRole `secret_id` used by the rotation worker itself needs a separate rotation mechanism (use response-wrapping + a bootstrap CI step).
- The Cloudflare mTLS certificate upload API requires the full PEM chain including the issuing CA certificate concatenated into `certificates`.
- Workers environment variable updates via API require a new deployment — the PATCH to `/settings` only takes effect after the next script publish.

**Verification**:
```bash
# Check active cert in Vault
vault list pki_int/certs

# Verify cert is uploaded and not expired in Cloudflare
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/mtls_certificates" \
  | jq '.result[] | {id, name, expires_on, status}'

# Test mTLS connection from a local curl using the same cert material
curl --cert worker-client.pem --key worker-client-key.pem \
  --cacert upstream-ca.pem https://your-upstream-service/health
```

**Related**:
- `cloudflare-mtls-client-certificates-terraform.md`
- `vault-cloudflare-workers-dynamic-secrets.md`
- `secrets-rotation-runbook.md`
- `ssl-tls-certificate-management.md`

**Sources**:
- https://developers.cloudflare.com/workers/runtime-apis/fetch/#mtls
- https://developer.hashicorp.com/vault/docs/secrets/pki
- https://developers.cloudflare.com/api/operations/m-tls-certificate-management-upload-m-tls-certificate
