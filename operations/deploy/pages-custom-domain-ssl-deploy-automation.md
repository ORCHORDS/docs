# Pages Custom Domain SSL Deploy Automation

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

After deploying a new Cloudflare Pages project (or promoting a branch to production), the custom domain and SSL certificate must be configured manually in the dashboard. This blocks automated environment provisioning, makes multi-tenant setups tedious, and introduces human error when adding multiple subdomains across staging and production.

---

## Context

Cloudflare Pages custom domains are managed via the Cloudflare API (`/accounts/{account_id}/pages/projects/{project_name}/domains`). SSL is handled automatically by Cloudflare once DNS is delegated; the deploy task is to attach the domain record and wait for certificate issuance. This can be fully automated in CI post-deploy hooks using the Cloudflare REST API or the `@cloudflare/cloudflare` SDK (formerly `cloudflare-sdk`).

Domain attach triggers Cloudflare to verify DNS ownership and issue a TLS certificate via its managed CA. On Cloudflare-managed DNS the certificate issuance is near-instant; on external DNS it requires CNAME verification first.

---

## Attaching a Custom Domain via API

```typescript
// scripts/attach-pages-domain.ts
const CF_API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const CF_ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;

interface DomainAttachRequest {
  projectName: string;
  domain: string;
}

interface DomainResponse {
  name: string;
  status: string;
  created_on: string;
  certificate_status: string;
}

async function attachDomain(req: DomainAttachRequest): Promise<DomainResponse> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/${req.projectName}/domains`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: req.domain }),
  });

  const json = await response.json() as { success: boolean; result: DomainResponse; errors: any[] };

  if (!json.success) {
    // Domain already attached is not a fatal error
    if (json.errors?.some((e: any) => e.code === 8000015)) {
      console.log(`Domain ${req.domain} already attached — skipping`);
      return { name: req.domain, status: "active", created_on: "", certificate_status: "active" };
    }
    throw new Error(`Failed to attach domain: ${JSON.stringify(json.errors)}`);
  }

  return json.result;
}

async function main() {
  const projectName = process.argv[2];
  const domain = process.argv[3];

  if (!projectName || !domain) {
    console.error("Usage: ts-node attach-pages-domain.ts <project-name> <domain>");
    process.exit(1);
  }

  const result = await attachDomain({ projectName, domain });
  console.log(`Domain attached: ${result.name} (status: ${result.status})`);
}

main().catch(console.error);
```

---

## Polling for SSL Certificate Issuance

```typescript
// scripts/wait-for-ssl.ts
const CF_API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const CF_ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;

async function getDomainStatus(projectName: string, domain: string): Promise<string> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/${projectName}/domains`;
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
  });
  const json = await response.json() as { result: Array<{ name: string; certificate_status: string }> };
  const found = json.result.find((d) => d.name === domain);
  return found?.certificate_status ?? "unknown";
}

async function waitForSSL(
  projectName: string,
  domain: string,
  timeoutMs = 120_000,
  pollIntervalMs = 5_000
): Promise<void> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const status = await getDomainStatus(projectName, domain);
    console.log(`[${new Date().toISOString()}] ${domain} certificate_status: ${status}`);

    if (status === "active") {
      console.log(`SSL certificate active for ${domain}`);
      return;
    }

    if (status === "error") {
      throw new Error(`SSL certificate issuance failed for ${domain}`);
    }

    await new Promise((r) => setTimeout(r, pollIntervalMs));
  }

  throw new Error(`Timeout waiting for SSL certificate on ${domain}`);
}

const [, , projectName, domain] = process.argv;
waitForSSL(projectName, domain).catch((err) => {
  console.error(err.message);
  process.exit(1);
});
```

---

## Multi-domain Provisioning

