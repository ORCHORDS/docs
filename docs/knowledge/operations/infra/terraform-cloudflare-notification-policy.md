# Cloudflare Notification Policy Terraform Automation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare account has DDoS attacks, Workers script errors, and health-check failures that are silently recovered or go unnoticed for hours. You need a repeatable, audited way to provision notification policies — email, Slack webhooks, and PagerDuty — without manually clicking through the dashboard per zone or account.

## Context

Cloudflare Notification Policies (`cloudflare_notification_policy`) send alerts to configured destinations when account or zone events occur. Each policy targets one `alert_type` and can fan-out to multiple destinations: email addresses, webhook integrations, and third-party integrations (PagerDuty, Ops Genie). Webhook destinations are provisioned separately as `cloudflare_notification_policy_webhooks`. Policies are account-scoped resources — they apply to all zones in the account unless filtered by zone ID in the policy `filters` block. Supported alert types vary by Cloudflare plan; Enterprise accounts have the broadest coverage.

---

## Provider and Variable Setup

```hcl
# versions.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.36"
    }
  }
  required_version = ">= 1.9"
}

provider "cloudflare" {
  api_token = <redacted-secret>
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "account_id" { type = string }
variable "zone_id"    { type = string }
variable "alert_email" {
  type    = string
  default = "platform-alerts@company.com"
}
variable "slack_webhook_url" {
  type      = string
  sensitive = true
}
variable "pagerduty_token" {
  type      = string
  sensitive = true
}
```

## Webhook Destination Setup

```hcl
# destinations.tf

# Slack webhook destination
resource "cloudflare_notification_policy_webhooks" "slack" {
  account_id = var.account_id
  name       = "slack-platform-channel"
  url        = var.slack_webhook_url
  # secret is optional — used to sign payloads for HMAC verification
}

# PagerDuty destination
resource "cloudflare_notification_policy_webhooks" "pagerduty" {
  account_id = var.account_id
  name       = "pagerduty-cloudflare-service"
  url        = "https://events.pagerduty.com/integration/${var.pagerduty_token}/enqueue"
}
```

## DDoS Attack Alert Policy

```hcl
# policies.tf

resource "cloudflare_notification_policy" "ddos_l7" {
  account_id  = var.account_id
  name        = "ddos-l7-attack-started"
  description = "Alert when an HTTP DDoS attack is detected on any zone"
  enabled     = true
  alert_type  = "http_ddos_attack"

  email_integration {
    id   = var.alert_email
    name = "platform-email"
  }

  webhooks_integration {
    id   = cloudflare_notification_policy_webhooks.slack.id
    name = cloudflare_notification_policy_webhooks.slack.name
  }

  webhooks_integration {
    id   = cloudflare_notification_policy_webhooks.pagerduty.id
    name = cloudflare_notification_policy_webhooks.pagerduty.name
  }
}

# Network-layer (L3/L4) DDoS alert — requires Magic Transit or Spectrum
resource "cloudflare_notification_policy" "ddos_l3" {
  account_id  = var.account_id
  name        = "ddos-l3-network-attack"
  description = "Alert on network-layer DDoS attacks"
  enabled     = true
  alert_type  = "dos_attack_l3"

  email_integration {
    id   = var.alert_email
    name = "platform-email"
  }

  webhooks_integration {
    id   = cloudflare_notification_policy_webhooks.slack.id
    name = cloudflare_notification_policy_webhooks.slack.name
  }
}
```

## Workers Script Error Rate Alert

```hcl
resource "cloudflare_notification_policy" "workers_error_rate" {
  account_id  = var.account_id
  name        = "workers-error-rate-spike"
  description = "Alert when Workers error rate exceeds threshold"
  enabled     = true
  alert_type  = "workers_alert"

  filters {
    enabled        = ["true"]
    # Filter to a specific Workers script by name
    worker_name    = ["api-worker", "auth-worker"]
    alert_trigger_preferences = ["error_rate"]
  }

  email_integration {
    id   = var.alert_email
    name = "platform-email"
  }

  webhooks_integration {
    id   = cloudflare_notification_policy_webhooks.slack.id
    name = cloudflare_notification_policy_webhooks.slack.name
  }
}
```

