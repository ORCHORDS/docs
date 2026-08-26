# CMMC 2.0 Level 2 — CUI Protection via Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your organisation is a US Department of Defense (DoD) contractor or sub-contractor that handles Controlled Unclassified Information (CUI) in a web application running on Cloudflare Workers. You need to demonstrate CMMC 2.0 Level 2 conformance — which maps 1:1 to the 110 practices of NIST SP 800-171 Rev 2 — prior to contract award or renewal.

## Context
CMMC 2.0 (Cybersecurity Maturity Model Certification) was finalised in the 32 CFR Part 170 rule effective December 2024. Level 2 covers DIB (Defense Industrial Base) companies handling CUI that is not deemed "critical programs." Level 2 requires a triennial third-party assessment (C3PAO) or annual self-assessment with a signed executive affirmation in SPRS. The 110 practices span 14 domains including Access Control (AC), Audit and Accountability (AU), Configuration Management (CM), Incident Response (IR), and System and Communications Protection (SC). Cloudflare Workers satisfy the boundary controls for CUI-processing applications when Workers are configured as the exclusive ingress/egress point.

## Access Control — CUI Boundary Enforcement (AC.L2-3.1.1 / 3.1.2)

NIST SP 800-171 AC.3.1.1 requires limiting system access to authorised users and processes. Workers act as the CUI boundary enforcing authenticated sessions and role checks before any CUI is read or written.

```typescript
// workers/cui-access-control.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
  JWT_SECRET: string;
  CUI_CATEGORY: string; // e.g. "PRVCY" "OPSEC"
}

interface SessionClaims {
  sub: string;
  roles: string[];
  clearanceLevel: "none" | "cui" | "cui_specified";
  exp: number;
}

async function verifyJwt(token: string, secret: string): Promise<SessionClaims | null> {
  try {
    const [headerB64, payloadB64, sigB64] = token.split(".");
    const encoder = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
      "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]
    );
    const data = encoder.encode(`${headerB64}.${payloadB64}`);
    const sig = Uint8Array.from(atob(sigB64.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
    const valid = await crypto.subtle.verify("HMAC", keyMaterial, sig, data);
    if (!valid) return null;
    return JSON.parse(atob(payloadB64)) as SessionClaims;
  } catch {
    return null;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const authHeader = request.headers.get("Authorization") ?? "";
    const token = authHeader.replace(/^Bearer\s+/, "");

    const claims = await verifyJwt(token, env.JWT_SECRET);
    if (!claims || claims.exp < Math.floor(Date.now() / 1000)) {
      return new Response(JSON.stringify({ error: "Unauthorized — CMMC AC.L2-3.1.1" }), {
        status: 401, headers: { "Content-Type": "application/json" },
      });
    }

    if (!["cui", "cui_specified"].includes(claims.clearanceLevel)) {
      // AC.L2-3.1.2: limit access to types of transactions users are authorised to execute
      await env.DB.prepare(
        "INSERT INTO access_violations (sub, path, reason, ts) VALUES (?, ?, 'insufficient_clearance', ?)"
      ).bind(claims.sub, new URL(request.url).pathname, new Date().toISOString()).run();
      return new Response(JSON.stringify({ error: "Forbidden — CUI access requires cui clearance level" }), { status: 403 });
    }

    const response = await fetch(request);
    return new Response(response.body, {
      status: response.status,
      headers: { ...Object.fromEntries(response.headers), "X-CUI-Category": env.CUI_CATEGORY },
    });
  },
};
```

## Audit and Accountability — Immutable CUI Access Log (AU.L2-3.3.1 / 3.3.2)

NIST SP 800-171 AU.3.3.1 requires audit logging of events sufficient to reconstruct actions involving CUI. Logs must be protected from unauthorised modification (AU.3.3.2).

