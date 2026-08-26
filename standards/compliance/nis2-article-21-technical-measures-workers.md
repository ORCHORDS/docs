# NIS2 Article 21 Technical Security Measures for Cloud-Native Workers Applications

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your organisation is classified as an essential or important entity under NIS2 (Directive (EU) 2022/2555)
and runs core services on Cloudflare Workers, D1, R2, and KV. The national competent authority (NCA)
or your CISO requests a demonstrable mapping of NIS2 Article 21 security measures to actual
infrastructure controls. Incident-reporting workflows (Article 23) are covered in a separate
article. This article focuses on the ten Article 21 risk-management measures as they apply to a
Workers-first, edge-native stack.

## Context

NIS2 Article 21 mandates that essential entities implement "appropriate and proportionate technical,
operational and organisational measures" across ten enumerated domains:

1. Policies on risk analysis and information system security
2. Incident handling
3. Business continuity and crisis management
4. Supply chain security
5. Security in network and information systems acquisition, development and maintenance
6. Policies and procedures to assess effectiveness of cybersecurity risk-management measures
7. Basic cyber hygiene practices and cybersecurity training
8. Cryptography and encryption
9. Human resources security, access control policies and asset management
10. Multi-factor authentication / continuous authentication / secured communications

Member state transposition deadlines passed October 2024. NCAs may request evidence of compliance
at any time; fines for essential entities reach €10 million or 2 % of global annual turnover.

Cloudflare Workers presents a specific challenge: there is no traditional server to harden, no
OS-level audit log, and no VPC firewall ruleset. Controls must be implemented in code, Wrangler
configuration, and Cloudflare dashboard settings.

## Article 21(2)(a) — Risk Analysis and System Security Policy

Maintain a live risk register keyed to Workers services. Each Worker should declare its risk profile
in a sidecar document stored in R2:

```typescript
// risk-register/update.ts — runs as a scheduled Worker (cron trigger)
import type { Env } from "./types";

interface ServiceRiskEntry {
  workerId: string;
  classification: "essential" | "important" | "ancillary";
  dataCategories: string[];
  externalConnections: string[];
  lastAssessed: string; // ISO-8601
  residualRiskScore: number; // 1-5
  mitigations: string[];
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const register: ServiceRiskEntry[] = await fetchCurrentRegister(env);

    for (const entry of register) {
      entry.lastAssessed = new Date().toISOString();
      entry.residualRiskScore = await scoreService(entry);
    }

    // Versioned key provides audit trail without overwriting prior entries
    const key = `risk-register/${new Date().toISOString().slice(0, 10)}.json`;
    await env.COMPLIANCE_BUCKET.put(key, JSON.stringify(register, null, 2), {
      httpMetadata: { contentType: "application/json" },
      customMetadata: { schema: "v2", classification: "internal" },
    });
  },
};

async function fetchCurrentRegister(env: Env): Promise<ServiceRiskEntry[]> {
  const obj = await env.COMPLIANCE_BUCKET.get("risk-register/current.json");
  if (!obj) return [];
  return obj.json<ServiceRiskEntry[]>();
}

async function scoreService(entry: ServiceRiskEntry): Promise<number> {
  const threatLikelihood = entry.externalConnections.length > 0 ? 3 : 1;
  const dataImpact = entry.dataCategories.includes("personal") ? 3 : 1;
  return Math.min(5, Math.ceil((threatLikelihood * dataImpact) / 2));
}
```

## Article 21(2)(c) — Business Continuity and Multi-Region Resilience

Workers run globally by default, but you must demonstrate RTO/RPO commitments and implement
observable failover logic:

```typescript
// src/resilience.ts
export async function resilientD1Query<T>(
  env: Env,
  primary: D1Database,
  fallback: D1Database,
  query: string,
  params: unknown[]
): Promise<T[]> {
  const startMs = Date.now();

  try {
    const result = await primary.prepare(query).bind(...params).all<T>();
    await recordMetric(env, "d1_query_latency_ms", Date.now() - startMs, { region: "primary" });
    return result.results;
  } catch (err) {
    // Failover — emit an event so the incident handler (Art.23) is triggered if needed
    await env.INCIDENT_QUEUE.send({
      type: "db_failover",
      timestamp: new Date().toISOString(),
      error: String(err),
      rto_ms: Date.now() - startMs,
    });

    const fallbackResult = await fallback.prepare(query).bind(...params).all<T>();
    return fallbackResult.results;
  }
}

async function recordMetric(
  env: Env,
  name: string,
  value: number,
  tags: Record<string, string>
): Promise<void> {
  // Push to Workers Analytics Engine for SLA evidence
  env.ANALYTICS.writeDataPoint({
    blobs: [name, JSON.stringify(tags)],
    doubles: [value],
    timestamp: Date.now(),
  });
}
```

