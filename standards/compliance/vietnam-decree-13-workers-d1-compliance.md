# Vietnam Decree 13 Personal Data Protection on Cloudflare Workers and D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project serves Vietnamese users who are subject to Decree 13/2023/ND-CP on Personal Data Protection (PDPD), effective 1 July 2023. The decree is enforced by the Ministry of Public Security (MPS) Department of Cybersecurity and Hi-Tech Crime Prevention (A05). Non-compliant platforms may be blocked, fined up to VND 100 million per violation, and required to localise sensitive personal data on Vietnamese infrastructure. An anonymous social platform must obtain two-tier consent (basic vs. sensitive), honour deletion and portability requests, and report breaches to A05 within 72 hours.

## Context

Decree 13 distinguishes *basic personal data* (name, DOB, phone, email, address, IP) from *sensitive personal data* (health, biometrics, political views, location precision). Sensitive data processing requires written, express consent and carries stricter transfer restrictions. The decree requires platforms to appoint a Personal Data Protection Department (PDPD) officer and register their processing activities with A05 before July 2024. Cloudflare D1 is used as the primary store for Vietnamese user records; Workers enforce consent at request time and fan out rights requests through Queues.

## Decree 13 Overview — Data Classification and D1 Schema

Decree 13 Art. 2 mandates that basic and sensitive personal data be tracked separately. The D1 schema enforces this at the column level to simplify audit queries.

```typescript
// D1 schema — run via wrangler d1 execute
const VN_SCHEMA = `
CREATE TABLE IF NOT EXISTS vn_user_data (
  user_id        TEXT PRIMARY KEY,
  pseudonym      TEXT NOT NULL,
  -- Basic personal data (Art. 2(1))
  email          TEXT,
  phone          TEXT,
  ip_last        TEXT,
  -- Sensitive personal data (Art. 2(2)) — encrypted at rest
  health_data    TEXT,
  location_fine  TEXT,
  created_at     INTEGER NOT NULL,
  country_code   TEXT NOT NULL DEFAULT 'VN',
  active         INTEGER NOT NULL DEFAULT 1,
  deleted_at     INTEGER
);

CREATE TABLE IF NOT EXISTS vn_consent (
  user_id       TEXT NOT NULL,
  data_type     TEXT NOT NULL,   -- 'basic' | 'sensitive'
  purpose       TEXT NOT NULL,
  granted       INTEGER NOT NULL DEFAULT 0,
  granted_at    INTEGER,
  revoked_at    INTEGER,
  express_form  TEXT,            -- reference to signed consent form for sensitive
  PRIMARY KEY (user_id, data_type, purpose)
);

CREATE TABLE IF NOT EXISTS vn_rights_log (
  request_id  TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  right_type  TEXT NOT NULL,
  received_at INTEGER NOT NULL,
  resolved_at INTEGER,
  status      TEXT
);
`;
```

## Data Subject Rights Implementation

Decree 13 Art. 9–16 grant data subjects rights to access, correct, delete, restrict, object, and port their data. The platform must respond within 72 hours for deletion requests and 30 days for all other rights.

