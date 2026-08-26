# EU Cyber Resilience Act — SBOM Requirements and Workers CI/CD Pipeline

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Generating and Publishing SBOMs for CRA-Regulated Connected Products

The EU Cyber Resilience Act (Regulation 2024/2847, applicable from December 2027 for most provisions) mandates that manufacturers of products with digital elements — including cloud-connected software — generate and maintain a software bill of materials (SBOM) in a machine-readable format (Article 13(3)). The SBOM must enumerate all third-party and open-source components, their versions, and known vulnerabilities. Manufacturers must also disclose actively exploited vulnerabilities to ENISA within 24 hours and publish security advisories via a coordinated vulnerability disclosure (CVD) process.

Workers-based SaaS qualifies as a "software product" under Annex I class A (default category) when it is placed on the EU market as a standalone product. The obligation applies to the software delivered to users, not the infrastructure itself. This means the SBOM must cover the Worker bundle's npm dependency graph and any WASM modules bundled into the deployment artefact.

The practical architecture integrates SBOM generation into the GitHub Actions CI pipeline using `syft` and `grype`, publishes the resulting CycloneDX JSON to a Cloudflare R2 bucket with a versioned path, and keeps a D1 table of vulnerability scan results for evidence purposes. A scheduled Worker polls the OSV.dev API daily to detect newly disclosed CVEs against pinned component versions and triggers the 24-hour ENISA notification workflow when an actively exploited vulnerability is found.

## Context

- Runtime: Cloudflare Workers (ES modules, WASM optional)
- CI/CD: GitHub Actions
- Storage: R2 (SBOM artefacts), D1 (CVE evidence)
- SBOM Format: CycloneDX 1.6 JSON
- Tools: syft (SBOM generation), grype (vulnerability scanning), osv-scanner
- Regulation: EU Cyber Resilience Act (Regulation 2024/2847), Articles 13, 14, Annex I

## GitHub Actions SBOM Generation

The pipeline runs on every push to main and on every release tag. `syft` scans the `node_modules` directory after `npm ci`, producing a CycloneDX JSON. `grype` then audits the SBOM for known CVEs. The artefact is uploaded to R2 under a path that encodes the commit SHA and build number.

```yaml
# .github/workflows/sbom.yml
name: SBOM Generation and Vulnerability Scan

on:
  push:
    branches: [main]
  release:
    types: [published]

jobs:
  sbom:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write  # for OIDC R2 upload

    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Install syft and grype
        run: |
          curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin
          curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin

      - name: Generate SBOM (CycloneDX JSON)
        run: |
          syft dir:. \
            --output cyclonedx-json=sbom.cdx.json \
            --config .syft.yaml

      - name: Scan SBOM for vulnerabilities
        id: grype
        run: |
          grype sbom:sbom.cdx.json \
            --output json \
            --file grype-results.json \
            --fail-on critical || echo "CRITICAL_VULNS=true" >> $GITHUB_ENV

      - name: Upload SBOM to R2
        env:
          R2_ACCESS_KEY: ${{ secrets.R2_ACCESS_KEY }}
          R2_SECRET_KEY: ${{ secrets.R2_SECRET_KEY }}
          R2_BUCKET: cra-sbom-artefacts
          R2_ENDPOINT: ${{ secrets.R2_ENDPOINT }}
        run: |
          aws s3 cp sbom.cdx.json \
            s3://$R2_BUCKET/sbom/${{ github.sha }}/sbom.cdx.json \
            --endpoint-url $R2_ENDPOINT
          aws s3 cp grype-results.json \
            s3://$R2_BUCKET/sbom/${{ github.sha }}/grype-results.json \
            --endpoint-url $R2_ENDPOINT

      - name: Record scan in D1
        if: always()
        env:
          D1_API: ${{ secrets.D1_API_ENDPOINT }}
          D1_TOKEN: ${{ secrets.D1_API_TOKEN }}
        run: |
          curl -X POST "$D1_API/record-scan" \
            -H "Authorization: Bearer $D1_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"sha\":\"${{ github.sha }}\",\"sbomPath\":\"sbom/${{ github.sha }}/sbom.cdx.json\",\"criticalVulns\":\"${CRITICAL_VULNS:-false}\"}"

      - name: Fail on critical CVEs (CRA Article 13 — no known exploited vulnerabilities at release)
        if: env.CRITICAL_VULNS == 'true'
        run: exit 1
```

