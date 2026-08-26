# Quebec Law 25 (Act 25) Privacy Compliance — Cloudflare Workers & D1

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your service processes personal information of Quebec residents and must satisfy Quebec's Act 25 (An Act to modernize legislative provisions as regards the protection of personal information), which introduced privacy-by-default, algorithmic transparency, and mandatory incident reporting to the Commission d'accès à l'information (CAI) in phased rollouts from 2022 through 2023. You need Workers-based enforcement of these obligations.

## Context
Quebec Law 25 reformed the Act respecting the protection of personal information in the private sector (Law 25 amends both the public-sector and private-sector privacy laws). Phase 3 (September 2023) activated portability, privacy-by-default, and automated decision transparency requirements. The CAI has published enforcement guidelines and has levied fines up to CAD 25 million or 4% of worldwide turnover. Unlike PIPEDA, Law 25 applies a stricter opt-in consent default and requires a Privacy Impact Assessment (PIA) before any new personal information system is deployed or communicated outside Quebec.

## Privacy-by-Default Middleware

Law 25 Section 9.1 requires that the strictest privacy setting be the default for any product or service — no pre-ticked boxes, no broad sharing on sign-up.

```typescript
// workers/privacy-by-default.ts
const DEFAULT_BLOCKED_COOKIES = ["analytics", "advertising", "social_tracking"];

export default {
  async fetch(request: Request): Promise<Response> {
    const response = await fetch(request);
    const headers = new Headers(response.headers);

    // Strip permissive cookie attributes and enforce SameSite=Strict by default
    const setCookie = headers.getSetCookie?.() ?? [];
    const sanitised = setCookie.map(cookie => {
      let c = cookie
        .replace(/SameSite=None/gi, "SameSite=Strict")
        .replace(/SameSite=Lax/gi, "SameSite=Strict");
      if (!c.includes("Secure")) c += "; Secure";
      return c;
    });

    headers.delete("Set-Cookie");
    sanitised.forEach(c => headers.append("Set-Cookie", c));

    // Communicate privacy-by-default posture to downstream analytics
    headers.set("X-Privacy-Default", "strict");
    headers.set("X-Law25-Enforced", "true");

    return new Response(response.body, { status: response.status, headers });
  },
};
```

## Consent Management with Withdrawal Tracking

Law 25 requires granular consent per purpose and a straightforward withdrawal mechanism. The withdrawal must trigger cessation of processing within a reasonable time.

```typescript
// workers/law25-consent.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env { DB: D1Database; }

interface ConsentRecord {
  subjectId: string;
  purposes: { id: string; description: string }[];
  language: "fr" | "en";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/consent") {
      const body = await request.json<ConsentRecord>();
      if (!["fr", "en"].includes(body.language)) {
        // Law 25: must offer French version for Quebec residents
        return new Response(JSON.stringify({ error: "Law 25 §9: consent notice must be available in French" }), {
          status: 400, headers: { "Content-Type": "application/json" },
        });
      }

      const id = crypto.randomUUID();
      const now = new Date().toISOString();

      await env.DB.prepare(
        `INSERT INTO law25_consent (id, subject_id, purposes, language, granted_at, withdrawn_at)
         VALUES (?, ?, ?, ?, ?, NULL)`
      ).bind(id, body.subjectId, JSON.stringify(body.purposes), body.language, now).run();

      return new Response(JSON.stringify({ consentId: id, grantedAt: now }), {
        status: 201, headers: { "Content-Type": "application/json" },
      });
    }

    if (request.method === "DELETE" && url.pathname.startsWith("/consent/")) {
      const consentId = url.pathname.split("/").pop();
      const now = new Date().toISOString();

      const result = await env.DB.prepare(
        "UPDATE law25_consent SET withdrawn_at = ? WHERE id = ? AND withdrawn_at IS NULL"
      ).bind(now, consentId).run();

      if (!result.meta.changes) {
        return new Response(JSON.stringify({ error: "Consent not found or already withdrawn" }), { status: 404 });
      }

      // Flag downstream data to be deleted within 30 days per cessation obligation
      await env.DB.prepare(
        "INSERT INTO deletion_queue (subject_consent_id, scheduled_for) VALUES (?, ?)"
      ).bind(consentId, new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString()).run();

      return new Response(JSON.stringify({ withdrawnAt: now }), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

## Privacy Incident Reporting to CAI (72-Hour Target)

Law 25 Section 3.5 requires reporting confidentiality incidents that present a risk of serious harm to the CAI within 72 hours and notifying affected individuals.

```typescript
// workers/cai-incident-reporter.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
  CAI_API_ENDPOINT: string;
  CAI_TOKEN: string;
}

interface IncidentPayload {
  incidentId: string;
  affectedCount: number;
  infoTypes: string[];         // e.g. ["name","sin","health"]
  seriousHarmRisk: boolean;
  detectedAt: string;
  description: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<IncidentPayload>();

