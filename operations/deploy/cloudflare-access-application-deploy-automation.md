# Cloudflare Access Application Deploy Automation

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

Every new internal tool, staging environment, or admin panel needs a Cloudflare Access application created to gate it — but engineers are creating them by hand in the dashboard, leading to inconsistent policy definitions, unreviewed allow-lists, and access policies that outlive the services they protect.

## Context

Cloudflare Access applications and their policies are first-class API resources under **Zero Trust**. Terraforming them alongside your Worker or Pages deploy means every environment gets an identity-aware perimeter automatically, reviewable in code, and torn down when the service is decommissioned. This article covers the full automation: Terraform modules for Access applications, GitHub Actions integration, and the service-token pattern for machine-to-machine auth between Workers.

---

## 1. Terraform Module — Access Application per Environment

```hcl
# terraform/modules/access_app/main.tf
variable "zone_id"       { type = string }
variable "account_id"    { type = string }
variable "app_name"      { type = string }
variable "app_domain"    { type = string }
variable "allowed_emails" { type = list(string) }
variable "session_duration" {
  type    = string
  default = "24h"
}

resource "cloudflare_zero_trust_access_application" "app" {
  account_id       = var.account_id
  name             = var.app_name
  domain           = var.app_domain
  type             = "self_hosted"
  session_duration = var.session_duration

  # Require re-authentication on every deploy by bumping app_launcher_visible
  app_launcher_visible = true
}

resource "cloudflare_zero_trust_access_policy" "allow_team" {
  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.app.id
  name           = "${var.app_name}-allow-team"
  precedence     = 1
  decision       = "allow"

  include {
    email = var.allowed_emails
  }
}

resource "cloudflare_zero_trust_access_policy" "deny_all" {
  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.app.id
  name           = "${var.app_name}-deny-all"
  precedence     = 99
  decision       = "deny"

  include {
    everyone = true
  }
}

output "application_id" { value = cloudflare_zero_trust_access_application.app.id }
output "application_aud" { value = cloudflare_zero_trust_access_application.app.aud }
```

```hcl
# terraform/staging/main.tf
module "staging_access" {
  source         = "../modules/access_app"
  account_id     = var.cf_account_id
  zone_id        = var.cf_zone_id
  app_name       = "myapp-staging"
  app_domain     = "staging.myapp.com"
  allowed_emails = ["*@mycompany.com"]
  session_duration = "8h"
}
```

---

## 2. Service Token Automation for Worker-to-Worker Auth

When a Worker needs to call another Access-protected endpoint (e.g., an internal API), use a **Service Token** rather than an identity token:

```hcl
# terraform/modules/access_app/service_token.tf
resource "cloudflare_zero_trust_access_service_token" "worker_token" {
  account_id = var.account_id
  name       = "${var.app_name}-worker-service-token"
  min_days_for_renewal = 30
}

resource "cloudflare_zero_trust_access_policy" "allow_service_token" {
  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.app.id
  name           = "${var.app_name}-allow-service-token"
  precedence     = 2
  decision       = "non_identity"

  include {
    service_token = [cloudflare_zero_trust_access_service_token.worker_token.id]
  }
}

output "service_client_id"     { value = cloudflare_zero_trust_access_service_token.worker_token.client_id     sensitive = true }
output "service_client_secret" { value = cloudflare_zero_trust_access_service_token.worker_token.client_secret sensitive = true }
```

Inject the token credentials into the consuming Worker as secrets:

```bash
wrangler secret put CF_ACCESS_CLIENT_ID     <<< "$TF_OUTPUT_SERVICE_CLIENT_ID"
wrangler secret put CF_ACCESS_CLIENT_SECRET <<< "$TF_OUTPUT_SERVICE_CLIENT_SECRET"
```

---

## 3. Worker Code — Attaching Access Service Token to Upstream Requests

```typescript
// workers/internal-api-client/src/index.ts
export interface Env {
  CF_ACCESS_CLIENT_ID:     string;
  CF_ACCESS_CLIENT_SECRET: string;
  INTERNAL_API_URL:        string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = new Request(env.INTERNAL_API_URL + new URL(request.url).pathname, {
      method:  request.method,
      headers: {
        ...Object.fromEntries(request.headers),
        "CF-Access-Client-Id":     env.CF_ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
      },
      body: request.body,
    });
    return fetch(upstream);
  },
} satisfies ExportedHandler<Env>;
```

