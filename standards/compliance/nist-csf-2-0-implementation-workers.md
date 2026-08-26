# NIST CSF 2.0 Implementation on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your engineering team needs to operationalise NIST Cybersecurity Framework 2.0 (February 2024) controls in a Cloudflare Workers architecture — specifically the six Functions: Govern, Identify, Protect, Detect, Respond, Recover — with automated evidence collection for assessors.

## Context

NIST CSF 2.0 introduces a new sixth Function, **Govern** (GV), which anchors the other five to organisational policies, roles, and supply-chain risk management. Unlike CSF 1.1, CSF 2.0 is explicitly applicable to all sectors and organisation sizes. Workers implement the *technical* slice of each Function: asset discovery via Durable Objects, continuous detection via Tail Workers, and recovery automation via Cron Triggers. Existing `nist-csf-2-mapping.md` covers control-to-category mapping; this article covers runtime implementation.

---

## 1. GOVERN (GV) — Policy Enforcement via Worker Config

GV.OC-01 requires organisational cybersecurity policy to be communicated and enforced. Implement a policy-as-config pattern using KV.

```typescript
// src/govern-policy.ts
interface CsfPolicy {
  version: string;
  effectiveDate: string;
  tlsMinVersion: 'TLSv1.2' | 'TLSv1.3';
  allowedCountries: string[];   // ISO 3166-1 alpha-2; empty = unrestricted
  maxSessionAgeSeconds: number;
  requireMfa: boolean;
}

export async function loadPolicy(kv: KVNamespace): Promise<CsfPolicy> {
  const raw = await kv.get('csf:policy:current', { type: 'json' }) as CsfPolicy | null;
  if (!raw) throw new Error('CSF policy not initialised — check GV.OC-01 controls');
  return raw;
}

export async function enforceGeoPolicy(
  request: Request,
  policy: CsfPolicy
): Promise<Response | null> {
  if (policy.allowedCountries.length === 0) return null;
  const country = (request.cf as { country?: string })?.country ?? '';
  if (!policy.allowedCountries.includes(country)) {
    return new Response('GV.OC: Access restricted by organisational policy', { status: 403 });
  }
  return null;
}
```

---

## 2. IDENTIFY (ID) — Asset Inventory via Durable Objects

ID.AM-01 requires a current inventory of hardware and software assets. Use Durable Objects to maintain a live asset register.

```typescript
// src/identify-assets.ts
export class AssetRegistry {
  private state: DurableObjectState;
  constructor(state: DurableObjectState) { this.state = state; }

  async fetch(request: Request): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (request.method === 'POST' && pathname === '/register') {
      const asset = await request.json<{
        assetId: string; assetType: string; owner: string; criticality: 'low'|'medium'|'high';
      }>();
      await this.state.storage.put(`asset:${asset.assetId}`, {
        ...asset, registeredAt: new Date().toISOString()
      });
      return new Response('registered', { status: 201 });
    }
    if (request.method === 'GET' && pathname === '/list') {
      const assets = await this.state.storage.list({ prefix: 'asset:' });
      return Response.json(Object.fromEntries(assets));
    }
    return new Response('Not found', { status: 404 });
  }
}
```

---

## 3. PROTECT (PR) — Data Security Controls

PR.DS-01 (data-at-rest protection) and PR.DS-02 (data-in-transit) are implemented via encryption headers and R2 server-side encryption.

```typescript
// src/protect-data.ts
export function addProtectHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  // PR.DS-02: enforce TLS and prevent content sniffing
  headers.set('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload');
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'");
  headers.set('X-Frame-Options', 'DENY');
  headers.set('X-CSF-Control', 'PR.DS-01,PR.DS-02');
  return new Response(response.body, { status: response.status, headers });
}

export async function storeEncryptedAsset(
  bucket: R2Bucket,
  key: string,
  data: ArrayBuffer,
  encryptionKey: CryptoKey
): Promise<void> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    encryptionKey,
    data
  );
  const blob = new Uint8Array([...iv, ...new Uint8Array(ciphertext)]);
  await bucket.put(key, blob, { customMetadata: { csfControl: 'PR.DS-01', encrypted: 'AES-GCM-256' } });
}
```

---

## 4. DETECT (DE) — Tail Worker Anomaly Detection

DE.CM-01 requires monitoring of networks and assets. Tail Workers receive every request/response pair for anomaly detection without adding latency.

