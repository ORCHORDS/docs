# Colombia Habeas Data Compliance on Cloudflare Workers and D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project operates in Colombia where Law 1581 of 2012 (Habeas Data statute) and its regulatory decrees grant Colombian residents a constitutional right to know, update, correct, and suppress personal data held by any entity. The Superintendencia de Industria y Comercio (SIC) can fine processors up to 2,000 SMMLV (~COP 2.3 billion in 2025) for violations. An anonymous social platform must honour data-subject requests within statutory deadlines (10 business days to confirm receipt; 15 business days to resolve) without inadvertently de-anonymising other users.

## Context

Colombia's habeas data framework pre-dates GDPR and carries a distinct taxonomy: *datos sensibles* (sensitive data requiring express consent), *datos semiprivados*, and *datos privados*. The SIC issues binding circulars that apply to platforms serving Colombian users regardless of where they are incorporated. Cloudflare D1 provides the primary store for Colombian user records; Workers handle rights-request routing, consent capture, and audit logging through a Queues-backed pipeline.

## Colombian Data Classification — D1 Schema

Decree 1377 of 2013 requires that personal data be classified at collection time. The D1 schema must distinguish sensitive data and track the legal basis for each processing purpose separately.

```typescript
// Schema: run via wrangler d1 execute
const SCHEMA = `
CREATE TABLE IF NOT EXISTS co_user_data (
  user_id      TEXT PRIMARY KEY,
  pseudonym    TEXT NOT NULL,
  email        TEXT,                  -- dato privado
  phone        TEXT,                  -- dato privado
  bio          TEXT,                  -- dato semiprivado
  created_at   INTEGER NOT NULL,
  country_code TEXT NOT NULL DEFAULT 'CO',
  active       INTEGER NOT NULL DEFAULT 1,
  deleted_at   INTEGER
);

CREATE TABLE IF NOT EXISTS co_consent (
  user_id    TEXT NOT NULL,
  purpose    TEXT NOT NULL,           -- 'analytics' | 'marketing' | 'otp'
  sensitive  INTEGER NOT NULL DEFAULT 0,  -- 1 for datos sensibles
  granted    INTEGER NOT NULL DEFAULT 0,
  granted_at INTEGER,
  revoked_at INTEGER,
  PRIMARY KEY (user_id, purpose)
);

CREATE TABLE IF NOT EXISTS co_rights_requests (
  request_id  TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  type        TEXT NOT NULL,          -- 'conocer' | 'actualizar' | 'suprimir' | 'revocar'
  received_at INTEGER NOT NULL,
  confirmed_at INTEGER,
  resolved_at INTEGER,
  resolution  TEXT
);
`;
```

## Data Subject Rights Implementation — Conocer, Actualizar, Suprimir

Law 1581 grants four core rights. The Worker below routes incoming rights requests, records receipt (starting the 10-business-day clock), and dispatches to a handler queue.

```typescript
// workers/co-habeas-data.ts
export interface Env {
  DB: D1Database;
  CO_RIGHTS_QUEUE: Queue;
}

type RightsType = "conocer" | "actualizar" | "suprimir" | "revocar";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { user_id, type, payload } = await request.json<{
      user_id: string;
      type: RightsType;
      payload?: Record<string, unknown>;
    }>();

    if (!["conocer", "actualizar", "suprimir", "revocar"].includes(type)) {
      return new Response(JSON.stringify({ error: "Invalid rights type" }), { status: 400 });
    }

    const requestId = crypto.randomUUID();
    const now = Date.now();

    await env.DB.prepare(
      `INSERT INTO co_rights_requests (request_id, user_id, type, received_at)
       VALUES (?, ?, ?, ?)`
    ).bind(requestId, user_id, type, now).run();

    await env.CO_RIGHTS_QUEUE.send({ requestId, user_id, type, payload, receivedAt: now });

    // Law 1581 Art. 15: confirm receipt within 10 business days
    return new Response(
      JSON.stringify({ request_id: requestId, message: "Request received. Response within 15 business days." }),
      { status: 202, headers: { "Content-Type": "application/json" } }
    );
  },
};

// Queue consumer — resolves each rights type
export async function consumeRightsRequest(
  batch: MessageBatch<{ requestId: string; user_id: string; type: RightsType; payload?: Record<string, unknown>; receivedAt: number }>,
  env: Env
): Promise<void> {
  for (const msg of batch.messages) {
    const { requestId, user_id, type, payload } = msg.body;
    let resolution = "";

    try {
      if (type === "suprimir") {
        await env.DB.prepare(
          `UPDATE co_user_data SET
             email = NULL, phone = NULL, bio = NULL,
             active = 0, deleted_at = ?
           WHERE user_id = ? AND country_code = 'CO'`
        ).bind(Date.now(), user_id).run();
        resolution = "suppressed";
      } else if (type === "actualizar" && payload) {
        const sets = Object.keys(payload)
          .filter((k) => ["email", "phone", "bio"].includes(k))
          .map((k) => `${k} = ?`).join(", ");
        const vals = Object.entries(payload)
          .filter(([k]) => ["email", "phone", "bio"].includes(k))
          .map(([, v]) => v);
        if (sets) {
          await env.DB.prepare(
            `UPDATE co_user_data SET ${sets} WHERE user_id = ? AND country_code = 'CO'`
          ).bind(...vals, user_id).run();
        }
        resolution = "updated";
      } else if (type === "revocar") {
        await env.DB.prepare(
          `UPDATE co_consent SET granted = 0, revoked_at = ?
           WHERE user_id = ?`
        ).bind(Date.now(), user_id).run();
        resolution = "consent_revoked";
      } else if (type === "conocer") {
        resolution = "data_disclosed_via_secure_channel";
      }

      await env.DB.prepare(
        `UPDATE co_rights_requests SET resolved_at = ?, resolution = ?
         WHERE request_id = ?`
      ).bind(Date.now(), resolution, requestId).run();

      msg.ack();
    } catch {
      msg.retry();
    }
  }
}
```