D1 is single-primary. Document the RTO in your BCP and ensure the failover replica binding is
declared in `wrangler.toml`:

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB_PRIMARY"
database_name = "production"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[d1_databases]]
binding = "DB_FALLBACK"
database_name = "production-replica"
database_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
```

## Article 21(2)(d) — Supply Chain Security for Workers Dependencies

NIS2 requires security measures extending to direct suppliers. For a Workers project this means
npm package provenance and Wrangler build attestation stored as durable evidence:

```yaml
# .github/workflows/supply-chain.yml
name: Supply Chain Security

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  id-token: write
  attestations: write

jobs:
  dependency-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Audit dependencies (block on high/critical)
        run: npm audit --audit-level=high

      - name: Generate SBOM (CycloneDX)
        uses: anchore/sbom-action@v0
        with:
          format: cyclonedx-json
          output-file: sbom.cdx.json

      - name: Upload SBOM to R2 for NIS2 evidence archive
        env:
          R2_ENDPOINT: ${{ secrets.R2_ENDPOINT }}
          AWS_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_KEY }}
        run: |
          aws s3 cp sbom.cdx.json \
            "s3://compliance-evidence/sbom/$(date +%Y-%m-%d)/$(git rev-parse --short HEAD).cdx.json" \
            --endpoint-url "$R2_ENDPOINT"

      - name: Build Workers bundle
        run: npx wrangler deploy --dry-run --outdir dist/

      - name: Attest build provenance
        uses: actions/attest-build-provenance@v1
        with:
          subject-path: dist/
```

## Article 21(2)(h) — Cryptography and Secrets Management

All secrets must be rotated on schedule and access must be auditable. Workers Secrets + KV-based
rotation with a 24-hour grace window:

```typescript
// src/crypto-hygiene.ts

export async function rotateHmacSecret(env: Env): Promise<void> {
  const newKey = await crypto.subtle.generateKey(
    { name: "HMAC", hash: "SHA-256" },
    true,
    ["sign", "verify"]
  );
  const exported = await crypto.subtle.exportKey("raw", newKey);
  const b64 = btoa(String.fromCharCode(...new Uint8Array(exported)));

  const existing = await env.SECRETS_KV.get("hmac:current");
  if (existing) {
    // Keep previous key for 24 h so in-flight tokens remain valid
    await env.SECRETS_KV.put("hmac:previous", existing, { expirationTtl: 86400 });
  }

  await env.SECRETS_KV.put("hmac:current", b64, {
    metadata: {
      rotatedAt: new Date().toISOString(),
      rotatedBy: "scheduled-rotation-worker",
    },
  });

  await env.AUDIT_LOG.put(
    `rotation/${new Date().toISOString()}`,
    JSON.stringify({
      event: "secret_rotation",
      keyId: "hmac",
      timestamp: new Date().toISOString(),
      nis2_control: "Art21(2)(h)",
    })
  );
}

// Always use constant-time comparison to prevent timing attacks
export async function verifyHmac(
  env: Env,
  payload: string,
  providedSig: string
): Promise<boolean> {
  const keyB64 = await env.SECRETS_KV.get("hmac:current");
  if (!keyB64) throw new Error("HMAC key not found");

  const keyBytes = Uint8Array.from(atob(keyB64), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    keyBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );

  const sigBytes = Uint8Array.from(atob(providedSig), (c) => c.charCodeAt(0));
  const payloadBytes = new TextEncoder().encode(payload);

  return crypto.subtle.verify("HMAC", cryptoKey, sigBytes, payloadBytes);
}
```

## Article 21(2)(j) — Multi-Factor Authentication on Management Interfaces

All Cloudflare dashboard access and Workers deploy pipelines must enforce MFA. Enforce via
Cloudflare Access + Terraform:

```hcl
# terraform/cloudflare-access-mfa.tf

resource "cloudflare_access_application" "workers_dashboard" {
  zone_id          = var.zone_id
  name             = "Workers Deploy Portal"
  domain           = "deploy.internal.example.com"
  type             = "self_hosted"
  session_duration = "4h"
}

resource "cloudflare_access_policy" "require_mfa" {
  application_id = cloudflare_access_application.workers_dashboard.id
  zone_id        = var.zone_id
  name           = "Require MFA — NIS2 Art21(2)(j)"
  decision       = "allow"
  precedence     = 1

  include {
    email_domain = ["example.com"]
  }

  require {
    auth_method = ["mfa"]          # Hardware key or TOTP
    ip_ranges   = var.corporate_cidr_blocks
  }
}

