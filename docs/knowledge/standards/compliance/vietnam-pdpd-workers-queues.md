# Vietnam Personal Data Protection Decree (PDPD) — Cloudflare Workers & Queues

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your platform processes personal data of Vietnamese residents and must satisfy Decree 13/2023/ND-CP on Personal Data Protection (PDPD), effective 1 July 2023. You need to implement dual-tier data classification, Ministry of Public Security (MPS) impact assessments, and consent audit trails using Cloudflare Workers, D1, and Queues.

## Context
Vietnam's PDPD distinguishes two tiers: basic personal data (name, DOB, address) and sensitive personal data (health, biometrics, race, religion, sexual orientation, criminal records, financial data). Sensitive data requires explicit consent, is subject to a Personal Data Protection Impact Assessment (PDPIA), and cross-border transfers to a third country require MPS approval via a DPIA filing. Enforcement sits with the Department of Cybersecurity and Hi-tech Crime Prevention under the MPS. Fines can reach VND 100 million (~USD 4,000) per violation but cumulative corporate penalties and criminal liability for executives are the real deterrent.

## Data Tier Classification Middleware

Route requests through a classifier that stamps a `X-VN-Data-Tier` header so downstream Workers enforce the correct handling path.

```typescript
// workers/pdpd-classifier.ts
const SENSITIVE_FIELDS = new Set([
  "health", "biometric", "race", "religion", "sexual_orientation",
  "criminal_record", "financial_detail", "political_opinion",
]);

interface ClassifiedPayload {
  fields: string[];

}

export default {
  async fetch(request: Request): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<ClassifiedPayload>();
    const tier = body.fields.some(f => SENSITIVE_FIELDS.has(f)) ? "sensitive" : "basic";

    const upstream = new Request(request.url, {
      method: request.method,
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        "X-VN-Data-Tier": tier,
        "X-VN-Classified-At": new Date().toISOString(),
      }),
      body: JSON.stringify(body),
    });

    return fetch(upstream);
  },
};
```

## Consent Registration with MPS-Ready Audit Record

PDPD Article 11 mandates written or electronic consent records that can be produced to MPS inspectors on demand.

