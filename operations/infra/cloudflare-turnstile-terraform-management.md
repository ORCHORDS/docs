# Cloudflare Turnstile Widget Terraform Management

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your team manages multiple Turnstile widgets across staging, production, and feature environments.
Manual widget creation in the Cloudflare dashboard causes configuration drift: different domains
are allowlisted per environment, widget modes diverge, and rotation of site keys becomes an ad-hoc
operation prone to downtime. You need repeatable, reviewable IaC for every widget lifecycle event.

## Context

Cloudflare Turnstile replaces CAPTCHA with a non-interactive browser challenge. Each widget is
scoped to an account (not a zone), has a `site_key` (public) and `secret_key` (sensitive), and
supports three modes: `managed`, `non-interactive`, and `invisible`. Terraform manages widgets
via the `cloudflare_turnstile_widget` resource in the `cloudflare/cloudflare` provider (≥ 4.x).
The secret key is marked sensitive in state and should be pushed into your secrets manager
immediately after `apply`.

---

## 1. Provider and Backend Setup

```hcl
# versions.tf
terraform {
  required_version = ">= 1.9"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
  backend "s3" {
    bucket         = "my-tfstate"
    key            = "cloudflare/turnstile/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "tf-lock"
  }
}

provider "cloudflare" {
  api_token = <redacted-secret>
}
```

The API token needs the **Account / Turnstile / Edit** permission. Zone permissions are not
required because Turnstile is account-scoped.

---

## 2. Widget Resource Definition

```hcl
# widgets.tf
variable "cloudflare_account_id" { type = string }

locals {
  widgets = {
    checkout = {
      name    = "Checkout Form"
      mode    = "managed"
      domains = ["example.com", "www.example.com"]
    }
    login = {
      name    = "Login Page"
      mode    = "invisible"
      domains = ["example.com", "app.example.com"]
    }
    signup = {
      name    = "Signup Flow"
      mode    = "non-interactive"
      domains = ["example.com"]
    }
  }
}

resource "cloudflare_turnstile_widget" "widget" {
  for_each   = local.widgets
  account_id = var.cloudflare_account_id
  name       = each.value.name
  mode       = each.value.mode
  domains    = each.value.domains
  # bot_fight_mode defaults to false; set true to combine with Bot Management
  bot_fight_mode = false
}
```

---

## 3. Outputs and Secret Key Extraction

```hcl
# outputs.tf
output "turnstile_site_keys" {
  description = "Public site keys per widget (safe to commit)"
  value = {
    for k, w in cloudflare_turnstile_widget.widget :
    k => w.id  # id == site_key
  }
}

output "turnstile_secret_keys" {
  description = "Secret keys — pipe to Vault/AWS Secrets Manager post-apply"
  sensitive   = true
  value = {
    for k, w in cloudflare_turnstile_widget.widget :
    k => w.secret
  }
}
```

Push secrets immediately after apply with a null_resource or a CI step:

```bash
# ci/push-turnstile-secrets.sh
KEYS=$(terraform output -json turnstile_secret_keys)
for widget in checkout login signup; do
  secret=$(echo "$KEYS" | jq -r ".${widget}")
  aws secretsmanager put-secret-value \
    --secret-id "cloudflare/turnstile/${widget}" \
    --secret-string "$secret"
done
```

---

## 4. Workers-Side Verification

```typescript
// src/turnstile-verify.ts
interface Env {
  TURNSTILE_SECRET: string; // bound from Workers secret, not Terraform output
}

export async function verifyTurnstile(
  token: string,
  ip: string,
  env: Env
): Promise<boolean> {
  const body = new URLSearchParams({
    secret: env.TURNSTILE_SECRET,
    response: token,
    remoteip: ip,
  });

  const res = await fetch(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    { method: "POST", body }
  );
  const data = (await res.json()) as { success: boolean; "error-codes": string[] };

  if (!data.success) {
    console.warn("Turnstile failed", data["error-codes"]);
  }
  return data.success;
}
```

Deploy the secret separately from Terraform to avoid state exposure:

```bash
wrangler secret put TURNSTILE_SECRET --env production
```

---

## 5. Multi-Environment Strategy

```hcl
# env/prod/main.tf
module "turnstile" {
  source              = "../../modules/turnstile"
  cloudflare_account_id = var.account_id
  environment         = "prod"
  allowed_domains     = ["example.com", "www.example.com"]
  mode                = "managed"
}

# env/staging/main.tf
module "turnstile" {
  source              = "../../modules/turnstile"
  cloudflare_account_id = var.account_id
  environment         = "staging"
  allowed_domains     = ["staging.example.com"]
  mode                = "non-interactive"  # faster for test suites
}
```

Staging widgets should only allow staging domains — a misconfigured allowlist lets attackers
replay staging tokens on production.

---

## Anti-patterns

- **Hardcoding site keys in frontend bundles without per-environment switching.** Use an env var
  injected at build time sourced from Terraform outputs.
- **Storing the secret key in Terraform state long-term.** The `secret` attribute is sensitive but
  still lives in the state file. Move it to Vault or AWS Secrets Manager within the same CI run.
- **Using a single widget across all domains.** Turnstile validates the referring domain; sharing
  widgets is fine only when the domain list is exhaustive and intentional.
- **Skipping `bot_fight_mode` alignment with Bot Management.** If you have Enterprise Bot
  Management, enabling `bot_fight_mode` on Turnstile avoids double-scoring.

---

## Gotchas

- `cloudflare_turnstile_widget.id` is the `sitekey`, not an opaque UUID. It is safe to use in
  frontend `<div data-sitekey="...">` attributes.
- Widget mode cannot be changed in-place for `invisible` → `managed`; Terraform will destroy and
  recreate, briefly breaking the challenge until the new site key propagates.
- The Cloudflare provider does not support importing existing Turnstile widgets by name; you must
  import by `account_id/sitekey`: `terraform import cloudflare_turnstile_widget.widget[\"login\"] ACCOUNT_ID/SITEKEY`.
- Turnstile challenges expire after 300 seconds. Verification calls older than that return
  `timeout-or-duplicate` even if the token was valid when issued.

---

## Verification

```bash
# Confirm widgets exist via API
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/challenges/widgets" \
  | jq '.result[] | {sitekey: .sitekey, name: .name, mode: .mode, domains: .domains}'

# Terraform plan should show zero changes after a clean apply
terraform plan -detailed-exitcode   # exit code 0 = no changes

# Confirm secrets landed in AWS
aws secretsmanager get-secret-value \
  --secret-id "cloudflare/turnstile/login" \
  --query SecretString --output text | wc -c  # non-zero = secret present
```

---

## Related

- `cloudflare-workers-api-token-scoping.md`
- `cloudflare-workers-kv-namespace-terraform.md`
- `terraform-write-only-arguments-secret-rotation.md`
- `workers-secrets-rotation-automation.md`
- `secrets-management-vault.md`

---

## Sources

- https://developers.cloudflare.com/turnstile/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/turnstile_widget
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