```typescript
// workers/cui-audit-log.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env { DB: D1Database; AUDIT_HMAC_KEY: string; }

export interface AuditEvent {
  userId: string;
  action: "read" | "write" | "delete" | "export";
  resource: string;
  cuiCategory: string;
  ipAddress: string;
  outcome: "success" | "failure";
  detail?: string;
}

export async function logCuiEvent(event: AuditEvent, env: Env): Promise<string> {
  const eventId = crypto.randomUUID();
  const ts = new Date().toISOString();

  // Compute HMAC to detect tampering (AU.L2-3.3.2)
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(env.AUDIT_HMAC_KEY), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const payload = JSON.stringify({ eventId, ts, ...event });
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(payload));
  const hmac = Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, "0")).join("");

  await env.DB.prepare(
    `INSERT INTO cui_audit_log
       (id, user_id, action, resource, cui_category, ip_address, outcome, detail, hmac, ts)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    eventId, event.userId, event.action, event.resource,
    event.cuiCategory, event.ipAddress, event.outcome,
    event.detail ?? null, hmac, ts
  ).run();

  return eventId;
}

export async function verifyLogIntegrity(env: Env, limit = 1000): Promise<{ valid: number; tampered: number }> {
  const rows = await env.DB.prepare(
    "SELECT * FROM cui_audit_log ORDER BY ts DESC LIMIT ?"
  ).bind(limit).all<{ id: string; hmac: string; [key: string]: unknown }>();

  let valid = 0, tampered = 0;
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(env.AUDIT_HMAC_KEY), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]
  );

  for (const row of rows.results) {
    const { hmac, ...rest } = row;
    const payload = JSON.stringify(rest);
    const sigBytes = Uint8Array.from(hmac.match(/../g)!.map(h => parseInt(h, 16)));
    const ok = await crypto.subtle.verify("HMAC", key, sigBytes, encoder.encode(payload));
    ok ? valid++ : tampered++;
  }

  return { valid, tampered };
}
```

## Configuration Management — CUI System Baseline (CM.L2-3.4.1)

NIST SP 800-171 CM.3.4.1 requires an established baseline configuration for organisational systems processing CUI. Record Worker binding versions and environment hashes at deploy time.

```typescript
// workers/baseline-recorder.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env { DB: D1Database; WORKER_VERSION: string; DEPLOY_TOKEN: string; }

interface BaselinePayload {
  deployId: string;
  workerName: string;
  bindingHashes: Record<string, string>; // binding name -> content hash
  envVarNames: string[];                  // names only, no values
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const authHeader = request.headers.get("Authorization");
    if (authHeader !== `Bearer ${env.DEPLOY_TOKEN}`) return new Response("Unauthorized", { status: 401 });

    const body = await request.json<BaselinePayload>();
    const now = new Date().toISOString();

    await env.DB.prepare(
      `INSERT INTO cm_baselines
         (deploy_id, worker_name, worker_version, binding_hashes, env_var_names, recorded_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      body.deployId, body.workerName, env.WORKER_VERSION,
      JSON.stringify(body.bindingHashes), JSON.stringify(body.envVarNames), now
    ).run();

    return new Response(JSON.stringify({ deployId: body.deployId, baselineRecordedAt: now }), {
      status: 201, headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Incident Response — CUI Incident Triage and DIBNET-PR Notification (IR.L2-3.6.2)

NIST SP 800-171 IR.3.6.2 requires reporting incidents involving CUI to appropriate authorities. DoD contractors must file in DIBNET-PR (now DC3's online portal) within 72 hours of discovery.

```typescript
// workers/cui-incident-reporter.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
  DC3_NOTIFY_ENDPOINT: string;
  DC3_API_KEY: string;
  CONTRACTOR_CAGE_CODE: string;
}

interface CuiIncident {
  incidentId: string;
  cuiCategories: string[];
  affectedSystems: string[];
  compromiseType: "confidentiality" | "integrity" | "availability" | "multiple";
  detectedAt: string;
  summary: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<CuiIncident>();
    const hoursElapsed = (Date.now() - new Date(body.detectedAt).getTime()) / 3_600_000;