```typescript
// scripts/provision-all-domains.ts
import { execSync } from "child_process";

interface DomainSpec {
  project: string;
  domains: string[];
}

const DOMAIN_SPECS: DomainSpec[] = [
  {
    project: "my-app-production",
    domains: ["app.example.com", "www.example.com"],
  },
  {
    project: "my-app-staging",
    domains: ["staging.example.com"],
  },
];

async function attachDomainViaAPI(project: string, domain: string): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${process.env.CLOUDFLARE_ACCOUNT_ID}/pages/projects/${project}/domains`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.CLOUDFLARE_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: domain }),
  });
  const data = await res.json() as any;
  if (!data.success && data.errors?.[0]?.code !== 8000015) {
    throw new Error(`${domain}: ${JSON.stringify(data.errors)}`);
  }
  console.log(`Attached ${domain} to ${project}`);
}

async function main(): Promise<void> {
  for (const spec of DOMAIN_SPECS) {
    for (const domain of spec.domains) {
      await attachDomainViaAPI(spec.project, domain);
    }
  }
  console.log("All domains provisioned");
}

main().catch((err) => { console.error(err); process.exit(1); });
```

---

## GitHub Actions Integration

```yaml
# .github/workflows/pages-deploy.yml
name: Pages Deploy with Custom Domain

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Cloudflare Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          accountId: ${{ secrets.CF_ACCOUNT_ID }}
          command: pages deploy ./dist --project-name my-app-production

      - name: Attach custom domain
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx ts-node scripts/attach-pages-domain.ts my-app-production app.example.com
          npx ts-node scripts/attach-pages-domain.ts my-app-production www.example.com

      - name: Wait for SSL certificate
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx ts-node scripts/wait-for-ssl.ts my-app-production app.example.com

      - name: Verify HTTPS
        run: |
          STATUS=$(curl -o /dev/null -s -w "%{http_code}" https://app.example.com/health)
          [ "$STATUS" -eq 200 ] && echo "HTTPS OK" || (echo "HTTPS check failed: $STATUS"; exit 1)
```

---

## Anti-patterns

- **Failing the pipeline when the domain already exists** — error code `8000015` means "already attached"; treat it as a no-op, not a failure.
- **Not waiting for certificate issuance before running smoke tests** — SSL is async; hitting HTTPS immediately after attach may result in certificate errors.
- **Hardcoding domain names in wrangler.toml under `routes`** — for Pages, custom domains are API-managed, not wrangler-managed; `routes` in wrangler.toml is for Workers, not Pages.
- **Attaching a domain before the Pages project has a production deployment** — the domain attach will succeed but serve a 522 error until a deployment exists.
- **Ignoring `certificate_status: "pending_validation"`** — on external DNS this status persists until the CNAME is added at the registrar.

---

## Gotchas

- Certificate issuance on Cloudflare-managed DNS typically completes within 30 seconds; on external DNS it may take up to 15 minutes pending DNS propagation.
- Removing a custom domain via the API does NOT delete the associated DNS record if the zone is Cloudflare-managed — delete the CNAME separately.
- Pages custom domains require the project to have at least one successful deployment on the `production` branch alias before the domain activates.
- The API endpoint for Pages domains is account-scoped, not zone-scoped — use the account-level API token.
- `wrangler pages deploy` does not manage custom domains; only the REST API or dashboard does.

---

## Verification

```bash
# List all domains attached to a Pages project
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/my-app-production/domains" \
  | jq '.result[] | {name, status, certificate_status}'

# Verify TLS certificate is valid
echo | openssl s_client -connect app.example.com:443 -servername app.example.com 2>/dev/null \
  | openssl x509 -noout -dates
```

---

## Related

- `cloudflare-pages-preview-deployments.md`
- `cloudflare-pages-build-cache-optimization.md`
- `wrangler-pages-direct-upload-ci.md`
- `multi-region-dns-failover-routing.md`
- `deploy-verification-smoke-tests.md`

---

## Sources

- https://developers.cloudflare.com/pages/configuration/custom-domains/
- https://api.cloudflare.com/#pages-domains-add-domain
- https://developers.cloudflare.com/pages/framework-guides/deploy-anything/
