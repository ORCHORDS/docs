# Pakistan PECA Content Moderation on Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project serves Pakistani users on an anonymous social platform, triggering obligations under Pakistan's Prevention of Electronic Crimes Act 2016 (PECA) and the accompanying Removal and Blocking of Unlawful Online Content Rules 2021. Operators who fail to act on takedown orders from the Pakistan Telecommunication Authority (PTA) within 24 hours face service blocks and fines up to PKR 500 million. The platform must implement a compliant content removal pipeline without breaking anonymity guarantees for non-targeted users.

## Context

PECA §37 empowers the PTA to direct removal of online content deemed unlawful (blasphemy, anti-state speech, CSAM, defamation). The 2021 Rules extend obligations to "significant social media companies" (500,000+ Pakistani users) and require an in-country presence or registered representative. Cloudflare Workers provide a real-time interception layer that can act on PTA removal orders before content reaches Pakistani users, while Queues decouple audit-log writes from the hot path.

## PECA Obligation Scope — What Workers Must Enforce

PECA §37 and the 2021 Rules impose four primary obligations on the platform:

1. **Takedown within 24 hours** of a PTA order (6 hours for "emergency" orders).
2. **User notification** where technically feasible (with exceptions for national-security orders).
3. **Audit trail** of all removal actions retained for 12 months.
4. **In-country data localisation** — subscriber data of Pakistani users must be stored on servers accessible to Pakistani authorities on request.

Workers intercept every request from Pakistani IPs (`CF-IPCountry: PK`) and query a D1 blocklist before serving content.

```typescript
// workers/peca-gate.ts
export interface Env {
  DB: D1Database;
  PECA_AUDIT: Queue;
  INTERNAL_ORIGIN: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const country = request.headers.get("CF-IPCountry") ?? "";
    if (country !== "PK") {
      return fetch(request); // non-PK requests bypass PECA gate
    }

    const url = new URL(request.url);
    const contentId = url.searchParams.get("id") ?? url.pathname.split("/").pop() ?? "";

    if (contentId) {
      const block = await env.DB.prepare(
        `SELECT order_ref, category, notifiable FROM peca_blocklist
         WHERE content_id = ? AND active = 1 LIMIT 1`
      ).bind(contentId).first<{ order_ref: string; category: string; notifiable: number }>();

      if (block) {
        ctx.waitUntil(
          env.PECA_AUDIT.send({
            event: "peca_block_served",
            content_id: contentId,
            order_ref: block.order_ref,
            category: block.category,
            ts: Date.now(),
          })
        );
        const body = block.notifiable
          ? JSON.stringify({ error: "Content removed under PTA order", ref: block.order_ref })
          : JSON.stringify({ error: "Content unavailable" });
        return new Response(body, { status: 451, headers: { "Content-Type": "application/json" } });
      }
    }

    return fetch(request);
  },
};
```

## Data Subject Rights Implementation

PECA does not itself codify a comprehensive right-to-erasure, but the PTA Personal Data Protection Rules (draft 2023) layer GDPR-style rights on top. Pakistani users may request deletion of their account data held in D1.

```typescript
// workers/pk-erasure.ts
export async function handlePKErasure(
  userId: string,
  env: { DB: D1Database; PECA_AUDIT: Queue }
): Promise<{ deleted: number }> {
  // Soft-delete: mark inactive, retain audit rows per PECA §37 12-month rule
  const result = await env.DB.prepare(
    `UPDATE users SET
       display_name = 'deleted',
       email        = NULL,
       phone        = NULL,
       deleted_at   = CURRENT_TIMESTAMP,
       active       = 0
     WHERE user_id = ? AND country_code = 'PK'`
  ).bind(userId).run();

  await env.DB.prepare(
    `DELETE FROM user_sessions WHERE user_id = ? AND country_code = 'PK'`
  ).bind(userId).run();

  await env.PECA_AUDIT.send({
    event: "pk_erasure_fulfilled",
    user_id: userId,
    ts: Date.now(),
  });

  return { deleted: result.meta.changes };
}
```

## Consent Management

The 2021 Rules require informed, freely-given consent for processing personal data of Pakistani users. For an anonymous platform example project collects only a pseudonymous device token — but if any enrichment (email, phone for OTP) is added, consent must be recorded per-category.

```typescript
// workers/pk-consent.ts
interface PKConsent {
  user_id: string;
  categories: ("otp_phone" | "email_notifications" | "analytics")[];
  ip_hash: string;
  granted_at: number;
}

export async function recordPKConsent(
  consent: PKConsent,
  db: D1Database
): Promise<void> {
  const stmts = consent.categories.map((cat) =>
    db.prepare(
      `INSERT INTO consent_records (user_id, category, country, ip_hash, granted_at)
       VALUES (?, ?, 'PK', ?, ?)
       ON CONFLICT(user_id, category) DO UPDATE SET
         granted_at = excluded.granted_at,
         ip_hash    = excluded.ip_hash`
    ).bind(consent.user_id, cat, consent.ip_hash, consent.granted_at)
  );
  await db.batch(stmts);
}

export async function checkPKConsent(
  userId: string,
  category: string,
  db: D1Database
): Promise<boolean> {
  const row = await db.prepare(
    `SELECT 1 FROM consent_records
     WHERE user_id = ? AND category = ? AND country = 'PK' AND granted_at IS NOT NULL`
  ).bind(userId, category).first();
  return row !== null;
}
```