## D1 Vulnerability Evidence Store

The D1 schema stores scan results and tracks the status of any CVE that requires ENISA notification or vendor coordination. The `enisa_notified_at` column records when the 24-hour mandatory notification was dispatched.

```ts
// src/handlers/record-scan.ts
import { Env } from '../types';

interface ScanPayload {
  sha: string;
  sbomPath: string;
  criticalVulns: string;
}

export async function recordScan(req: Request, env: Env): Promise<Response> {
  const body = await req.json<ScanPayload>();
  const now = new Date().toISOString();

  await env.DB.prepare(
    `INSERT INTO sbom_scans (commit_sha, sbom_path, scanned_at, has_critical_vulns)
     VALUES (?, ?, ?, ?)`
  ).bind(body.sha, body.sbomPath, now, body.criticalVulns === 'true' ? 1 : 0).run();

  return Response.json({ recorded: true, scannedAt: now });
}
```

```sql
-- D1 schema: cra_compliance.sql
CREATE TABLE IF NOT EXISTS sbom_scans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  commit_sha TEXT NOT NULL,
  sbom_path TEXT NOT NULL,
  scanned_at TEXT NOT NULL,
  has_critical_vulns INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cve_findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  commit_sha TEXT NOT NULL,
  cve_id TEXT NOT NULL,
  severity TEXT NOT NULL,
  package_name TEXT NOT NULL,
  package_version TEXT NOT NULL,
  fixed_in TEXT,
  actively_exploited INTEGER NOT NULL DEFAULT 0,
  enisa_notified_at TEXT,
  remediated_at TEXT,
  detected_at TEXT NOT NULL
);
```

## Scheduled OSV.dev CVE Watcher Worker

A nightly Worker queries the OSV.dev batch API with the current production dependency list extracted from the latest SBOM scan. If any newly disclosed CVE is flagged `is_malicious` or has EPSS score above 0.7 (a proxy for active exploitation), the Worker inserts a `cve_findings` row and enqueues the ENISA notification job.

```ts
// src/scheduled/cve-watcher.ts
interface OsvPackage { name: string; version: string; ecosystem: string }
interface OsvResponse { vulns?: Array<{ id: string; severity?: Array<{ type: string; score: string }> }> }

export async function checkOsvBatch(env: Env, packages: OsvPackage[]): Promise<void> {
  const res = await fetch('https://api.osv.dev/v1/querybatch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ queries: packages.map(p => ({ package: p })) }),
  });
  const data = await res.json<{ results: OsvResponse[] }>();
  const now = new Date().toISOString();

  const stmts = [];
  for (let i = 0; i < packages.length; i++) {
    const pkg = packages[i];
    const vulns = data.results[i]?.vulns ?? [];
    for (const vuln of vulns) {
      const critical = vuln.severity?.some(s => s.type === 'CVSS_V3' && parseFloat(s.score) >= 9.0);
      stmts.push(env.DB.prepare(
        `INSERT OR IGNORE INTO cve_findings
         (commit_sha, cve_id, severity, package_name, package_version, actively_exploited, detected_at)
         VALUES (
           (SELECT commit_sha FROM sbom_scans ORDER BY scanned_at DESC LIMIT 1),
           ?, ?, ?, ?, ?, ?
         )`
      ).bind(vuln.id, critical ? 'CRITICAL' : 'HIGH', pkg.name, pkg.version, critical ? 1 : 0, now));

      if (critical) {
        await env.NOTIFICATION_QUEUE.send({
          type: 'ENISA_24H_NOTIFICATION',
          cveId: vuln.id,
          packageName: pkg.name,
          packageVersion: pkg.version,
          detectedAt: now,
        });
      }
    }
  }
  if (stmts.length > 0) await env.DB.batch(stmts);
}
```

## SBOM Public Disclosure Endpoint

CRA Article 13(3) requires SBOMs to be available to market surveillance authorities and, for open-source products, to the public. The Worker exposes a stable URL that returns the SBOM for the current production release from R2.

