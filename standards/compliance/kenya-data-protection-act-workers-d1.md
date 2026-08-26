# Kenya Data Protection Act — Cloudflare Workers and D1 Implementation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project serves Kenyan users under the Kenya Data Protection Act 2019 (DPA), enforced by the Office of the Data Protection Commissioner (ODPC). The ODPC can levy fines up to KES 5 million or 1% of annual global turnover for violations and has initiated enforcement actions since 2023. An anonymous social platform must implement D1-backed data subject rights, consent capture with an audit trail, and a 72-hour breach notification pipeline — all without de-anonymising users who have not opted into identifiable processing.

## Context

The Kenya DPA 2019 closely tracks GDPR in structure and is supplemented by the Data Protection (General) Regulations 2021 and the Data Protection (Registration of Data Controllers and Data Processors) Regulations 2021. Platforms with 100,000+ Kenyan data subjects must register with the ODPC. Cloudflare's Mombasa and Nairobi PoPs reduce latency for Kenyan traffic; D1 stores the authoritative record of Kenyan user data and consent, while KV provides a fast read layer for per-request consent checks.

## Kenya DPA Regulation Overview — D1 Schema

The DPA and its General Regulations require that data be adequate, relevant, not excessive, accurate, and retained only as long as necessary. The D1 schema enforces data minimisation at the column level and tracks registration status.

```typescript
// D1 schema — run via wrangler d1 execute
const KE_SCHEMA = `
CREATE TABLE IF NOT EXISTS ke_user_data (
  user_id       TEXT PRIMARY KEY,
  pseudonym     TEXT NOT NULL,
  email         TEXT,
  phone         TEXT,
  country_code  TEXT NOT NULL DEFAULT 'KE',
  created_at    INTEGER NOT NULL,
  active        INTEGER NOT NULL DEFAULT 1,
  deleted_at    INTEGER,
  retention_ttl INTEGER  -- epoch ms after which data must be purged
);

CREATE TABLE IF NOT EXISTS ke_consent (
  user_id    TEXT NOT NULL,
  purpose    TEXT NOT NULL,
  granted    INTEGER NOT NULL DEFAULT 0,
  granted_at INTEGER,
  revoked_at INTEGER,
  method     TEXT,     -- 'checkbox' | 'signed_form' | 'verbal_recorded'
  PRIMARY KEY (user_id, purpose)
);

CREATE TABLE IF NOT EXISTS ke_rights_requests (
  request_id  TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  right_type  TEXT NOT NULL,
  received_at INTEGER NOT NULL,
  resolved_at INTEGER,
  resolution  TEXT
);

CREATE TABLE IF NOT EXISTS ke_breach_log (
  breach_id    TEXT PRIMARY KEY,
  detected_at  INTEGER NOT NULL,
  notified_at  INTEGER,
  odpc_ref     TEXT,
  categories   TEXT,
  subject_count INTEGER
);
`;
```

## Data Subject Rights Implementation

DPA §§ 26–34 grant Kenyan data subjects rights to access, correction, deletion, restriction, objection, and portability. The ODPC expects rights requests to be acknowledged within 21 days and fully resolved without "undue delay" (best practice: 30 days). The Worker below routes all rights types through a unified endpoint backed by D1 and a Queue.

