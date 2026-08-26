# China PIPL — Cloudflare Workers Cross-Border Data Transfer Compliance

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers application serves users globally including mainland China, and you need to comply with the Personal Information Protection Law (PIPL, effective 1 November 2021). You must detect Chinese users, route their personal information to China-localized infrastructure, obtain PIPL-compliant consent for sensitive personal information (SPI), and ensure any cross-border transfer relies on a recognised legal basis filed with the Cyberspace Administration of China (CAC).

## Context

PIPL applies to processing personal information of natural persons within China, even by overseas entities. Cross-border transfer is broadly prohibited unless the controller satisfies one of three gateways: passing a CAC security assessment, executing a standard contract (SCCs issued by CAC), or obtaining a certification from a CAC-approved institution. Sensitive personal information — biometrics, religious belief, medical health, financial accounts, location, minors under 14 — requires separate explicit consent. Because Cloudflare's D1 is a globally distributed SQLite service without a China-only region, PII for CN users must not flow to D1; instead route it to a China-resident data store (e.g. Alibaba Cloud RDS in cn-hangzhou accessed via a Cloudflare Worker bound to a Hyperdrive or direct fetch).

## Detecting Chinese Users and Routing to China Data Path

```typescript
// src/pipl-router.ts
import { Env } from './types';

export async function handleRequest(request: Request, env: Env): Promise<Response> {
  const country = (request as any).cf?.country as string | undefined;
  const isChinaUser = country === 'CN';

  if (isChinaUser) {
    return handleChinaPath(request, env);
  }
  return handleGlobalPath(request, env);
}

async function handleChinaPath(request: Request, env: Env): Promise<Response> {
  // Do NOT write PII to D1 (global). Forward to China-resident backend.
  const cnBackendUrl = env.CN_BACKEND_URL; // e.g. https://api.cn.example.com
  const proxied = new Request(cnBackendUrl + new URL(request.url).pathname, {
    method: request.method,
    headers: request.headers,
    body: request.body,
  });
  const response = await fetch(proxied);
  return new Response(response.body, {
    status: response.status,
    headers: {
      ...Object.fromEntries(response.headers),
      'X-Data-Region': 'CN',
    },
  });
}

async function handleGlobalPath(request: Request, env: Env): Promise<Response> {
  // Global path — D1 is acceptable for non-CN personal data
  const result = await env.DB.prepare('SELECT 1 AS ok').first();
  return new Response(JSON.stringify({ region: 'global', db: result }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Consent Management for Sensitive Personal Information

```typescript
// src/pipl-consent.ts
export interface PIPLConsent {
  subject_id: string;
  spi_categories: string[];   // e.g. ['biometric','health','financial']
  purpose: string;
  third_party_sharing: boolean;
  cross_border_transfer: boolean;
  granted_at: string;
  withdrawn_at: string | null;
}

