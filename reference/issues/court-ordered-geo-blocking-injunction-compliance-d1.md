# Court-Ordered Geo-Blocking & Injunction Compliance in Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project receives a court injunction, government blocking order, or regulatory directive requiring that specific content (posts, accounts, topics) be inaccessible to users in a named jurisdiction. Examples: a German court orders removal of extremist content from German IP ranges; an Indian IT Act s.69A blocking notice arrives for a viral post; a UK Online Safety Act s.104 Access Restriction Order targets an entire account. The platform must comply within the legally specified window (often 24–72 hours), maintain an audit trail, and be able to reverse the block if the order is appealed or expires.

## Context

Unlike voluntary geo-restrictions (VPN blocking, NSFW gating), court orders carry legal deadlines, require documented compliance evidence, and may themselves be confidential (e.g., US 18 U.S.C. §2703(d) court orders carry gag provisions). The compliance implementation must:

1. Take effect at the edge within the required window.
2. Log the activation with an immutable timestamp for the evidence record.
3. Serve a legally appropriate response to blocked users (not a 404 — must indicate restriction, per DSA Art. 17).
4. Support time-bounded expiry and reverse with an audit trail.
5. Not expose the existence of a gag-ordered blocking directive in error messages or headers.

## 1. Injunction Registry Table in D1

```sql
-- migration: 0045_injunction_registry.sql
CREATE TABLE injunctions (
  id              TEXT PRIMARY KEY,
  reference       TEXT NOT NULL,          -- internal docket number
  issuing_body    TEXT NOT NULL,          -- "Landgericht Hamburg", "MeitY IN", etc.
  jurisdiction    TEXT NOT NULL,          -- ISO 3166-1 alpha-2, e.g. "DE", "IN", "GB"
  target_type     TEXT NOT NULL,          -- 'post' | 'account' | 'topic' | 'domain'
  target_id       TEXT NOT NULL,
  block_type      TEXT NOT NULL DEFAULT 'access_restriction',
  effective_at    INTEGER NOT NULL,
  expires_at      INTEGER,                -- NULL = indefinite
  gag_order       INTEGER NOT NULL DEFAULT 0,
  activated_at    INTEGER,
  activated_by    TEXT,
  revoked_at      INTEGER,
  revoked_by      TEXT,
  evidence_r2_key TEXT                    -- R2 key storing the sealed order PDF
);

CREATE INDEX idx_injunction_jurisdiction ON injunctions (jurisdiction, target_type, target_id);
CREATE INDEX idx_injunction_active ON injunctions (effective_at, expires_at) WHERE revoked_at IS NULL;
```

## 2. Injunction Activation Worker (Legal Ops Tool)

```typescript
// src/legal/activate-injunction.ts
import type { Env } from "../types";

export async function activateInjunction(
  env: Env,
  params: {
    reference: string;
    issuingBody: string;
    jurisdiction: string;      // ISO-3166-1 alpha-2
    targetType: "post" | "account" | "topic" | "domain";
    targetId: string;
    effectiveAt: number;       // Unix ms
    expiresAt?: number;
    gagOrder: boolean;
    orderPdfBytes?: ArrayBuffer;
    activatedBy: string;       // operator email
  }
): Promise<string> {
  const id = crypto.randomUUID();

  // Seal the order PDF in R2 with server-side encryption
  let r2Key: string | null = null;
  if (params.orderPdfBytes) {
    r2Key = `legal/injunctions/${id}/order.pdf`;
    await env.LEGAL_BUCKET.put(r2Key, params.orderPdfBytes, {
      httpMetadata: { contentType: "application/pdf" },
      customMetadata: { reference: params.reference, jurisdiction: params.jurisdiction },
    });
  }

  await env.DB.prepare(
    `INSERT INTO injunctions
       (id, reference, issuing_body, jurisdiction, target_type, target_id,
        effective_at, expires_at, gag_order, activated_at, activated_by, evidence_r2_key)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    id, params.reference, params.issuingBody, params.jurisdiction,
    params.targetType, params.targetId,
    params.effectiveAt, params.expiresAt ?? null,
    params.gagOrder ? 1 : 0,
    Date.now(), params.activatedBy, r2Key
  ).run();

  // Push to KV for O(1) edge lookup
  await env.KV_INJUNCTIONS.put(
    `inj:${params.jurisdiction}:${params.targetType}:${params.targetId}`,
    JSON.stringify({ id, expiresAt: params.expiresAt ?? null, gagOrder: params.gagOrder }),
    { expirationTtl: params.expiresAt
        ? Math.ceil((params.expiresAt - Date.now()) / 1000) + 3600
        : undefined }
  );

  return id;
}
```

## 3. Edge Enforcement in the Main Request Worker

```typescript
// src/middleware/injunction-gate.ts
interface InjunctionRecord {
  id: string;
  expiresAt: number | null;
  gagOrder: boolean;
}