    if (!body.seriousHarmRisk) {
      // Only incidents presenting serious-harm risk require CAI reporting
      await env.DB.prepare(
        "INSERT INTO incident_log (id, serious_harm, cai_reported, created_at) VALUES (?, 0, 0, ?)"
      ).bind(body.incidentId, new Date().toISOString()).run();
      return new Response(JSON.stringify({ caiReporting: "not_required" }), { status: 200 });
    }

    const report = {
      incident_ref: body.incidentId,
      detected: body.detectedAt,
      reported: new Date().toISOString(),
      affected_count: body.affectedCount,
      information_types: body.infoTypes,
      description: body.description,
      organization: "example.com",
      law_ref: "Quebec Law 25 §3.5",
    };

    const resp = await fetch(env.CAI_API_ENDPOINT, {
      method: "POST",
      headers: { "Authorization": `Bearer ${env.CAI_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify(report),
    });

    await env.DB.prepare(
      "INSERT INTO incident_log (id, serious_harm, cai_reported, cai_status, created_at) VALUES (?, 1, 1, ?, ?)"
    ).bind(body.incidentId, resp.status, new Date().toISOString()).run();

    return new Response(JSON.stringify({ caiStatus: resp.status }), {
      status: resp.ok ? 200 : 502,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Algorithmic Decision Transparency (Section 12.1)

Law 25 Section 12.1 grants individuals the right to know when an automated decision has been made about them using their personal information and to request human review.

```typescript
// workers/algo-transparency.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env { DB: D1Database; }

interface AlgoDecision {
  subjectId: string;
  decisionType: string;
  modelId: string;
  inputFeatures: string[];
  outcome: string;
  confidence: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<AlgoDecision>();

    const decisionId = crypto.randomUUID();
    const now = new Date().toISOString();

    // Persist decision record with human-review flag
    await env.DB.prepare(
      `INSERT INTO algo_decisions
         (id, subject_id, decision_type, model_id, input_features, outcome, confidence, human_review_requested, decided_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)`
    ).bind(
      decisionId, body.subjectId, body.decisionType, body.modelId,
      JSON.stringify(body.inputFeatures), body.outcome, body.confidence, now
    ).run();

    // Return disclosure as required by Law 25 §12.1
    const disclosure = {
      decisionId,
      decidedAt: now,
      decisionType: body.decisionType,
      basedOnPersonalInfo: true,
      humanReviewAvailable: true,
      humanReviewUrl: `/dsr/review/${decisionId}`,
      law25Ref: "Quebec Law 25 §12.1",
    };

    return new Response(JSON.stringify({ outcome: body.outcome, transparency: disclosure }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Anti-patterns
- Defaulting analytics and advertising cookies to "on" at sign-up — Law 25 §9.1 requires strictest defaults; users must opt in.
- Delivering consent notices only in English for Quebec residents — French version is mandatory.
- Conflating PIPEDA obligations with Law 25 — the threshold for consent, PIAs, and breach reporting differs; Law 25 is stricter in most respects.
- Starting a new personal information system without a PIA approved by the privacy officer prior to deployment.
- Treating the 72-hour incident window as a hard deadline only; Law 25 requires notification "with due diligence," meaning you should report sooner if details are available.

## Gotchas
- "Serious risk of harm" is the threshold for CAI reporting — define internal criteria (SIN, financial data, health data exposure) in your incident runbook.
- Law 25 applies a data-residency preference for provincial bodies; private-sector entities should still document transfer safeguards for data leaving Quebec.
- The CAI has published a formal administrative complaint form; the API endpoint in this article should target whatever the CAI exposes under your regtech agreement.
- Portability exports must be in a structured, commonly used technological format — JSON (as shown in the DSR portability handler above) satisfies this.
- Law 25's destruction requirement applies to data no longer necessary for its purpose — wire up the `deletion_queue` table to a cron-triggered Worker.

## Verification
1. POST a cookie-setting response through the middleware without `SameSite=Strict` — confirm headers are rewritten.
2. POST a consent record with `language: "es"` — expect HTTP 400.
3. DELETE a consent record and confirm `deletion_queue` row exists with `scheduled_for` 30 days out.
4. POST an incident with `seriousHarmRisk: false` — confirm DB row shows `cai_reported = 0` and response `"not_required"`.
5. POST an algo decision and confirm response includes `humanReviewUrl` and DB row has `human_review_requested = 0`.

## Related
- `/documentation/categories/compliance/pipeda-canada-compliance.md`
- `/documentation/categories/compliance/gdpr-consent-management-cloudflare-workers.md`
- `/documentation/categories/compliance/automated-decision-making-profiling-transparency.md`
- `/documentation/categories/compliance/gdpr-breach-notification-72h.md`
- `/documentation/categories/compliance/data-retention-automated-deletion-workers.md`

## Sources
- Quebec Law 25 (Act 25): https://www.legisquebec.gouv.qc.ca/
- Commission d'accès à l'information (CAI): https://www.cai.gouv.qc.ca/
- Office of the Privacy Commissioner of Canada — Law 25 comparison: https://www.priv.gc.ca/