## Breach Notification

The draft Personal Data Protection Rules require notification to the PTA and affected users within 72 hours of discovering a breach affecting Pakistani residents. The Worker below triggers on a KV sentinel written by the detection pipeline.

```typescript
// workers/pk-breach-notify.ts
export interface Env {
  DB: D1Database;
  BREACH_KV: KVNamespace;
  PTA_NOTIFY_SECRET: string;
}

export async function dispatchPKBreachNotice(
  breachId: string,
  env: Env
): Promise<void> {
  const existing = await env.BREACH_KV.get(`pk_breach:${breachId}`);
  if (existing) return; // already dispatched

  // Record dispatch to prevent double-send
  await env.BREACH_KV.put(`pk_breach:${breachId}`, "dispatched", { expirationTtl: 7 * 86400 });

  // Notify PTA portal (fictitious endpoint — replace with actual PTA API)
  await fetch("https://notify.pta.gov.pk/api/breach", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.PTA_NOTIFY_SECRET}`,
    },
    body: JSON.stringify({
      breach_id: breachId,
      platform: "example.com",
      detected_at: new Date().toISOString(),
      affected_jurisdictions: ["PK"],
    }),
  });

  // Queue per-user notifications for affected Pakistani accounts
  const affected = await env.DB.prepare(
    `SELECT user_id FROM users
     WHERE country_code = 'PK' AND active = 1
       AND user_id IN (SELECT user_id FROM breach_affected WHERE breach_id = ?)`
  ).bind(breachId).all();

  // Fan-out handled by separate notification Worker via Queue
  console.log(`PK breach notice dispatched for ${affected.results.length} users`);
}
```

## Anti-patterns

- Applying PECA blocks globally instead of scoping to `CF-IPCountry: PK` — breaks the platform for non-Pakistani users unnecessarily.
- Logging full content of removed posts in the audit trail — the audit must record the order reference and action taken, not the offending content itself.
- Ignoring "emergency order" SLA: standard orders are 24 h, but emergency orders under Rule 10 require 6-hour compliance — use separate priority queue processing.
- Returning HTTP 404 instead of 451 for PTA-ordered removals — 451 ("Unavailable for Legal Reasons") is the IETF-standard status and supports transparency.
- Deleting audit rows as part of user erasure — PECA §37 mandates 12-month retention of removal-action records regardless of user deletion requests.

## Gotchas

- PECA "significant social media company" threshold is 500,000 Pakistani users — below that threshold, most obligations are voluntary but blocks can still be imposed.
- The 2021 Rules require an in-country data centre or a local representative office; Cloudflare's Islamabad PoP does not substitute for this.
- PTA orders may target a user account (by username/phone) or a URL pattern — your D1 schema must support both `content_id` and `url_pattern` blocklist entries.
- Pakistani courts can separately issue injunctions that override PTA orders; maintain a `court_order` flag in the blocklist with higher precedence.

## Verification

1. Seed `peca_blocklist` with a test `content_id` and `active = 1`.
2. Send a request with `CF-IPCountry: PK` header (use Wrangler `--header` flag locally) and confirm a `451` response.
3. Send the same request with `CF-IPCountry: US` and confirm content is served normally.
4. Trigger `handlePKErasure` for a seeded PK user and verify `users.deleted_at` is set but audit rows remain.
5. Call `dispatchPKBreachNotice` twice with the same `breachId` and confirm the PTA endpoint is called exactly once.

## Related

- [GDPR Breach Notification 72h](gdpr-breach-notification-72h.md)
- [CSAM Detection and NCMEC Reporting](csam-detection-ncmec-reporting-plumbing.md)
- [DSA Trusted Flaggers Content Moderation](dsa-trusted-flaggers-content-moderation.md)
- [Cross-Border Data Transfer Cloudflare Workers](cross-border-data-transfer-cloudflare-workers.md)

## Sources

- Prevention of Electronic Crimes Act 2016: https://pta.gov.pk/en/peca
- Removal and Blocking of Unlawful Online Content Rules 2021: https://pta.gov.pk/en/media-center/single-media/rules-2021
- PTA Personal Data Protection Rules (draft): https://pta.gov.pk/en/data-protection
- Cloudflare Workers `CF-IPCountry` header docs: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- IETF RFC 7725 — HTTP 451: https://tools.ietf.org/html/rfc7725
