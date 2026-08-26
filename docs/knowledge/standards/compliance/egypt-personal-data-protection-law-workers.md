# Egypt Personal Data Protection Law on Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project serves Egyptian users on an anonymous social platform, activating obligations under Egypt's Personal Data Protection Law (PDPL) No. 151 of 2020 and its Executive Regulations (Ministerial Decree 190 of 2022). The law is enforced by the Personal Data Protection Centre (PDPC) under the Ministry of Communications and Information Technology (MCIT). Non-compliance carries fines of EGP 1–5 million and imprisonment for egregious cases. The platform must implement consent, subject-rights handling, and breach notification without compromising user pseudonymity.

## Context

Egypt PDPL applies to any entity that processes personal data of Egyptian residents, regardless of where the entity is based. It mirrors GDPR in structure but diverges on cross-border transfer rules, mandatory registration, and a requirement to appoint an Egyptian-registered Data Protection Officer (DPO) for large-scale processors. Cloudflare Workers intercept Egyptian traffic (identified via `CF-IPCountry: EG`) and route it through a compliant data pipeline backed by D1 for personal data storage and KV for consent state.

## Egypt PDPL Regulation Overview — Key Obligations

The PDPL imposes six primary obligations relevant to example project:

1. **Lawful basis**: Processing must have a legal basis (consent, contract, legal obligation, vital interests, public task, or legitimate interests — Art. 4).
2. **Data minimisation**: Collect only data adequate and relevant for the stated purpose (Art. 5).
3. **Cross-border transfers**: Transfers to countries without an MCIT adequacy decision require contractual safeguards or PDPC authorisation (Art. 28).
4. **Mandatory registration**: Entities processing large-scale data of Egyptian residents must register with the PDPC.
5. **Data subject rights**: Access, rectification, erasure, restriction, objection, portability — 30-day response deadline.
6. **Breach notification**: Notify PDPC within 72 hours; notify affected subjects without undue delay.

```typescript
// workers/eg-compliance-middleware.ts
export interface Env {
  DB: D1Database;
  EG_CONSENT_KV: KVNamespace;
  EG_AUDIT_QUEUE: Queue;
}

export async function egyptMiddleware(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  next: () => Promise<Response>
): Promise<Response> {
  const country = request.headers.get("CF-IPCountry") ?? "";
  if (country !== "EG") return next();

  const userId = request.headers.get("X-User-Id") ?? "";
  const path = new URL(request.url).pathname;

  // Check consent for non-essential processing on Egyptian traffic
  if (path.startsWith("/api/analytics") || path.startsWith("/api/recommendations")) {
    const consent = await env.EG_CONSENT_KV.get(`eg_consent:${userId}:analytics`);
    if (!consent) {
      return new Response(
        JSON.stringify({ error: "Egyptian PDPL: consent required for analytics processing" }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    }
  }

  ctx.waitUntil(
    env.EG_AUDIT_QUEUE.send({
      event: "eg_request",
      user_id: userId,
      path,
      ts: Date.now(),
    })
  );

  return next();
}
```

## Data Subject Rights Implementation

PDPL Art. 20–26 grant Egyptian residents rights to access, rectify, erase, restrict, object, and port their data. The platform must respond within 30 calendar days. The following Worker handles all rights types via a unified endpoint.

```typescript
// workers/eg-rights.ts
export interface Env {
  DB: D1Database;
  EG_AUDIT_QUEUE: Queue;
}

type EGRight = "access" | "rectify" | "erase" | "restrict" | "object" | "portability";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { user_id, right, payload } = await request.json<{
      user_id: string;
      right: EGRight;
      payload?: Record<string, unknown>;
    }>();

    const requestId = crypto.randomUUID();

    await env.DB.prepare(
      `INSERT INTO eg_rights_requests (request_id, user_id, right_type, received_at)
       VALUES (?, ?, ?, ?)`
    ).bind(requestId, user_id, right, Date.now()).run();

    let result: Record<string, unknown> = {};

    switch (right) {
      case "access": {
        const row = await env.DB.prepare(
          `SELECT user_id, pseudonym, email, phone, created_at
           FROM eg_user_data WHERE user_id = ? AND country_code = 'EG'`
        ).bind(user_id).first();
        result = { data: row ?? null };
        break;
      }
      case "erase": {
        await env.DB.prepare(
          `UPDATE eg_user_data SET
             email = NULL, phone = NULL, bio = NULL,
             active = 0, deleted_at = ?
           WHERE user_id = ? AND country_code = 'EG'`
        ).bind(Date.now(), user_id).run();
        result = { erased: true };
        break;
      }
      case "rectify": {
        if (payload) {
          const allowed = ["email", "phone", "bio"] as const;
          for (const field of allowed) {
            if (field in payload) {
              await env.DB.prepare(
                `UPDATE eg_user_data SET ${field} = ? WHERE user_id = ? AND country_code = 'EG'`
              ).bind(payload[field], user_id).run();
            }
          }
        }
        result = { rectified: true };
        break;
      }
      case "portability": {
        const rows = await env.DB.prepare(
          `SELECT * FROM eg_user_data WHERE user_id = ? AND country_code = 'EG'`
        ).bind(user_id).all();
        result = { export: rows.results };
        break;
      }
      default:
        result = { acknowledged: true, right };
    }

    await env.DB.prepare(
      `UPDATE eg_rights_requests SET resolved_at = ? WHERE request_id = ?`
    ).bind(Date.now(), requestId).run();

    await env.EG_AUDIT_QUEUE.send({ event: "eg_right_fulfilled", requestId, right, ts: Date.now() });

    return new Response(JSON.stringify({ request_id: requestId, ...result }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Consent Management

PDPL Art. 4(a) requires consent to be freely given, specific, informed, and unambiguous. For an anonymous platform, only a pseudonymous device token is collected by default; consent is required for any enrichment (email, phone OTP). Consent records must be stored in a way that can be produced to the PDPC on request.

```typescript
// workers/eg-consent.ts
interface EGConsentRecord {
  user_id: string;
  purpose: string;
  granted: boolean;
  granted_at?: number;
  revoked_at?: number;
  ip_hash: string;
}