## Load Balancer Health Check Alert

```hcl
resource "cloudflare_notification_policy" "lb_health_check" {
  account_id  = var.account_id
  name        = "load-balancer-pool-unhealthy"
  description = "Alert when a load balancer pool drops below healthy threshold"
  enabled     = true
  alert_type  = "load_balancing_health_alert"

  filters {
    health_check_type = ["pool"]
    # pool_id filter limits alerts to specific pools
    pool_id           = [cloudflare_load_balancer_pool.primary.id]
  }

  email_integration {
    id   = var.alert_email
    name = "platform-email"
  }

  webhooks_integration {
    id   = cloudflare_notification_policy_webhooks.pagerduty.id
    name = cloudflare_notification_policy_webhooks.pagerduty.name
  }
}
```

## SSL Certificate Expiry Alert

```hcl
resource "cloudflare_notification_policy" "ssl_expiry" {
  account_id  = var.account_id
  name        = "ssl-cert-expiry-30d"
  description = "Alert 30 days before SSL certificate expires"
  enabled     = true
  alert_type  = "universal_ssl_event_type"

  filters {
    ssl_certificate_type = ["custom", "advanced"]
  }

  email_integration {
    id   = var.alert_email
    name = "platform-email"
  }
}

# Dedicated certificate alert with zone filter
resource "cloudflare_notification_policy" "advanced_ssl_expiry" {
  account_id  = var.account_id
  name        = "advanced-cert-expiry-zone"
  description = "Advanced cert expiry for specific zone"
  enabled     = true
  alert_type  = "advanced_certificate_alert_type"

  filters {
    zone_id = [var.zone_id]
  }

  webhooks_integration {
    id   = cloudflare_notification_policy_webhooks.slack.id
    name = cloudflare_notification_policy_webhooks.slack.name
  }
}
```

---

## Anti-patterns

- **One policy per destination per alert type**: Fan out within a single policy by adding multiple `webhooks_integration` and `email_integration` blocks. Duplicate policies for the same `alert_type` produce duplicate notifications.
- **Hardcoding webhook URLs in `.tf` files**: Webhook URLs contain secrets. Store them in Vault, SOPS-encrypted tfvars, or CI secrets and inject via `TF_VAR_`.
- **Leaving `enabled = false` in production state files**: Disabled policies are easy to forget and leave incidents unnoticed. Use Terraform workspaces or environment-based tfvars to keep staging policies disabled and production ones enabled.
- **Missing `filters` on noisy alert types**: `load_balancing_health_alert` without a `pool_id` filter will fire for every pool in the account on every health change.

## Gotchas

- Alert type strings are Cloudflare-internal identifiers and are not well-documented outside the API reference; use the API to enumerate supported types for your plan: `GET /accounts/{id}/alerting/v3/available_alerts`.
- The `email_integration.id` field accepts an email address string directly — it is not a resource ID.
- Webhook secret signature verification (`secret` attribute on `cloudflare_notification_policy_webhooks`) uses HMAC-SHA256; the signature is in the `CF-Webhook-Auth` header.
- Some `alert_type` values are only available on Enterprise plans; applying a policy with an unsupported type returns a 400 from the Cloudflare API.
- Deleting a webhook destination (`cloudflare_notification_policy_webhooks`) before the policies that reference it will cause a Terraform error; remove the policy references first.

## Verification

```bash
# List all notification policies for the account
curl -s "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/alerting/v3/policies" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, alert_type, enabled}'

# List available alert types for this account/plan
curl -s "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/alerting/v3/available_alerts" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq 'keys'

# Test-fire a notification policy
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/alerting/v3/policies/$POLICY_ID/test" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.success'

# Confirm Terraform state matches API
terraform show | grep -A5 "cloudflare_notification_policy"
```

## Related

- `terraform-cloudflare-registrar-domain-management.md`
- `cloudflare-load-balancer-health-check-workers.md`
- `prometheus-alertmanager-config.md`
- `alerting-fatigue-reduction.md`

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/notification_policy
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/notification_policy_webhooks
- https://developers.cloudflare.com/notifications/
- https://developers.cloudflare.com/notifications/notification-available/
- https://developers.cloudflare.com/notifications/get-started/configure-webhooks/