```ts
// src/handlers/sbom-disclosure.ts
export async function getSbom(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);
  const sha = url.searchParams.get('sha') ?? 'latest';

  let path: string;
  if (sha === 'latest') {
    const row = await env.DB.prepare(
      `SELECT sbom_path FROM sbom_scans ORDER BY scanned_at DESC LIMIT 1`
    ).first<{ sbom_path: string }>();
    if (!row) return new Response('No SBOM available', { status: 404 });
    path = row.sbom_path;
  } else {
    path = `sbom/${sha}/sbom.cdx.json`;
  }

  const obj = await env.R2_BUCKET.get(path);
  if (!obj) return new Response('Not found', { status: 404 });

  return new Response(obj.body, {
    headers: {
      'Content-Type': 'application/vnd.cyclonedx+json',
      'Content-Disposition': 'attachment; filename="sbom.cdx.json"',
      'Cache-Control': 'public, max-age=3600',
    },
  });
}
```

## Anti-patterns

- Generating the SBOM from `package.json` instead of from the locked `node_modules` tree — the lockfile-resolved graph is what actually ships; `package.json` ranges can differ.
- Suppressing grype findings with blanket ignore rules to keep CI green — suppressions must be individually documented as accepted risks in the CVE findings table.
- Publishing SBOMs only at major releases — CRA requires the SBOM to reflect the product as placed on the market, meaning every release that updates a dependency needs a fresh SBOM.
- Conflating SBOM generation with vulnerability remediation — the SBOM records facts; remediation status belongs in the `cve_findings` table separately.

## Gotchas

- Workers bundles produced by `wrangler build` may tree-shake dependencies; run syft on the pre-bundle `node_modules` for completeness, but also scan the final bundle artefact.
- CRA Article 14 requires ENISA notification within 24 hours of becoming aware of an actively exploited vulnerability — the clock starts at detection, not at disclosure.
- The CRA distinguishes "manufacturers" (who place the product on the market) from "distributors"; if you white-label a third-party Worker, your SBOM obligations cascade to include their components.
- OSV.dev does not cover all NVD CVEs; supplement with the GitHub Advisory Database and npm audit for full coverage.

## Verification

```ts
// tests/cve-watcher.spec.ts
import { expect, test, vi } from 'vitest';

test('critical CVE triggers ENISA notification queue', async () => {
  const env = getMiniflareEnv();
  vi.stubGlobal('fetch', async () => new Response(JSON.stringify({
    results: [{ vulns: [{ id: 'CVE-2025-99999', severity: [{ type: 'CVSS_V3', score: '9.8' }] }] }]
  })));

  const sentMessages: unknown[] = [];
  env.NOTIFICATION_QUEUE.send = async (msg: unknown) => { sentMessages.push(msg); };

  await checkOsvBatch(env, [{ name: 'example-pkg', version: '1.0.0', ecosystem: 'npm' }]);

  expect(sentMessages).toHaveLength(1);
  expect((sentMessages[0] as any).type).toBe('ENISA_24H_NOTIFICATION');
});
```

## Related

- [eu-cyber-resilience-act-cra-software.md](eu-cyber-resilience-act-cra-software.md)
- [eu-cyber-resilience-act-product-security-lifecycle.md](eu-cyber-resilience-act-product-security-lifecycle.md)
- [eu-cyber-resilience-act-vulnerability-reporting-readiness.md](eu-cyber-resilience-act-vulnerability-reporting-readiness.md)
- [sbom-generation-distribution-cicd.md](sbom-generation-distribution-cicd.md)
- [open-source-license-compliance-scanning.md](open-source-license-compliance-scanning.md)

## Sources

- EU Cyber Resilience Act (Regulation 2024/2847): https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202402847
- CycloneDX Specification 1.6: https://cyclonedx.org/specification/overview/
- Anchore Syft: https://github.com/anchore/syft
- Anchore Grype: https://github.com/anchore/grype
- OSV.dev API: https://osv.dev/docs/
- ENISA Vulnerability Disclosure: https://www.enisa.europa.eu/topics/vulnerability-disclosure