---

## 4. JWT Validation in the Access-Protected Worker

Validate the Access JWT so the Worker itself enforces identity — not just the perimeter:

```typescript
// workers/protected-api/src/access-jwt.ts
const CERTS_URL = "https://myteam.cloudflareaccess.com/cdn-cgi/access/certs";

interface JWTPayload {
  sub:   string;
  email: string;
  aud:   string[];
  exp:   number;
}

export async function verifyAccessJWT(
  request: Request,
  applicationAud: string
): Promise<JWTPayload> {
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) throw new Response("Missing Access JWT", { status: 401 });

  const certsRes  = await fetch(CERTS_URL);
  const { keys }  = await certsRes.json() as { keys: JsonWebKey[] };

  // Import first matching key (production: match by kid header)
  const key = await crypto.subtle.importKey(
    "jwk", keys[0], { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]
  );

  const [headerB64, payloadB64, sigB64] = token.split(".");
  const payload: JWTPayload = JSON.parse(atob(payloadB64));

  if (!payload.aud.includes(applicationAud)) throw new Response("Wrong audience", { status: 403 });
  if (payload.exp < Date.now() / 1000)        throw new Response("Token expired",  { status: 401 });

  return payload;
}
```

---

## 5. GitHub Actions — Terraform Apply on Deploy

```yaml
# .github/workflows/deploy-with-access.yml
name: Deploy + Provision Access

on:
  push:
    branches: [main]

jobs:
  terraform:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: terraform/staging
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.10.0"

      - name: Terraform Init
        run: terraform init
        env:
          TF_VAR_cf_account_id: ${{ secrets.CF_ACCOUNT_ID }}
          TF_VAR_cf_api_token:  ${{ secrets.CF_API_TOKEN }}

      - name: Terraform Apply
        run: terraform apply -auto-approve
        env:
          TF_VAR_cf_account_id: ${{ secrets.CF_ACCOUNT_ID }}
          TF_VAR_cf_api_token:  ${{ secrets.CF_API_TOKEN }}

  deploy-worker:
    needs: terraform
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Anti-patterns

- **Hand-creating Access applications in the dashboard** — they become orphaned when the service is deleted; Terraform state keeps lifecycle in sync.
- **Using identity tokens for Worker-to-Worker calls** — identity tokens expire in hours; service tokens auto-renew via Terraform and rotate on schedule.
- **Skipping JWT validation in the Worker** — the Access perimeter can be bypassed if an attacker has direct IP access to the Worker's `*.workers.dev` origin; always validate the `Cf-Access-Jwt-Assertion` header.
- **Sharing a single service token across multiple Workers** — blast radius on token compromise; issue one token per service pair.

## Gotchas

- **`min_days_for_renewal`** — Terraform's `cloudflare_zero_trust_access_service_token` will regenerate the secret when `min_days_for_renewal` days remain before expiry; this triggers a Terraform diff and a new `wrangler secret put` cycle. Automate this in CI.
- **AUD claim mismatch** — the `aud` field in the JWT is the Access Application ID (a UUID), not the domain. Export it from Terraform as `application_aud` and inject it into the Worker as a secret or var.
- **Wildcard subdomain applications** — Access supports `*.staging.myapp.com` as the domain, but JWT audience verification must still match the specific application UUID.
- **`non_identity` decision** — service token policies must use `decision = "non_identity"`, not `"allow"`; mixing them silently rejects service token requests.

## Verification

```bash
# Confirm Access application exists
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/access/apps" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | select(.domain == "staging.myapp.com") | {id, name, aud}'

# Test identity gate (expect 302 redirect to Access login)
curl -sI https://staging.myapp.com/ | grep -i location

# Test service token bypass
curl -sf https://staging.myapp.com/health \
  -H "CF-Access-Client-Id: $SERVICE_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $SERVICE_CLIENT_SECRET" \
  | jq .
```

## Related

- `secrets-management-wrangler-vault.md`
- `oidc-federated-deploy-credentials.md`
- `gitops-secrets-management.md`
- `workers-secrets-rotation-zero-downtime.md`

## Sources

- Cloudflare Zero Trust Access Applications API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/
- Access Service Tokens: https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- Terraform Cloudflare provider — access resources: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/zero_trust_access_application
- Validating Access JWTs: https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
