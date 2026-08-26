# Cloudflare Tunnel Deploy Automation CI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You run private services (databases, internal APIs, staging environments) on self-hosted
infrastructure and need to expose them to Cloudflare Workers or external clients without
opening inbound firewall ports. Manually creating and updating Cloudflare Tunnels via the
dashboard is error-prone and unauditable. The goal is fully automated, GitOps-driven
Tunnel configuration that deploys consistently across staging and production.

---

## Context

Cloudflare Tunnel (`cloudflared`) creates an outbound-only persistent connection from your
infrastructure to Cloudflare's network. Traffic flows: client → Cloudflare edge →
encrypted tunnel → `cloudflared` daemon → internal service.

Key concepts:

- **Tunnel** — A named resource in your Cloudflare account. Has a UUID and a set of
  credentials stored in a JSON file.
- **Ingress rules** — Ordered list mapping hostnames/paths to internal service URLs.
- **cloudflared config.yml** — The daemon config file; contains the tunnel UUID, credentials
  path, and ingress rules.
- **Named tunnels vs legacy tunnels** — Always use named tunnels (API-managed). Legacy
  `--hostname` quick tunnels are ephemeral and not suitable for production.
- `cloudflared tunnel create`, `route dns`, `run` — the three CLI primitives.

---

## Terraform-Managed Tunnel Creation

Provision the Tunnel resource declaratively so its UUID and credentials are reproducible.

```hcl
# terraform/tunnel.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

resource "cloudflare_tunnel" "internal_api" {
  account_id = var.cloudflare_account_id
  name       = "internal-api-${var.environment}"
  secret     = <redacted-secret>  # 32-byte base64 string; generate once, store in Vault
}

resource "cloudflare_tunnel_config" "internal_api" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_tunnel.internal_api.id

  config {
    ingress_rule {
      hostname = "api-internal.${var.environment}.example.com"
      service  = "http://localhost:8080"
    }
    ingress_rule {
      hostname = "db-admin.${var.environment}.example.com"
      service  = "http://localhost:8081"
      origin_request {
        no_tls_verify = false
      }
    }
    # Required catch-all
    ingress_rule {
      service = "http_status:404"
    }
  }
}

resource "cloudflare_record" "tunnel_dns" {
  zone_id = var.cloudflare_zone_id
  name    = "api-internal.${var.environment}"
  value   = "${cloudflare_tunnel.internal_api.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
}

output "tunnel_id" {
  value = cloudflare_tunnel.internal_api.id
}

output "tunnel_token" {
  value     = cloudflare_tunnel.internal_api.tunnel_token
  sensitive = true
}
```

---

## cloudflared Deployment as a Systemd Service

```bash
#!/usr/bin/env bash
# scripts/install-tunnel-daemon.sh
# Run on the host that will run the tunnel daemon.
# Requires: TUNNEL_TOKEN env var (from Terraform output)

set -euo pipefail

CLOUDFLARED_VERSION="2024.12.0"

# Install cloudflared
curl -fsSL "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-amd64.deb" \
  -o /tmp/cloudflared.deb
dpkg -i /tmp/cloudflared.deb

# Install as a systemd service using the token (no config file needed)
cloudflared service install "${TUNNEL_TOKEN}"
systemctl enable --now cloudflared
systemctl status cloudflared --no-pager
```

---

## Kubernetes Deployment for Tunnel Daemon

For container-based infrastructure, run `cloudflared` as a Kubernetes Deployment.

```yaml
# k8s/cloudflared-deployment.yaml
apiVersion: v1
kind: Secret
metadata:
  name: tunnel-credentials
  namespace: network
type: Opaque
stringData:
  token: "PLACEHOLDER_REPLACED_BY_CI"   # replaced via envsubst in CI

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cloudflared
  namespace: network
  labels:
    app: cloudflared
spec:
  replicas: 2   # HA: two connectors per tunnel
  selector:
    matchLabels:
      app: cloudflared
  template:
    metadata:
      labels:
        app: cloudflared
    spec:
      containers:
        - name: cloudflared
          image: cloudflare/cloudflared:2024.12.0
          args:
            - tunnel
            - --no-autoupdate
            - run
          env:
            - name: TUNNEL_TOKEN
              valueFrom:
                secretKeyRef:
                  name: tunnel-credentials
                  key: token
          resources:
            requests:
              memory: 128Mi
              cpu: 100m
            limits:
              memory: 256Mi
              cpu: 500m
          readinessProbe:
            httpGet:
              path: /ready
              port: 2000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /ready
              port: 2000
            initialDelaySeconds: 15
            periodSeconds: 20
      terminationGracePeriodSeconds: 30
```

---

## CI/CD Pipeline: End-to-End Tunnel Deploy

