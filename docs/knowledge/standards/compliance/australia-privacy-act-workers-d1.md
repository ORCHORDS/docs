# Australia Privacy Act 1988 (2024 Amendments) Compliance with Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application collects personal information from Australian residents. You need to comply with the Privacy Act 1988 (Cth) as amended by the Privacy and Other Legislation Amendment Act 2024, including all 13 Australian Privacy Principles (APPs), notifiable data breach obligations, and mandatory breach reporting to the Office of the Australian Information Commissioner (OAIC).

## Context

The Privacy Act 1988 applies to Australian Government agencies and private sector organisations with annual turnover exceeding AUD 3 million, plus certain other entities regardless of size (health service providers, operators of certain online platforms). The 2024 amendments introduce a statutory tort for serious invasions of privacy, enhanced enforcement powers, and a direct right of action. Workers + D1 provide an edge-first architecture that keeps data in nominated regions while supporting synchronous access controls required by APP 12.

Key APPs relevant to engineering:
- **APP 1** — open and transparent management; publish a privacy policy
- **APP 3** — collection of solicited personal information (minimisation)
- **APP 6** — use or disclosure of personal information (purpose limitation)
- **APP 11** — security of personal information
- **APP 12** — access to personal information
- **APP 13** — correction of personal information

## APP 12 — Access Endpoint (Worker querying D1)

```typescript
// workers/privacy-access.ts
import { Env } from './types';

interface AccessRequest {
  userId: string;
  requestedAt: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const { userId } = await request.json<AccessRequest>();
    if (!userId) {
      return new Response(JSON.stringify({ error: 'userId required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // APP 12: must respond within 30 days; log every request
    await env.DB.prepare(
      `INSERT INTO access_requests (user_id, requested_at, status)
       VALUES (?, datetime('now'), 'pending')`
    ).bind(userId).run();

    // Gather all personal information held about the individual
    const [profile, consents, activityLogs] = await Promise.all([
      env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(userId).first(),
      env.DB.prepare(
        'SELECT purpose, collected_at FROM consent_records WHERE user_id = ?'
      ).bind(userId).all(),
      env.DB.prepare(
        `SELECT action, occurred_at FROM audit_log
         WHERE user_id = ? ORDER BY occurred_at DESC LIMIT 200`
      ).bind(userId).all(),
    ]);

    if (!profile) {
      return new Response(JSON.stringify({ error: 'Individual not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const payload = {
      personal_information: profile,
      consent_records: consents.results,
      activity: activityLogs.results,
      held_by: 'example.com',
      act_reference: 'Privacy Act 1988 (Cth) APP 12',
    };

    await env.DB.prepare(
      `UPDATE access_requests SET status = 'fulfilled', fulfilled_at = datetime('now')
       WHERE user_id = ? AND status = 'pending'`
    ).bind(userId).run();

    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

## APP 11 — Security: D1 Field-Level Encryption

APP 11 requires reasonable steps to protect personal information from misuse, interference, loss, and unauthorised access. Use the Web Crypto API inside Workers to encrypt sensitive fields before writing to D1.

```typescript
// lib/fieldEncrypt.ts
const ALGO = { name: 'AES-GCM', length: 256 } as const;

export async function encryptField(
  plaintext: string,
  keyHex: string
): Promise<string> {
  const raw = hexToBytes(keyHex);
  const key = await crypto.subtle.importKey('raw', raw, ALGO, false, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const enc = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(plaintext)
  );
  // store iv + ciphertext as base64
  const combined = new Uint8Array(iv.byteLength + enc.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(enc), iv.byteLength);
  return btoa(String.fromCharCode(...combined));
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2)
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  return bytes;
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS users (
  id          TEXT PRIMARY KEY,
  email_enc   TEXT NOT NULL,   -- AES-GCM encrypted
  name_enc    TEXT NOT NULL,   -- AES-GCM encrypted
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  deleted_at  TEXT
);

CREATE TABLE IF NOT EXISTS access_requests (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  fulfilled_at TEXT,
  status       TEXT NOT NULL DEFAULT 'pending'
);
```

## Notifiable Data Breaches (NDB) Scheme — APP 1 & Reporting Endpoint

Under Part IIIC of the Privacy Act, entities must notify the OAIC and affected individuals of an eligible data breach (unauthorised access/disclosure likely to result in serious harm). The notification to OAIC must include: entity name, description of breach, kinds of information involved, and steps taken.

```typescript
// workers/breach-notify.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('405', { status: 405 });

    const body = await request.json<{
      description: string;
      affectedCount: number;
      dataCategories: string[];
      discoveredAt: string;
    }>();

    // Log breach internally
    await env.DB.prepare(
      `INSERT INTO breach_log
         (description, affected_count, data_categories, discovered_at, reported_at)
       VALUES (?, ?, ?, ?, datetime('now'))`
    ).bind(
      body.description,
      body.affectedCount,
      JSON.stringify(body.dataCategories),
      body.discoveredAt
    ).run();

    // Notify OAIC via their online NDB notification form API (stub)
    await fetch('https://www.oaic.gov.au/api/ndb-notify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entity: 'example.com',
        ...body,
      }),
    });

    return new Response(JSON.stringify({ status: 'notified' }), {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

## Anti-patterns

- Storing unencrypted sensitive fields (health, financial) directly in D1 text columns — violates APP 11.
- Failing to log APP 12 access requests; the OAIC expects evidence of compliance during audits.
- Using a single encryption key across all records; rotate keys and store key IDs alongside ciphertext.
- Delaying NDB notifications beyond 30 days of becoming aware of an eligible breach.
- Collecting more personal information than is reasonably necessary (APP 3 minimisation).

## Gotchas

- The 2024 amendments introduce a **direct right of action** for individuals — class actions become viable; budget for legal exposure.
- APP 8 imposes obligations when disclosing personal information to overseas recipients, even to Cloudflare's non-Australian edge nodes. Rely on adequacy or contractual protections.
- D1 currently stores data in Cloudflare's global network; use `--location` flag or location hints to pin replicas to Australian regions where possible.
- The OAIC can issue civil penalty orders up to AUD 50 million for serious or repeated interferences with privacy.

## Verification

```bash
# Confirm access request is logged
wrangler d1 execute example project-db --command \
  "SELECT * FROM access_requests ORDER BY requested_at DESC LIMIT 5;"

# Confirm breach log
wrangler d1 execute example project-db --command \
  "SELECT * FROM breach_log ORDER BY reported_at DESC LIMIT 5;"

# Smoke-test access endpoint
curl -X POST https://privacy.example.com/access \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u_001"}'
```

## Related

- `documentation/docs/policies/compliance/south-korea-pipa-workers-d1-consent.md`
- `documentation/docs/policies/compliance/canada-pipeda-workers-d1-breach.md`
- `documentation/docs/policies/compliance/indonesia-pdp-law-workers-d1.md`
- `documentation/docs/policies/compliance/hong-kong-pdpo-workers-d1.md`

## Sources

- Privacy Act 1988 (Cth): https://www.legislation.gov.au/Details/C2022C00361
- Privacy and Other Legislation Amendment Act 2024
- OAIC Australian Privacy Principles guidelines: https://www.oaic.gov.au/privacy/australian-privacy-principles-guidelines
- Notifiable Data Breaches scheme: https://www.oaic.gov.au/privacy/notifiable-data-breaches
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