    const dibnetPayload = {
      cage_code: env.CONTRACTOR_CAGE_CODE,
      incident_id: body.incidentId,
      detected_at: body.detectedAt,
      reported_at: new Date().toISOString(),
      cui_categories: body.cuiCategories,
      affected_systems: body.affectedSystems,
      compromise_type: body.compromiseType,
      summary: body.summary,
      hours_to_report: Math.round(hoursElapsed),
      nist_ref: "SP 800-171 IR.3.6.2",
    };

    const resp = await fetch(env.DC3_NOTIFY_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-DC3-Key": env.DC3_API_KEY },
      body: JSON.stringify(dibnetPayload),
    });

    await env.DB.prepare(
      `INSERT INTO cui_incidents
         (id, cage_code, cui_categories, compromise_type, hours_elapsed, dc3_status, reported_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      body.incidentId, env.CONTRACTOR_CAGE_CODE, JSON.stringify(body.cuiCategories),
      body.compromiseType, Math.round(hoursElapsed), resp.status, new Date().toISOString()
    ).run();

    return new Response(JSON.stringify({ dc3Status: resp.status, hoursElapsed: Math.round(hoursElapsed) }), {
      status: resp.ok ? 200 : 502,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Anti-patterns
- Using a Workers environment variable to store CUI content — Workers environment variables are configuration, not a CUI data store; use D1 with encrypted columns or R2 with SSE.
- Sharing a single JWT signing key between CUI and non-CUI Workers — CMMC requires system boundary isolation; separate keys enforce the boundary.
- Omitting the SPRS score submission after self-assessment — even a perfect-practice company must submit via PIEE/SPRS within 90 days of assessment.
- Treating CMMC Level 1 practices (basic cyber hygiene) as sufficient for Level 2 — Level 2 adds 100 additional practices from NIST SP 800-171.
- Neglecting subcontractor flow-down — CMMC applies to every tier that receives or generates CUI under the prime contract; audit D1 query patterns for CUI shared with third-party Workers.

## Gotchas
- Cloudflare's FedRAMP Moderate ATO covers specific services; verify which Workers features (AI, D1, KV, Queues) are within the FedRAMP boundary before CUI processing.
- CMMC 2.0 requires multi-factor authentication for all privileged accounts (IA.L2-3.5.3) — enforce MFA at the identity provider upstream of the Workers JWT issuer.
- Audit log retention must meet the 3-year retention period specified in CUI Executive Order 13556 implementing guidance; configure D1 data lifecycle accordingly.
- CMMC allows Plan of Action and Milestones (POA&M) for deficiencies but limits total open POA&M practices to avoid assessment failure.
- System Security Plan (SSP) must reference Workers-specific boundary diagrams; generic cloud diagrams are insufficient for C3PAO assessors.

## Verification
1. Send a request without a Bearer token — expect HTTP 401 with CMMC reference in body.
2. Send with a valid JWT but `clearanceLevel: "none"` — expect HTTP 403 and confirm `access_violations` row inserted.
3. Call `logCuiEvent` then `verifyLogIntegrity` — confirm `tampered: 0`.
4. Manually flip a single byte in `cui_audit_log.detail` and re-run `verifyLogIntegrity` — confirm `tampered: 1`.
5. POST a CUI incident and confirm `cui_incidents` row exists with `dc3_status = 200` and `hours_elapsed` accurate.

## Related
- `/documentation/categories/compliance/fedramp-compliance.md`
- `/documentation/categories/compliance/nist-800-53-control-families.md`
- `/documentation/categories/compliance/nist-sp-800-171ar3-assessment-evidence-traceability.md`
- `/documentation/categories/compliance/audit-log-mandatory.md`
- `/documentation/categories/compliance/security-incident-response-plan.md`

## Sources
- 32 CFR Part 170 — CMMC 2.0 Final Rule: https://www.federalregister.gov/documents/2024/10/15/2024-23960
- NIST SP 800-171 Rev 2: https://csrc.nist.gov/publications/detail/sp/800-171/rev-2/final
- DoD CUI Registry: https://www.archives.gov/cui
- DC3 Cyber Crime Center DIBNet Portal: https://dibnet.dod.mil/