export async function recordConsent(
  env: Env,
  consent: Omit<PIPLConsent, 'granted_at' | 'withdrawn_at'>
): Promise<string> {
  // Stored in China-resident backend for CN users; this function is called from cnBackend
  const payload = {
    ...consent,
    granted_at: new Date().toISOString(),
    withdrawn_at: null,
  };
  const resp = await fetch(`${env.CN_BACKEND_URL}/consent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Internal-Key': env.CN_INTERNAL_KEY },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`Consent store error: ${resp.status}`);
  const data = await resp.json<{ id: string }>();
  return data.id;
}

export async function withdrawConsent(env: Env, subjectId: string): Promise<void> {
  await fetch(`${env.CN_BACKEND_URL}/consent/${subjectId}/withdraw`, {
    method: 'PATCH',
    headers: { 'X-Internal-Key': env.CN_INTERNAL_KEY },
  });
  // Trigger data deletion per PIPL Art. 47 — individual has right to deletion upon withdrawal
  await fetch(`${env.CN_BACKEND_URL}/data/${subjectId}`, {
    method: 'DELETE',
    headers: { 'X-Internal-Key': env.CN_INTERNAL_KEY },
  });
}
```

## Cross-Border Transfer Legal Bases

For any residual cross-border data flow (e.g. analytics, error reporting) involving CN user data:

| Legal Basis | When Required | Action |
|---|---|---||
| CAC Security Assessment | >1 M records/year OR SPI at scale | File assessment at https://beian.cac.gov.cn |
| Standard Contract (SCC) | Smaller volumes, no SPI | Execute CAC-issued template, file within 10 days |
| Certification | Intra-group transfers in MNCs | Obtain from CAC-approved certifier |

Store the filed contract or assessment reference in a D1 table (non-PII metadata only):

```typescript
// migrations/0002_pipl_transfer.sql
export const TRANSFER_SCHEMA = `
CREATE TABLE IF NOT EXISTS pipl_transfer_basis (
  id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  basis_type    TEXT NOT NULL CHECK(basis_type IN ('cac_assessment','standard_contract','certification')),
  filed_at      TEXT NOT NULL,
  expires_at    TEXT,
  reference_num TEXT NOT NULL,
  destination_country TEXT NOT NULL,
  data_categories TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
`;
```

## PIPL-Compliant Privacy Notice Structure

Every Workers-served application must surface a Chinese-language privacy notice before collecting any personal information. Required elements per PIPL Art. 17:

- Identity and contact of the personal information processor.
- Purpose and method of processing.
- Categories and retention period of personal information.
- Methods for individuals to exercise their rights (access, copy, correct, delete, withdraw consent).
- Cross-border transfer details if applicable.

Serve the notice as a static asset from R2 with locale detection:

```typescript
// src/privacy-notice.ts
export async function servePrivacyNotice(request: Request, env: Env): Promise<Response> {
  const country = (request as any).cf?.country as string;
  const lang = country === 'CN' ? 'zh-CN' : 'en';
  const key = `privacy-notice/${lang}.html`;
  const obj = await env.ASSETS.get(key);
  if (!obj) return new Response('Privacy notice not found', { status: 404 });
  return new Response(obj.body, {
    headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'max-age=3600' },
  });
}
```

## Anti-patterns

- **Storing CN user PII in D1 global** — D1 does not offer China-only data residency; any CN PII in D1 constitutes an unlawful cross-border transfer under PIPL.
- **Bundling SPI consent with general terms** — PIPL Art. 29 requires separate, explicit, stand-alone consent for each SPI category; checkbox-in-ToS is non-compliant.
- **Assuming GDPR adequacy covers PIPL** — PIPL has distinct requirements; a GDPR-compliant setup does not automatically satisfy PIPL's CAC filing and localisation rules.

## Gotchas

- `cf.country` reflects Cloudflare's GeoIP database; users on VPNs may appear outside CN. Apply conservative fallback: if SPI is involved and country is ambiguous, treat as CN.
- The CAC security assessment is mandatory when cumulative cross-border personal data reaches 100,000 individuals/year or SPI reaches 10,000 individuals/year (2023 thresholds).
- PIPL extraterritorial fines can reach RMB 50 million or 5% of prior-year revenue; overseas entities are added to a CAC rectification list blocking them from PRC app stores.

## Verification

```bash
# Confirm no CN-country requests are hitting D1 write paths
wrangler tail --format=json | jq 'select(.cf.country == "CN") | .url'

# Verify transfer basis records are populated
wrangler d1 execute example project-db --command \
  "SELECT basis_type, filed_at, destination_country FROM pipl_transfer_basis;"

# Test CN routing locally with a simulated CF header
curl -H 'X-Simulated-CF-Country: CN' https://your-worker.workers.dev/api/test
```

## Related

- `philippines-dpa-2012-workers-d1-data-subject-rights.md`
- `turkey-kvkk-workers-d1-personal-data-processing.md`
- `saudi-arabia-pdpl-workers-d1-consent-management.md`

## Sources

- PIPL Full Text (English) — https://www.cac.gov.cn/2021-08/20/c_1631049984640464.htm
- CAC Cross-Border Transfer Regulations 2023 — https://www.cac.gov.cn/2023-02/24/c_1679601798021831.htm
- CAC Standard Contract Template — https://www.cac.gov.cn/2023-02/24/c_1679601798021831.htm
- Cloudflare Workers cf.country docs — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