```typescript
// workers/ke-rights.ts
export interface Env {
  DB: D1Database;
  KE_RIGHTS_QUEUE: Queue;
}

type KERight = "access" | "correction" | "erasure" | "restriction" | "objection" | "portability";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { user_id, right, payload } = await request.json<{
      user_id: string;
      right: KERight;
      payload?: Record<string, unknown>;
    }>();

    const requestId = crypto.randomUUID();

    await env.DB.prepare(
      `INSERT INTO ke_rights_requests (request_id, user_id, right_type, received_at)
       VALUES (?, ?, ?, ?)`
    ).bind(requestId, user_id, right, Date.now()).run();

    await env.KE_RIGHTS_QUEUE.send({ requestId, user_id, right, payload });

    return new Response(
      JSON.stringify({
        request_id: requestId,
        message: "Request received. Response within 21 days per Kenya DPA §26.",
      }),
      { status: 202, headers: { "Content-Type": "application/json" } }
    );
  },
};

export async function consumeKERights(
  batch: MessageBatch<{ requestId: string; user_id: string; right: KERight; payload?: Record<string, unknown> }>,
  env: Env
): Promise<void> {
  for (const msg of batch.messages) {
    const { requestId, user_id, right, payload } = msg.body;
    try {
      let resolution = "";

      switch (right) {
        case "erasure": {
          await env.DB.prepare(
            `UPDATE ke_user_data SET
               email = NULL, phone = NULL,
               active = 0, deleted_at = ?
             WHERE user_id = ? AND country_code = 'KE'`
          ).bind(Date.now(), user_id).run();
          await env.DB.prepare(
            `UPDATE ke_consent SET granted = 0, revoked_at = ? WHERE user_id = ?`
          ).bind(Date.now(), user_id).run();
          resolution = "erased";
          break;
        }
        case "correction": {
          if (payload) {
            const allowed = ["email", "phone"] as const;
            for (const field of allowed) {
              if (field in payload) {
                await env.DB.prepare(
                  `UPDATE ke_user_data SET ${field} = ? WHERE user_id = ? AND country_code = 'KE'`
                ).bind(payload[field], user_id).run();
              }
            }
          }
          resolution = "corrected";
          break;
        }
        case "access": {
          // In production: deliver data via secure, verified channel
          resolution = "data_disclosed_via_secure_channel";
          break;
        }
        case "portability": {
          resolution = "export_queued";
          break;
        }
        default:
          resolution = `acknowledged:${right}`;
      }

      await env.DB.prepare(
        `UPDATE ke_rights_requests SET resolved_at = ?, resolution = ?
         WHERE request_id = ?`
      ).bind(Date.now(), resolution, requestId).run();

      msg.ack();
    } catch {
      msg.retry();
    }
  }
}
```

## Consent Management

DPA § 30 requires consent to be informed, specific, freely given, and unambiguous. For an anonymous platform, default processing uses legitimate interest for pseudonymous analytics; consent is required for identifiable email or phone collection. The consent method (checkbox, signed form, etc.) must be recorded.

```typescript
// workers/ke-consent.ts
type ConsentMethod = "checkbox" | "signed_form" | "verbal_recorded";

export async function recordKEConsent(
  userId: string,
  purpose: string,
  method: ConsentMethod,
  db: D1Database,
  kv: KVNamespace
): Promise<void> {
  await db.prepare(
    `INSERT INTO ke_consent (user_id, purpose, granted, granted_at, method)
     VALUES (?, ?, 1, ?, ?)
     ON CONFLICT(user_id, purpose) DO UPDATE SET
       granted    = 1,
       granted_at = excluded.granted_at,
       method     = excluded.method,
       revoked_at = NULL`
  ).bind(userId, purpose, Date.now(), method).run();

  // Fast-path cache for per-request consent checks
  await kv.put(`ke_consent:${userId}:${purpose}`, "1", { expirationTtl: 3600 });
}

export async function revokeKEConsent(
  userId: string,
  purpose: string,
  db: D1Database,
  kv: KVNamespace
): Promise<void> {
  await db.prepare(
    `UPDATE ke_consent SET granted = 0, revoked_at = ?
     WHERE user_id = ? AND purpose = ?`
  ).bind(Date.now(), userId, purpose).run();

  await kv.delete(`ke_consent:${userId}:${purpose}`);
}

export async function hasKEConsent(
  userId: string,
  purpose: string,
  kv: KVNamespace,
  db: D1Database
): Promise<boolean> {
  const cached = await kv.get(`ke_consent:${userId}:${purpose}`);
  if (cached !== null) return cached === "1";

  // Fallback to D1 on cache miss
  const row = await db.prepare(
    `SELECT 1 FROM ke_consent
     WHERE user_id = ? AND purpose = ? AND granted = 1 AND revoked_at IS NULL`
  ).bind(userId, purpose).first();
  return row !== null;
}
```

## Breach Notification

DPA § 43 and General Regulations Reg. 30 require notification to the ODPC within 72 hours of discovering a breach. The notification must describe the nature of the breach, categories affected, and remediation steps. Affected individuals must be notified without undue delay when the breach poses high risk.