export async function enforceInjunctions(
  request: Request,
  env: Env,
  targetType: string,
  targetId: string
): Promise<Response | null> {
  const country = request.cf?.country ?? "XX";
  if (country === "XX") return null; // unknown country — pass through

  const key = `inj:${country}:${targetType}:${targetId}`;
  const raw = await env.KV_INJUNCTIONS.get(key);
  if (!raw) return null;

  const inj: InjunctionRecord = JSON.parse(raw);

  // Check expiry
  if (inj.expiresAt && Date.now() > inj.expiresAt) {
    await env.KV_INJUNCTIONS.delete(key);
    return null;
  }

  // DSA Art. 17 requires the restriction reason be communicated UNLESS gag order
  if (inj.gagOrder) {
    // Generic "not available" — do not mention legal order
    return new Response("This content is not available in your region.", {
      status: 451,
      headers: { "Content-Type": "text/plain" },
    });
  }

  // Non-gag: RFC 7725 compliance — 451 with Link header pointing to explanation
  return new Response("Access to this content has been restricted by court order.", {
    status: 451,
    headers: {
      "Content-Type": "text/plain",
      "Link": `<https://example.com/legal/restrictions/${inj.id}>; rel="blocked-by"`,
    },
  });
}
```

## 4. Expiry & Revocation Worker (Scheduled)

```typescript
// src/legal/injunction-expiry.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const now = Date.now();
    const { results } = await env.DB.prepare(
      `SELECT id, jurisdiction, target_type, target_id
       FROM injunctions
       WHERE expires_at IS NOT NULL
         AND expires_at < ?
         AND revoked_at IS NULL`
    ).bind(now).all<{
      id: string; jurisdiction: string; target_type: string; target_id: string;
    }>();

    for (const inj of results) {
      const key = `inj:${inj.jurisdiction}:${inj.target_type}:${inj.target_id}`;
      await env.KV_INJUNCTIONS.delete(key);
      await env.DB.prepare(
        `UPDATE injunctions SET revoked_at = ?, revoked_by = 'system:expiry'
         WHERE id = ?`
      ).bind(now, inj.id).run();
    }
  },
};
```

## 5. Compliance Evidence Export

```typescript
// src/legal/compliance-report.ts
export async function buildComplianceEvidence(
  env: Env,
  injunctionId: string
): Promise<ComplianceBundle> {
  const inj = await env.DB.prepare(
    "SELECT * FROM injunctions WHERE id = ?"
  ).bind(injunctionId).first<Injunction>();

  if (!inj) throw new Error(`Injunction ${injunctionId} not found`);

  const orderPdf = inj.evidence_r2_key
    ? await env.LEGAL_BUCKET.get(inj.evidence_r2_key)
    : null;

  return {
    injunctionId: inj.id,
    reference: inj.reference,
    jurisdiction: inj.jurisdiction,
    activatedAt: new Date(inj.activated_at!).toISOString(),
    revokedAt: inj.revoked_at ? new Date(inj.revoked_at).toISOString() : null,
    orderPdfPresent: !!orderPdf,
    // Suitable for submission as Annex to compliance filing
  };
}
```

## Anti-patterns

- **Returning 404** — RFC 7725 and DSA Art. 17 require HTTP 451; 404 constitutes misrepresentation.
- **Exposing injunction ID in gag-order responses** — the ID can be used to infer the existence of a sealed order.
- **Storing jurisdiction blocks only in D1** — D1 read latency adds ~10 ms per request; KV cache is mandatory for edge enforcement.
- **Deleting the order record on expiry** — legal holds may require retention of the injunction record for 7 years; only set `revoked_at`, never DELETE.

## Gotchas

- KV `expirationTtl` is in seconds; add a 3600 s buffer so the edge KV entry outlives the DB record — the scheduled worker cleans up the DB side.
- `request.cf?.country` is populated by Cloudflare's GeoIP; it can be absent (`null`) on localhost dev — always default to `"XX"` and pass through.
- Some injunctions cover multiple jurisdictions — model as separate `injunctions` rows, one per country code, sharing the same `reference`.
- Indian IT Act s.69A orders carry a 48-hour compliance window from receipt; log `effective_at` from the order date, not the activation date.

## Verification

```bash
# Confirm KV key is set for a test injunction
wrangler kv:key get --namespace-id=$KV_INJUNCTIONS_ID "inj:DE:post:test-post-123"

# Test 451 response from German PoP (simulate with header)
curl -H "CF-IPCountry: DE" https://example project.example.com/post/test-post-123 -i | head -5
# Expected: HTTP/2 451

# List active injunctions with upcoming expiry
wrangler d1 execute example project-db --command \
  "SELECT id, jurisdiction, target_id, expires_at FROM injunctions
   WHERE revoked_at IS NULL AND expires_at < $(( $(date +%s) + 604800 ))000
   ORDER BY expires_at;"
```

## Related

- `vpn-proxy-detection-geo-restrictions.md`
- `legal-hold-evidence-preservation-d1-r2.md`
- `platform-liability-section-230-dsa.md`
- `user-privacy-law-enforcement-requests.md`
- `cross-border-data-localization-user-content.md`

## Sources

- RFC 7725 — An HTTP Status Code to Report Legal Obstacles
- DSA Article 17 — Statement of reasons
- UK Online Safety Act 2023, s.104 — Access restriction orders
- Indian IT Act 2000, s.69A — Power to block public access
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