## Consent Management — Datos Sensibles Require Express Consent

For *datos sensibles* (health, biometric, political, religious data), Law 1581 Art. 6 requires prior, explicit, and informed consent. example project must not process such data by default.

```typescript
// workers/co-consent.ts
export async function grantCOConsent(
  userId: string,
  purpose: string,
  isSensitive: boolean,
  db: D1Database
): Promise<void> {
  if (isSensitive) {
    // Datos sensibles: require a signed consent document reference
    // Do not store sensitive data without this step
    throw new Error(
      "Datos sensibles require explicit written consent under Law 1581 Art. 6. " +
      "Store the signed consent reference before calling this function."
    );
  }

  await db.prepare(
    `INSERT INTO co_consent (user_id, purpose, sensitive, granted, granted_at)
     VALUES (?, ?, ?, 1, ?)
     ON CONFLICT(user_id, purpose) DO UPDATE SET
       granted = 1, granted_at = excluded.granted_at, revoked_at = NULL`
  ).bind(userId, purpose, isSensitive ? 1 : 0, Date.now()).run();
}

export async function hasCOConsent(
  userId: string,
  purpose: string,
  db: D1Database
): Promise<boolean> {
  const row = await db.prepare(
    `SELECT granted FROM co_consent
     WHERE user_id = ? AND purpose = ? AND granted = 1 AND revoked_at IS NULL`
  ).bind(userId, purpose).first<{ granted: number }>();
  return row !== null;
}
```

## Breach Notification

The SIC requires notification of breaches affecting Colombian residents within 15 business days of discovery (SIC Circular 002 of 2015). The notification must describe the nature of the breach, affected data categories, and remediation measures.

```typescript
// workers/co-breach-notify.ts
export interface Env {
  DB: D1Database;
  BREACH_KV: KVNamespace;
  SIC_NOTIFY_TOKEN: string;
}

export async function notifySIC(
  breachId: string,
  summary: { nature: string; categories: string[]; remediations: string[] },
  env: Env
): Promise<void> {
  const key = `co_breach:${breachId}`;
  const existing = await env.BREACH_KV.get(key);
  if (existing) return;

  await env.BREACH_KV.put(key, "notified", { expirationTtl: 30 * 86400 });

  // SIC notification portal (replace URL with current SIC e-filing endpoint)
  const resp = await fetch("https://sicele.sic.gov.co/api/breach-notice", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.SIC_NOTIFY_TOKEN}`,
    },
    body: JSON.stringify({
      breach_id: breachId,
      platform: "example.com",
      detected_at: new Date().toISOString(),
      nature: summary.nature,
      data_categories: summary.categories,
      remediation_steps: summary.remediations,
      jurisdiction: "CO",
    }),
  });

  if (!resp.ok) {
    // Remove sentinel on failure so retry is possible
    await env.BREACH_KV.delete(key);
    throw new Error(`SIC notification failed: ${resp.status}`);
  }
}
```

## Anti-patterns

- Treating Colombian personal data the same as a generic GDPR erasure — the Colombian right of *supresión* has exceptions (legal obligations, public interest) that differ from GDPR Art. 17 and must be evaluated separately.
- Failing to record the 10-business-day receipt confirmation — Law 1581 Art. 15 requires acknowledgement of receipt before the 15-day resolution clock starts.
- Using opt-out consent for any processing of *datos sensibles* — these require opt-in, express, and documented consent.
- Storing the SIC notification payload in D1 without expiry — breach records are audit artefacts; retain for the SIC-recommended 5-year audit period then purge.
- Combining `revocar` (consent revocation) with `suprimir` (erasure) in a single handler without checking whether continued processing is required by law (e.g., tax records).

## Gotchas

- Business days in Colombia exclude Sundays and official public holidays; implement a Colombian calendar calculator or buffer with an extra 3 calendar days to be safe.
- The SIC's e-filing portal changes URLs periodically; parameterise the endpoint in a Worker secret rather than hard-coding it.
- Foreign companies without a Colombian entity must still comply; appoint a local representative and register the database with the SIC Registro Nacional de Bases de Datos (RNBD).
- Law 2300 of 2023 (pending full implementation) may extend habeas data rights to algorithmic profiling — monitor SIC circulars.

## Verification

1. POST to the rights endpoint with `type: "suprimir"` and confirm `co_user_data.active = 0` and `deleted_at` set.
2. POST with `type: "actualizar"` and `payload: { bio: "updated" }` and verify the D1 row reflects the change.
3. Call `grantCOConsent` with `isSensitive: true` without a consent document reference and confirm it throws.
4. Call `notifySIC` twice with the same `breachId` and verify the SIC endpoint receives exactly one request.
5. Query `co_rights_requests` and confirm `resolved_at` is populated after Queue consumption.

## Related

- [LGPD Brazil Compliance](lgpd-brazil-compliance.md)
- [Argentina PDPA Data Localization Workers](argentina-pdpa-data-localization-workers.md)
- [Peru LPDP Workers D1](peru-lpdp-workers-d1.md)
- [GDPR Data Subject Rights API](gdpr-data-subject-rights-api.md)

## Sources

- Ley Estatutaria 1581 de 2012: https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981
- Decreto 1377 de 2013: https://www.sic.gov.co/recursos_user/documentos/normatividad/Decretos/2013/Decreto_1377_2013.pdf
- SIC Circular 002 de 2015 (breach notification): https://www.sic.gov.co/circular-002-2015
- SIC Registro Nacional de Bases de Datos: https://rnbd.sic.gov.co/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