export async function recordEGConsent(
  record: EGConsentRecord,
  db: D1Database,
  kv: KVNamespace
): Promise<void> {
  await db.prepare(
    `INSERT INTO eg_consent
       (user_id, purpose, country, granted, granted_at, ip_hash)
     VALUES (?, ?, 'EG', ?, ?, ?)
     ON CONFLICT(user_id, purpose) DO UPDATE SET
       granted = excluded.granted,
       granted_at = excluded.granted_at,
       revoked_at = CASE WHEN excluded.granted = 0 THEN ? ELSE NULL END,
       ip_hash = excluded.ip_hash`
  ).bind(
    record.user_id,
    record.purpose,
    record.granted ? 1 : 0,
    record.granted_at ?? Date.now(),
    record.ip_hash,
    Date.now()
  ).run();

  // Cache in KV for low-latency middleware checks
  await kv.put(
    `eg_consent:${record.user_id}:${record.purpose}`,
    record.granted ? "1" : "0",
    { expirationTtl: 86400 }
  );
}
```

## Breach Notification

PDPL Art. 24 requires notification to the PDPC within 72 hours of discovery and to data subjects without undue delay when the breach is likely to result in high risk. The platform tracks notification dispatch in KV to prevent duplicates.

```typescript
// workers/eg-breach-notify.ts
export interface Env {
  DB: D1Database;
  BREACH_KV: KVNamespace;
  PDPC_API_KEY: string;
}

export async function notifyPDPC(
  breachId: string,
  details: {
    nature: string;
    categories: string[];
    estimated_records: number;
    likely_consequences: string;
    measures_taken: string;
  },
  env: Env
): Promise<void> {
  const key = `eg_breach:${breachId}`;
  if (await env.BREACH_KV.get(key)) return; // idempotency guard

  await env.BREACH_KV.put(key, JSON.stringify({ notified_at: Date.now() }), {
    expirationTtl: 30 * 86400,
  });

  // PDPC reporting portal — URL from MCIT official documentation
  const resp = await fetch("https://pdpc.mcit.gov.eg/api/v1/breach-notification", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": env.PDPC_API_KEY,
    },
    body: JSON.stringify({
      breach_id: breachId,
      controller: "example.com",
      notification_time: new Date().toISOString(),
      jurisdiction: "EG",
      ...details,
    }),
  });

  if (!resp.ok) {
    await env.BREACH_KV.delete(key);
    throw new Error(`PDPC notification failed: ${resp.status} ${await resp.text()}`);
  }
}
```

## Anti-patterns

- Applying PDPL logic to all global traffic instead of scoping to `CF-IPCountry: EG` — unnecessary latency and over-processing for non-Egyptian users.
- Treating Egypt's 72-hour breach notification window as a soft deadline — the PDPC has issued fines for late notifications; automate the dispatch as part of your incident detection pipeline.
- Omitting DPO contact details from the privacy notice — Egypt PDPL Art. 11 requires the DPO's identity and contact to be disclosed to data subjects.
- Storing consent records only in KV without D1 backup — KV is eventually consistent and items can expire; KV is suitable for fast checks but D1 is the authoritative record.
- Processing special categories of data (health, religion, political affiliation) without explicit consent — PDPL Art. 7 requires express opt-in, not just legitimate interest.

## Gotchas

- Egypt's adequacy list for cross-border transfers is not yet published; until the PDPC publishes it, treat all outbound transfers as requiring contractual safeguards or individual PDPC authorisation.
- The Executive Regulations allow the PDPC to require mandatory data localisation for certain categories — monitor for implementing decrees.
- The 30-day deadline for rights requests is calendar days, not business days — unlike Colombian law.
- PDPL Art. 32 allows the PDPC to conduct on-site audits with 48-hour notice; ensure D1 query interfaces are accessible to compliance staff without production access.

## Verification

1. POST `right: "erase"` for an Egyptian user and confirm `eg_user_data.active = 0` and `deleted_at` set.
2. POST `right: "access"` and verify the response payload contains the D1 row data.
3. Call `recordEGConsent` with `granted: false` and confirm KV stores `"0"` and D1 sets `revoked_at`.
4. Call `notifyPDPC` twice with the same `breachId` and confirm the PDPC endpoint is invoked exactly once.
5. Hit `/api/analytics` from a simulated Egyptian request without consent KV key; confirm `403` response.

## Related

- [GDPR Data Subject Rights API](gdpr-data-subject-rights-api.md)
- [GDPR Breach Notification 72h](gdpr-breach-notification-72h.md)
- [Saudi Arabia PDPL Workers D1](saudi-arabia-pdpl-workers-d1.md)
- [Turkey KVKK Workers D1](turkey-kvkk-workers-d1.md)
- [Cross-Border Data Transfer Cloudflare Workers](cross-border-data-transfer-cloudflare-workers.md)

## Sources

- Egypt Personal Data Protection Law No. 151 of 2020: https://mcit.gov.eg/en/Media_Center/Press_Releases/2020/8/6
- Executive Regulations — Ministerial Decree 190 of 2022: https://pdpc.mcit.gov.eg/regulations
- Personal Data Protection Centre (PDPC): https://pdpc.mcit.gov.eg/
- Cloudflare Workers CF-IPCountry: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare KV: https://developers.cloudflare.com/kv/