```typescript
// src/detect-tail.ts
// Deployed as a Tail Worker — receives TraceItem[] after request completes
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      if (event.event?.response?.status === undefined) continue;
      const status = event.event.response.status;
      const path = (event.event.request?.url ?? '');

      // DE.CM-01: detect unusual 4xx/5xx bursts
      if (status >= 400) {
        await env.ANOMALY_QUEUE.send({
          csfControl: 'DE.CM-01',
          type: status >= 500 ? 'SERVER_ERROR' : 'CLIENT_ERROR',
          url: path,
          status,
          timestamp: new Date(event.eventTimestamp).toISOString(),
          scriptName: event.scriptName,
        });
      }
    }
  }
};
```

---

## 5. RESPOND (RS) — Incident Playbook Trigger

RS.MA-01 requires incident management processes. Use Queues to trigger structured playbook steps when anomalies are confirmed.

```typescript
// src/respond-incident.ts
interface Incident {
  incidentId: string;
  severity: 'P1' | 'P2' | 'P3';
  csfCategory: string;   // e.g. 'DE.CM-01'
  description: string;
  detectedAt: string;
  assignee: string | null;
}

export async function openIncident(
  db: D1Database,
  queue: Queue,
  incident: Incident
): Promise<void> {
  await db.prepare(`
    INSERT INTO csf_incidents
      (incident_id, severity, csf_category, description, detected_at, status)
    VALUES (?, ?, ?, ?, ?, 'open')
  `).bind(
    incident.incidentId, incident.severity, incident.csfCategory,
    incident.description, incident.detectedAt
  ).run();
  // RS.MA-01: route to playbook queue
  await queue.send({ type: 'INCIDENT_OPENED', ...incident });
}
```

---

## 6. RECOVER (RC) — Automated Recovery Verification Cron

RC.RP-01 requires recovery plans to be tested. A Cron Trigger validates backup integrity and writes a recovery-test record.

```typescript
// src/recover-cron.ts
// wrangler.toml: crons = ["0 2 * * 0"]  (weekly, Sunday 02:00 UTC)
export async function runRecoveryTest(
  db: D1Database,
  bucket: R2Bucket
): Promise<void> {
  const probe = await bucket.head('backups/latest.tar.gz.enc');
  const status = probe ? 'backup_present' : 'backup_missing';
  await db.prepare(`
    INSERT INTO csf_recovery_tests (tested_at, result, csf_control)
    VALUES (?, ?, 'RC.RP-01')
  `).bind(new Date().toISOString(), status).run();
  if (status === 'backup_missing') {
    throw new Error('RC.RP-01: Recovery backup missing — incident required');
  }
}
```

---

## Anti-patterns

- **Mapping CSF Categories to single Workers** — CSF controls span process and technology; do not conflate a Workers implementation with full control satisfaction.
- **Skipping GV (Govern) implementation** — CSF 2.0 explicitly states Govern is foundational; policy gaps invalidate downstream control claims.
- **Storing CSF evidence only in Tail Worker logs** — Logpush destinations (R2, D1) must retain evidence for the assessment period (typically 12 months).
- **Treating CSF as a checklist** — CSF is a risk-based framework; your organisation Profile and Target Profile must justify control selection.

---

## Gotchas

- Tail Workers run after the response is sent; anomaly signals are asynchronous — do not use them for synchronous access decisions.
- Durable Object storage has a 128 KiB per-value limit; for large asset inventories, store asset IDs in DO and full records in D1.
- CSF 2.0 Profiles and Tiers are new concepts: document your Current Profile and Target Profile before implementation to scope the gap.
- NIST CSF 2.0 is a voluntary framework; sector-specific regulations (HIPAA, FISMA, DORA) may mandate specific controls regardless of CSF tier.

---

## Verification

```bash
# Check policy version in KV
wrangler kv key get --binding KV_NAMESPACE csf:policy:current

# Count open incidents by severity
wrangler d1 execute CSF_DB --command \
  "SELECT severity, COUNT(*) as n FROM csf_incidents WHERE status='open' GROUP BY severity"

# Verify recovery test results
wrangler d1 execute CSF_DB --command \
  "SELECT tested_at, result FROM csf_recovery_tests ORDER BY tested_at DESC LIMIT 5"

# List asset registry
curl https://asset-registry.<account>.workers.dev/list
```

---

## Related

- `nist-csf-2-mapping.md`
- `nist-800-53-control-families.md`
- `iso-27001-continuous-monitoring-automation-workers-d1.md`
- `fisma-compliance-controls-workers.md`
- `nis2-article-21-technical-measures-workers.md`

---

## Sources

- NIST CSF 2.0 — https://doi.org/10.6028/NIST.CSWP.29
- NIST CSF 2.0 Quick Start Guide — https://www.nist.gov/cyberframework/getting-started
- Cloudflare Tail Workers — https://developers.cloudflare.com/workers/observability/tail-workers/
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