```typescript
// workers/pdpd-consent.ts
import { D1Database, Queue } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
  AUDIT_QUEUE: Queue;
}

interface ConsentRequest {
  subjectId: string;
  dataTier: "basic" | "sensitive";
  purposes: string[];
  consentMethod: "web_form" | "api_call" | "signed_document";
  languageUsed: "vi" | "en" | string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<ConsentRequest>();

    if (body.dataTier === "sensitive" && body.consentMethod !== "signed_document" && body.consentMethod !== "web_form") {
      return new Response(
        JSON.stringify({ error: "PDPD Art. 11: sensitive data requires explicit written or web-form consent" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    const consentId = crypto.randomUUID();
    const now = new Date().toISOString();

    await env.DB.prepare(
      `INSERT INTO pdpd_consent
         (id, subject_id, data_tier, purposes, consent_method, language, granted_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      consentId, body.subjectId, body.dataTier,
      JSON.stringify(body.purposes), body.consentMethod, body.languageUsed, now
    ).run();

    // Enqueue for async MPS-format audit export
    await env.AUDIT_QUEUE.send({ event: "consent_granted", consentId, subjectId: body.subjectId, timestamp: now });

    return new Response(JSON.stringify({ consentId, grantedAt: now }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Personal Data Protection Impact Assessment (PDPIA) Tracker

PDPD Article 24 requires a PDPIA before processing sensitive data and before any cross-border transfer. The assessment must be filed with MPS within 60 days of processing commencement.

```typescript
// workers/pdpia-tracker.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env { DB: D1Database; }

interface PdpiaEntry {
  processingActivityId: string;
  dataTier: "basic" | "sensitive";
  crossBorderDestination?: string;
  riskLevel: "low" | "medium" | "high";
  mitigations: string[];
  startDate: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<PdpiaEntry>();
    const mpsDeadline = new Date(
      new Date(body.startDate).getTime() + 60 * 24 * 60 * 60 * 1000
    ).toISOString(); // 60-day MPS filing deadline

    const id = crypto.randomUUID();

    await env.DB.prepare(
      `INSERT INTO pdpia_register
         (id, activity_id, data_tier, cross_border_dest, risk_level, mitigations, start_date, mps_filing_deadline, filed_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)`
    ).bind(
      id, body.processingActivityId, body.dataTier,
      body.crossBorderDestination ?? null, body.riskLevel,
      JSON.stringify(body.mitigations), body.startDate, mpsDeadline
    ).run();

    return new Response(JSON.stringify({ pdpiaId: id, mpsFilingDeadline: mpsDeadline }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Breach Notification Queue Consumer

PDPD Article 23 requires breach notification to MPS within 72 hours of discovery. A Queue consumer retries delivery and persists status.

```typescript
// workers/breach-queue-consumer.ts
import { D1Database, MessageBatch } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
  MPS_NOTIFY_URL: string;
  MPS_API_KEY: string;
}

interface BreachMessage {
  incidentId: string;
  affectedCount: number;
  dataCategories: string[];
  detectedAt: string;
  description: string;
}

export default {
  async queue(batch: MessageBatch<BreachMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const ev = msg.body;
      const hoursElapsed =
        (Date.now() - new Date(ev.detectedAt).getTime()) / 3_600_000;

      const payload = {
        incident_id: ev.incidentId,
        detected_at: ev.detectedAt,
        reported_at: new Date().toISOString(),
        affected_count: ev.affectedCount,
        data_categories: ev.dataCategories,
        description: ev.description,
        hours_elapsed: Math.round(hoursElapsed),
        law_ref: "Decree 13/2023/ND-CP Art. 23",
      };

      const resp = await fetch(env.MPS_NOTIFY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": env.MPS_API_KEY },
        body: JSON.stringify(payload),
      });

      await env.DB.prepare(
        `INSERT INTO breach_notifications (incident_id, channel, status_code, hours_elapsed, submitted_at)
         VALUES (?, 'MPS', ?, ?, ?)`
      ).bind(ev.incidentId, resp.status, Math.round(hoursElapsed), new Date().toISOString()).run();

      if (resp.ok) {
        msg.ack();
      } else {
        msg.retry({ delaySeconds: 300 }); // retry after 5 min
      }
    }
  },
};
```

## Anti-patterns
- Treating all personal data as "basic" tier to avoid PDPIA filings — MPS inspectors can require full records of what data was collected.
- Filing the PDPIA after the 60-day window has elapsed from processing start; track `start_date` at activity creation, not discovery.
- Omitting the Vietnamese-language version of consent text; PDPD requires disclosure in Vietnamese for resident subjects.
- Cross-border transfers to countries without MPS adequacy determination or without a signed transfer agreement on file.
- Using `msg.ack()` before confirming MPS HTTP 200 — a 500 from MPS should trigger retry to avoid missed 72-hour window.

## Gotchas
- PDPD covers both online and offline processing — Worker-only enforcement misses CRM or offline systems that must comply.
- The PDPIA obligation triggers on collecting, not just storing, sensitive data — edge collection Workers need classification too.
- MPS has no published public API yet (as of 2026); build the notification queue consumer to target whatever endpoint MPS provides under your licence.
- Data subjects have a right to know the full list of third-party recipients — maintain a `data_sharing_register` table in D1.
- Vietnamese courts have interpreted the law to cover IP addresses as personal data under certain contexts; hash or truncate IPs at ingestion.

## Verification
1. POST to classifier with `fields: ["health"]` — confirm `X-VN-Data-Tier: sensitive` response header.
2. POST a consent record with `dataTier: sensitive` and `consentMethod: api_call` — expect HTTP 400.
3. Create a PDPIA with a `startDate` 61 days ago; query `pdpia_register` and confirm `mps_filing_deadline < NOW()` — alert should fire.
4. Enqueue a breach message with `detectedAt` 70 hours ago; confirm Queue consumer posts to MPS mock and records `hours_elapsed ≈ 70`.
5. Withdraw consent for a subject and confirm downstream data access returns 403.

## Related
- `/documentation/docs/policies/compliance/singapore-pdpa-workers-d1.md`
- `/documentation/docs/policies/compliance/pdpa-thailand-compliance.md`
- `/documentation/docs/policies/compliance/cross-border-data-transfer-mechanisms.md`
- `/documentation/docs/policies/compliance/gdpr-breach-notification-72h.md`
- `/documentation/docs/policies/compliance/data-retention-automated-deletion-workers.md`

## Sources
- Decree 13/2023/ND-CP on Personal Data Protection (Vietnam): https://vanban.chinhphu.vn/
- Ministry of Public Security guidance: https://bocongan.gov.vn/
- ASEAN Cross-Border Data Flows Framework: https://asean.org/