```yaml
# .github/workflows/deploy-tunnel.yml
name: Deploy Cloudflare Tunnel

on:
  push:
    branches: [main]
    paths:
      - "terraform/tunnel.tf"
      - "k8s/cloudflared-deployment.yaml"

env:
  TF_VAR_cloudflare_account_id: ${{ secrets.CF_ACCOUNT_ID }}
  TF_VAR_cloudflare_zone_id: ${{ secrets.CF_ZONE_ID }}
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

jobs:
  terraform-tunnel:
    runs-on: ubuntu-latest
    outputs:
      tunnel_token: ${{ steps.tf-output.outputs.tunnel_token }}
      tunnel_id: ${{ steps.tf-output.outputs.tunnel_id }}
    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.9.0

      - name: Terraform Init
        run: terraform init
        working-directory: terraform

      - name: Terraform Plan
        run: terraform plan -var="environment=production" -var="tunnel_secret=${{ secrets.TUNNEL_SECRET }}"
        working-directory: terraform

      - name: Terraform Apply
        run: terraform apply -auto-approve -var="environment=production" -var="tunnel_secret=${{ secrets.TUNNEL_SECRET }}"
        working-directory: terraform

      - name: Export Tunnel Token
        id: tf-output
        run: |
          echo "tunnel_token=$(terraform output -raw tunnel_token)" >> "$GITHUB_OUTPUT"
          echo "tunnel_id=$(terraform output -raw tunnel_id)" >> "$GITHUB_OUTPUT"
        working-directory: terraform

  deploy-daemon:
    needs: terraform-tunnel
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Substitute tunnel token into K8s manifest
        run: |
          TUNNEL_TOKEN="${{ needs.terraform-tunnel.outputs.tunnel_token }}" \
            envsubst < k8s/cloudflared-deployment.yaml > /tmp/cloudflared-rendered.yaml

      - name: Apply to Kubernetes
        run: kubectl apply -f /tmp/cloudflared-rendered.yaml
        env:
          KUBECONFIG_DATA: ${{ secrets.KUBECONFIG }}

      - name: Wait for rollout
        run: kubectl rollout status deployment/cloudflared -n network --timeout=120s

  verify-connectivity:
    needs: [terraform-tunnel, deploy-daemon]
    runs-on: ubuntu-latest
    steps:
      - name: Verify tunnel is active
        run: |
          TUNNEL_ID="${{ needs.terraform-tunnel.outputs.tunnel_id }}"
          ACTIVE=$(curl -s \
            "https://api.cloudflare.com/client/v4/accounts/${{ secrets.CF_ACCOUNT_ID }}/cfd_tunnel/${TUNNEL_ID}/connections" \
            -H "Authorization: Bearer ${{ secrets.CF_API_TOKEN }}" | jq '.result | length')
          echo "Active connections: $ACTIVE"
          [ "$ACTIVE" -ge 1 ] || { echo "No active tunnel connections"; exit 1; }

      - name: Smoke test internal endpoint
        run: |
          HTTP_CODE=$(curl -o /dev/null -s -w "%{http_code}" \
            https://api-internal.production.example.com/health)
          [ "$HTTP_CODE" = "200" ] || { echo "Health check failed: $HTTP_CODE"; exit 1; }
```

---

## Ingress Rule Update Without Daemon Restart

Tunnel ingress config is stored server-side in Cloudflare. Updating it does not require
restarting `cloudflared`; the daemon polls for config changes every 300 seconds by default.

```typescript
// scripts/update-tunnel-ingress.ts
// Patch ingress rules via API without Terraform for fast iteration

const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const TUNNEL_ID = process.env.TUNNEL_ID!;

interface IngressRule {
  hostname?: string;
  service: string;
}

async function updateIngress(rules: IngressRule[]): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ config: { ingress: rules } }),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Failed to update ingress: ${err}`);
  }

  console.log("Ingress updated; daemon will pick up changes within 300 s");
}

// Force faster propagation: send SIGUSR1 to cloudflared to reload config immediately
// On K8s: kubectl exec -n network deploy/cloudflared -- kill -USR1 1
```

---

## Anti-patterns

- **Committing tunnel credentials JSON to Git** — Credentials allow any process to impersonate
  the tunnel. Always store in Vault, GitHub Secrets, or a Kubernetes Secret.
- **Running `cloudflared tunnel login` in CI** — This writes a cert.pem tied to your
  Cloudflare account. Use `TUNNEL_TOKEN` (the per-tunnel token) instead; it has minimum scope.
- **Single replica `cloudflared` in production** — Cloudflare recommends two connectors
  per tunnel for HA. A single replica means a daemon restart causes downtime.
- **Using `--url` quick-tunnel flag** — Generates an ephemeral random hostname. Never use
  for production workloads.
- **Hardcoding `no-tls-verify: true` for origin** — Bypasses certificate verification
  for internal services. Use a private CA and proper cert pinning instead.

---

## Gotchas

- The `tunnel_token` Terraform output contains the full base64-encoded credential blob.
  It is valid immediately after `terraform apply`; no additional `tunnel login` step is
  needed.
- Cloudflare Tunnel requires `cloudflared` to maintain at least one active connection.
  During a rolling K8s update, ensure `minReadySeconds` keeps at least one old pod alive
  while the new pod establishes its connection.
- The Terraform `cloudflare_tunnel.secret` must be exactly 32 bytes of entropy
  base64-encoded to a 44-character string. Use `openssl rand -base64 32` to generate it.
- DNS CNAME records pointing to `.cfargotunnel.com` must have `proxied: true` (orange
  cloud). Setting `proxied: false` bypasses Cloudflare entirely and exposes the tunnel UUID.
- If `cloudflared` crashes without a graceful shutdown, active WebSocket connections
  through the tunnel are terminated immediately. Configure `terminationGracePeriodSeconds`
  ≥ 30 for the K8s pod.

---

## Verification

```bash
# List tunnels and their status
cloudflared tunnel list

# Check active connections for a specific tunnel
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID/connections" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {colo: .colo_name, id: .id}'

# View live tunnel metrics (when daemon is running)
cloudflared tunnel info $TUNNEL_ID

# Test internal route without DNS (direct via tunnel ID)
curl https://$TUNNEL_ID.cfargotunnel.com/health
```

---

## Related

- `oidc-federated-deploy-credentials.md`
- `pages-functions-env-var-management.md`
- `secrets-management-wrangler-vault.md`
- `multi-region-dns-failover-routing.md`
- `environment-parity-staging-production.md`

---

## Sources

- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/deploy-tunnels/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/tunnel
- https://github.com/cloudflare/cloudflared