```typescript
// workers/vn-rights.ts
export interface Env {
  DB: D1Database;
  VN_RIGHTS_QUEUE: Queue;
  VN_AUDIT_KV: KVNamespace;
}

type VNRight = "access" | "correct" | "delete" | "restrict" | "object" | "portability";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { user_id, right, payload } = await request.json<{
      user_id: string;
      right: VNRight;
      payload?: Record<string, unknown>;
    }>();

    const requestId = crypto.randomUUID();
    const now = Date.now();

    await env.DB.prepare(
      `INSERT INTO vn_rights_log (request_id, user_id, right_type, received_at)
       VALUES (?, ?, ?, ?)`
    ).bind(requestId, user_id, right, now).run();

    // Dispatch to Queue — deletion SLA is 72h, others 30 days
    await env.VN_RIGHTS_QUEUE.send({ requestId, user_id, right, payload, receivedAt: now });

    const sla = right === "delete" ? "72 hours" : "30 days";
    return new Response(
      JSON.stringify({ request_id: requestId, sla, message: `Request received. Response within ${sla}.` }),
      { status: 202, headers: { "Content-Type": "application/json" } }
    );
  },
};

// Queue consumer
export async function consumeVNRights(
  batch: MessageBatch<{
    requestId: string;
    user_id: string;
    right: VNRight;
    payload?: Record<string, unknown>;
  }>,
  env: Env
): Promise<void> {
  for (const msg of batch.messages) {
    const { requestId, user_id, right, payload } = msg.body;
    try {
      let status = "fulfilled";

      if (right === "delete") {
        await env.DB.prepare(
          `UPDATE vn_user_data SET
             email = NULL, phone = NULL, ip_last = NULL,
             health_data = NULL, location_fine = NULL,
             active = 0, deleted_at = ?
           WHERE user_id = ? AND country_code = 'VN'`
        ).bind(Date.now(), user_id).run();
        await env.DB.prepare(
          `UPDATE vn_consent SET granted = 0, revoked_at = ? WHERE user_id = ?`
        ).bind(Date.now(), user_id).run();
      } else if (right === "correct" && payload) {
        const allowed = ["email", "phone"] as const;
        for (const field of allowed) {
          if (field in payload) {
            await env.DB.prepare(
              `UPDATE vn_user_data SET ${field} = ? WHERE user_id = ? AND country_code = 'VN'`
            ).bind(payload[field], user_id).run();
          }
        }
      } else if (right === "portability") {
        const rows = await env.DB.prepare(
          `SELECT user_id, pseudonym, email, phone, created_at
           FROM vn_user_data WHERE user_id = ? AND country_code = 'VN'`
        ).bind(user_id).all();
        status = `portability_export_ready:${JSON.stringify(rows.results)}`;
      }

      await env.DB.prepare(
        `UPDATE vn_rights_log SET resolved_at = ?, status = ?
         WHERE request_id = ?`
      ).bind(Date.now(), status, requestId).run();

      msg.ack();
    } catch {
      msg.retry();
    }
  }
}
```

## Consent Management — Two-Tier Consent for Basic vs. Sensitive Data

Decree 13 Art. 11 requires that consent be voluntary, specific, informed, and clear. For sensitive data (Art. 2(2)), written express consent is required. example project collects only pseudonymous device tokens by default; any enrichment triggers the appropriate tier.

```typescript
// workers/vn-consent.ts
export interface VNConsentPayload {
  user_id: string;
  data_type: "basic" | "sensitive";
  purpose: string;
  express_form_ref?: string; // Required for sensitive data
}

export async function recordVNConsent(
  consent: VNConsentPayload,
  db: D1Database
): Promise<void> {
  if (consent.data_type === "sensitive" && !consent.express_form_ref) {
    throw new Error(
      "Decree 13 Art. 11: sensitive personal data requires express written consent. " +
      "Provide express_form_ref before granting consent."
    );
  }

  await db.prepare(
    `INSERT INTO vn_consent
       (user_id, data_type, purpose, granted, granted_at, express_form)
     VALUES (?, ?, ?, 1, ?, ?)
     ON CONFLICT(user_id, data_type, purpose) DO UPDATE SET
       granted = 1,
       granted_at = excluded.granted_at,
       revoked_at = NULL,
       express_form = excluded.express_form`
  ).bind(
    consent.user_id,
    consent.data_type,
    consent.purpose,
    Date.now(),
    consent.express_form_ref ?? null
  ).run();
}

export async function hasVNConsent(
  userId: string,
  dataType: "basic" | "sensitive",
  purpose: string,
  db: D1Database
): Promise<boolean> {
  const row = await db.prepare(
    `SELECT 1 FROM vn_consent
     WHERE user_id = ? AND data_type = ? AND purpose = ?
       AND granted = 1 AND revoked_at IS NULL`
  ).bind(userId, dataType, purpose).first();
  return row !== null;
}
```

## Breach Notification

Decree 13 Art. 23 requires notification to A05 within 72 hours of discovering a breach. The notification must include the nature of the breach, categories and estimated volume of affected data, and remediation measures. A KV sentinel prevents double notification.