# CI deploy tokens: short-lived, scoped, IP-restricted
resource "cloudflare_api_token" "ci_deploy" {
  name = "CI/CD Deploy Token — NIS2"

  policy {
    effect = "allow"
    resources = {
      "com.cloudflare.api.account.worker.script.*" = "*"
    }
    permission_groups = [
      { id = data.cloudflare_api_token_permission_groups.all.worker["Workers Scripts Write"] }
    ]
  }

  condition {
    request_ip {
      in = var.github_actions_ips
    }
  }
}
```

## Anti-patterns

- Storing API tokens as plain-text `[vars]` in `wrangler.toml` rather than using `wrangler secret put` — violates Art.21(2)(h) and exposes secrets in version control.
- Running a single global Worker with no RTO evidence and no failover path — cannot demonstrate Art.21(2)(c) commitments to an NCA.
- Using `npm install --legacy-peer-deps` in CI without an audit step — undermines the Art.21(2)(d) supply-chain assurance obligation.
- Granting `cloudflare:*` API-token permissions to CI pipelines instead of least-privilege, expiring tokens — violates Art.21(2)(j) access-control requirements.
- Conflating NIS2 Art.23 incident-reporting timelines (24 h early warning / 72 h notification) with Art.21 preventive controls — they are separate obligations requiring separate evidence packages.

## Gotchas

- NIS2 applies to the **entity**, not to Cloudflare. Cloudflare's ISO 27001 and SOC 2 certificates cover their infrastructure. You must separately evidence your own Workers application controls (the "use-layer").
- The `cf` object (`request.cf.colo`, `request.cf.country`) varies per PoP. Do not rely on it for MFA enforcement — use Cloudflare Access policies that evaluate server-side before the Worker executes.
- Workers KV has eventual consistency with up to 60-second propagation lag. If you use KV for session revocation (Art.21(2)(j)), a revoked token may still be accepted at another PoP. Use Durable Objects for strong-consistency revocation when the risk assessment demands it.
- D1 does not support automatic write failover. RTO evidence must reflect this limitation and your BCP must explicitly account for periods of D1 primary unavailability.
- NIS2 transposition varies by member state. Germany (NIS2UmsuCG), France, the Netherlands, and others add sector-specific requirements above the Directive minimum. Always check NCA-specific implementing guidance alongside the Directive text.

## Verification

```bash
# 1. Confirm no plaintext secrets in wrangler.toml
grep -rE "(API_KEY|SECRET|TOKEN|PASSWORD)\s*=" wrangler.toml \
  && echo "FAIL: plaintext secret detected" || echo "PASS"

# 2. Verify npm audit is clean
npm audit --audit-level=high --json | jq '.metadata.vulnerabilities | .high + .critical'
# Expected: 0

# 3. Confirm SBOM was generated and uploaded this week
aws s3 ls "s3://compliance-evidence/sbom/$(date +%Y-%m-%d)/" \
  --endpoint-url "$R2_ENDPOINT"

# 4. Check that a Cloudflare Access MFA policy is active for the deploy portal
curl -sS "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/apps" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | \
  jq '.result[] | select(.name | contains("Workers")) | {name, session_duration}'

# 5. Verify HMAC rotation occurred within the last 90 days
wrangler kv:key get "hmac:current" \
  --namespace-id="${KV_NAMESPACE_ID}" \
  --format json | jq '.metadata.rotatedAt'
```

## Related

- `nis2-article-23-incident-reporting-playbook.md`
- `nis2-directive-implementation.md`
- `eu-cyber-resilience-act-cra-software.md`
- `dora-digital-operational-resilience.md`
- `soc2-type2-controls-engineering.md`
- `sbom-generation-distribution-cicd.md`

## Sources

- Directive (EU) 2022/2555 (NIS2), Articles 21 and 23 — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2555
- ENISA NIS2 Implementation Guidance (2024) — https://www.enisa.europa.eu/topics/cybersecurity-policy/nis-directive-new
- ENISA Guidelines on Security Measures under NIS2 Article 21 — https://www.enisa.europa.eu/publications/guidelines-on-measures-article-21
- Cloudflare Workers Security Model — https://developers.cloudflare.com/workers/reference/security-model/
- Cloudflare Access — https://developers.cloudflare.com/cloudflare-one/policies/access/
- BSI TR-03116 (German NIS2 technical requirements) — https://www.bsi.bund.de/EN/Topics/CloudComputing/Anforderungskatalog/anforderungskatalog_node.html