```typescript
// workers/ke-breach-notify.ts
export interface Env {
  DB: D1Database;
  BREACH_KV: KVNamespace;
  ODPC_API_KEY: string;
}

export async function notifyODPC(
  breachId: string,
  details: {
    nature: string;
    categories: string[];
    subject_count: number;
    measures: string;
    discovery_time: string;
  },
  env: Env
): Promise<string> {
  const key = `ke_breach:${breachId}`;
  if (await env.BREACH_KV.get(key)) return "already_notified";

  await env.BREACH_KV.put(key, "pending", { expirationTtl: 30 * 86400 });

  // ODPC portal — verify current endpoint with ODPC
  const resp = await fetch("https://odpc.go.ke/api/breach-notification", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": env.ODPC_API_KEY,
    },
    body: JSON.stringify({
      breach_id: breachId,
      controller: "example.com",
      jurisdiction: "KE",
      notified_at: new Date().toISOString(),
      ...details,
    }),
  });

  if (!resp.ok) {
    await env.BREACH_KV.delete(key);
    throw new Error(`ODPC notification failed: ${resp.status}`);
  }

  const { reference } = await resp.json<{ reference: string }>();

  await env.DB.prepare(
    `INSERT OR REPLACE INTO ke_breach_log
       (breach_id, detected_at, notified_at, odpc_ref, categories, subject_count)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    breachId,
    new Date(details.discovery_time).getTime(),
    Date.now(),
    reference,
    JSON.stringify(details.categories),
    details.subject_count
  ).run();

  await env.BREACH_KV.put(key, reference, { expirationTtl: 30 * 86400 });
  return reference;
}
```

## Anti-patterns

- Using KV alone for consent records without a D1 backup — KV items can expire and are eventually consistent; the ODPC may request consent evidence years after collection.
- Failing to record the consent `method` — the DPA and ODPC guidance distinguish different consent capture methods; this field is required to demonstrate compliance in an audit.
- Applying a single erasure handler to all fields regardless of legal retention requirements — tax records, fraud logs, and breach audit trails may have legal hold obligations that override erasure.
- Hardcoding the ODPC breach notification URL — the ODPC portal has changed; parameterise via a Worker secret and update it without code deploys.
- Omitting Kenyan D1 data from retention TTL scheduling — DPA § 25 requires data not be kept longer than necessary; set `retention_ttl` and run a nightly cleanup Cron Trigger.

## Gotchas

- Organisations with 1,000+ data subjects of Kenyan residents must register with the ODPC; example project will quickly exceed this threshold — register before onboarding Kenyan users.
- The DPA imposes individual liability on directors and officers for wilful or reckless violations — this elevates compliance from a legal checkbox to a board-level concern.
- Cross-border transfers require an adequacy finding or appropriate safeguards (SCCs or binding corporate rules) — no Kenya adequacy list exists yet; use SCCs modelled on the GDPR equivalents.
- The "right to object" (§ 34) applies to processing based on legitimate interests and direct marketing — ensure objection flags are checked before every marketing dispatch.

## Verification

1. POST `right: "erasure"` for a KE user; confirm `ke_user_data.active = 0`, `deleted_at` set, and consent revoked.
2. Call `hasKEConsent` after `revokeKEConsent`; confirm `false` returned from both KV and D1 paths.
3. Call `notifyODPC` twice with the same `breachId`; confirm the ODPC endpoint is called exactly once.
4. Query `ke_breach_log` after notification; verify `odpc_ref` is populated.
5. Simulate a KV cache miss by deleting the KV key and calling `hasKEConsent`; confirm D1 fallback path returns the correct result.

## Related

- [Kenya Data Protection Act Workers](kenya-data-protection-act-workers.md)
- [GDPR Data Subject Rights API](gdpr-data-subject-rights-api.md)
- [GDPR Breach Notification 72h](gdpr-breach-notification-72h.md)
- [South Africa POPIA Workers D1](south-africa-popia-workers-d1.md)
- [Data Retention Automated Deletion Workers](data-retention-automated-deletion-workers.md)

## Sources

- Kenya Data Protection Act 2019: https://www.odpc.go.ke/data-protection-act-2019/
- Data Protection (General) Regulations 2021: https://www.odpc.go.ke/general-regulations/
- Data Protection (Registration) Regulations 2021: https://www.odpc.go.ke/registration-regulations/
- ODPC enforcement actions: https://www.odpc.go.ke/enforcement/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