```typescript
// workers/vn-breach-notify.ts
export interface Env {
  BREACH_KV: KVNamespace;
  DB: D1Database;
  A05_API_KEY: string;
}

export async function notifyA05(
  breachId: string,
  details: {
    nature: string;
    data_categories: ("basic" | "sensitive")[];
    estimated_subjects: number;
    discovery_time: string;
    measures: string;
  },
  env: Env
): Promise<void> {
  const key = `vn_breach:${breachId}`;
  if (await env.BREACH_KV.get(key)) return;

  await env.BREACH_KV.put(key, JSON.stringify({ notified_at: Date.now() }), {
    expirationTtl: 30 * 86400,
  });

  // A05 reporting portal — confirm current URL with MPS
  const resp = await fetch("https://cibernet.gov.vn/api/pdpd/breach", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": env.A05_API_KEY,
    },
    body: JSON.stringify({
      breach_id: breachId,
      platform: "example.com",
      jurisdiction: "VN",
      notified_at: new Date().toISOString(),
      ...details,
    }),
  });

  if (!resp.ok) {
    await env.BREACH_KV.delete(key);
    throw new Error(`A05 breach notification failed: ${resp.status}`);
  }
}
```

## Anti-patterns

- Treating basic and sensitive personal data identically — Decree 13 imposes stricter obligations on sensitive data; the schema and consent tier must reflect this distinction.
- Storing Vietnamese user data outside Vietnam without MPS approval — Decree 13 Art. 25 requires cross-border transfer assessment and MPS notification 60 days before the first transfer.
- Sending a breach notification without the required 72-hour timestamp — A05 checks the reported discovery time against the notification time; automate discovery timestamping in your detection pipeline.
- Allowing consent withdrawal without immediate effect — Decree 13 Art. 9 mandates that consent withdrawal stops processing immediately; revocation must propagate to all active processing pipelines.
- Ignoring the PDPD officer registration requirement — platforms must register their data processing activities with A05; failure is an independent violation regardless of data practices.

## Gotchas

- The 72-hour deletion SLA under Decree 13 is stricter than GDPR's "without undue delay" standard — clock it from request receipt, not from verification completion.
- Vietnamese working days exclude public holidays and Tet; if SLA calculations are business-day based (for rights requests other than deletion), use a Vietnamese calendar library.
- Cross-border data transfer restrictions under Decree 13 differ from GDPR Standard Contractual Clauses — MPS approval or binding corporate rules may be required; SCCs alone are insufficient.
- D1 replication across regions may route Vietnamese user data through non-VN Cloudflare nodes; review Cloudflare's data residency options (Jurisdictions) for sensitive data fields.

## Verification

1. POST `right: "delete"` for a VN user; confirm `vn_user_data.active = 0`, `deleted_at` set, and consent revoked within 72-hour test window.
2. Call `recordVNConsent` with `data_type: "sensitive"` without `express_form_ref`; confirm it throws.
3. Call `hasVNConsent` after revocation; confirm it returns `false`.
4. Call `notifyA05` twice with the same `breachId`; confirm A05 endpoint called exactly once.
5. Run `SELECT * FROM vn_rights_log` and verify `resolved_at` is populated after Queue processing.

## Related

- [Vietnam PDPD Workers Queues](vietnam-pdpd-workers-queues.md)
- [GDPR Breach Notification 72h](gdpr-breach-notification-72h.md)
- [Data Retention Automated Deletion Workers](data-retention-automated-deletion-workers.md)
- [Cross-Border Data Transfer Cloudflare Workers](cross-border-data-transfer-cloudflare-workers.md)
- [Singapore PDPA Workers D1](singapore-pdpa-workers-d1.md)

## Sources

- Decree 13/2023/ND-CP (Vietnamese): https://vanban.chinhphu.vn/?pageid=27160&docid=205919
- English translation overview (DFDL): https://www.dfdl.com/resources/legal-and-tax-updates/vietnam-personal-data-protection-decree-13
- MPS Department A05: https://www.mps.gov.vn/
- Cloudflare D1 Jurisdictions: https://developers.cloudflare.com/d1/reference/data-location/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
