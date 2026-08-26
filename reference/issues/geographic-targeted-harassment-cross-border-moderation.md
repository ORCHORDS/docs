# Geographic Targeted Harassment — Cross-Border Moderation Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A cluster of anonymous accounts sends coordinated abusive content specifically targeting users in a
single country, city, or post-code. The abuse may be ethnicity-based, politically motivated, or
triggered by a real-world event (election, protest, natural disaster). Because example project is
anonymous, standard user-graph signals (mutual follows, verified identity) are absent. Platform
receives regulatory pressure from local authorities to act, but cross-jurisdictional legal standards
differ: what is lawful speech in one country is a criminal offence in another.

---

## Context

Geographic targeting makes harassment especially harmful:

1. **Amplified fear** — messages referencing a victim's neighbourhood or local landmarks increase
   perceived physical threat.
2. **Coordinated pile-ons** — many attackers, same target geography, short time window = viral harm.
3. **Jurisdictional complexity** — the EU NIS2 / DSA framework, UK Online Safety Act 2023, and
   Australian Online Safety Act 2021 each impose different takedown timelines and geo-blocking duties.
4. **Anonymous attacker network** — conventional IP-based detection is evaded through VPNs, Tor,
   and mobile data rotation.

Workers AI can score geographic harassment signals. Cloudflare's `CF-IPCountry` / `CF-IPCity`
request headers give originating geography without a third-party geolocation API call.

---

## Architecture

```
Incoming post → Worker (geo-enrich → harassment score)
             → D1 (geo_abuse_events)
             → Durable Object (per-target geo rate-counter)
             → Queues (moderation-action-queue)
                 → shadow-restrict, notify-victim, geo-block
```

---

## Implementation

### 1. Geo-Enrichment Middleware

```typescript
// src/middleware/geo-enrich.ts

export interface GeoContext {
  countryCode: string;   // e.g. "DE"
  city: string;          // e.g. "Berlin"
  region: string;        // e.g. "BE"
  asn: string;           // Autonomous System Number
}

export function extractGeo(request: Request): GeoContext {
  const cf = (request as Request & { cf?: Record<string, string> }).cf ?? {};
  return {
    countryCode: cf['country'] ?? 'XX',
    city:        cf['city']    ?? '',
    region:      cf['region']  ?? '',
    asn:         cf['asn']     ?? '0',
  };
}
```

### 2. Harassment Scoring — Workers AI

```typescript
// src/scoring/geo-harassment.ts
import type { Env } from '../types';

export interface HarassmentScore {
  score: number;          // 0.0 – 1.0
  isGeoTargeted: boolean;
  signals: string[];
}

const GEO_HARASSMENT_PROMPT = (content: string, targetCity: string) => `
You are a content moderation classifier for an anonymous social platform.

Post content: """${content}"""
Reported target location: ${targetCity}

Determine whether this post constitutes geographically targeted harassment.
Signals to look for:
- Direct references to the target's neighbourhood, city landmarks, or local events
- Threatening language combined with location-specific detail
- Slurs correlated with ethnic groups predominantly in that region
- "We know where you are" or equivalent implicit threat

Respond ONLY with JSON:
{
  "score": <0.0–1.0>,
  "is_geo_targeted": <boolean>,
  "signals": [<array of signal descriptions, max 5>]
}
`.trim();

export async function scoreGeoHarassment(
  content: string,
  targetCity: string,
  env: Env,
): Promise<HarassmentScore> {
  const result = await env.AI.run('@cf/meta/llama-3.3-70b-instruct-fp8-fast', {
    prompt: GEO_HARASSMENT_PROMPT(content, targetCity),
    max_tokens: 200,
  });

  try {
    const parsed = JSON.parse((result as { response: string }).response);
    return {
      score: Number(parsed.score ?? 0),
      isGeoTargeted: Boolean(parsed.is_geo_targeted),
      signals: Array.isArray(parsed.signals) ? parsed.signals : [],
    };
  } catch {
    return { score: 0, isGeoTargeted: false, signals: [] };
  }
}
```

### 3. Durable Object — Per-Target Geographic Burst Counter

```typescript
// src/durable-objects/geo-burst-counter.ts

export class GeoBurstCounter {
  private state: DurableObjectState;
  private events: number[] = [];

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/record') {
      return this.record();
    }
    if (url.pathname === '/count') {
      return this.count();
    }
    return new Response('Not found', { status: 404 });
  }

  private async record(): Promise<Response> {
    const now = Date.now();
    const windowMs = 60 * 60 * 1000; // 1-hour rolling window

    // Load existing events from storage
    const stored = await this.state.storage.get<number[]>('events') ?? [];
    const fresh = stored.filter((t) => now - t < windowMs);
    fresh.push(now);

    await this.state.storage.put('events', fresh);
    return Response.json({ count: fresh.length });
  }

  private async count(): Promise<Response> {
    const now = Date.now();
    const windowMs = 60 * 60 * 1000;
    const stored = await this.state.storage.get<number[]>('events') ?? [];
    const fresh = stored.filter((t) => now - t < windowMs);
    return Response.json({ count: fresh.length });
  }
}
```

### 4. Main Handler — Orchestration

```typescript
// src/handlers/post.ts
import { extractGeo } from '../middleware/geo-enrich';
import { scoreGeoHarassment } from '../scoring/geo-harassment';
import type { Env } from '../types';

const GEO_BURST_THRESHOLD = 15; // >15 geo-targeted posts at same target/hour
const SCORE_AUTO_RESTRICT  = 0.80;
const SCORE_QUEUE_REVIEW   = 0.55;

export async function handlePost(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{ content: string; targetUserId?: string }>();
  const geo  = extractGeo(request);
  const postId = crypto.randomUUID();

  // Score for geographic harassment
  const harassment = await scoreGeoHarassment(
    body.content,
    geo.city,
    env,
  );

  // Persist event
  await env.DB.prepare(
    `INSERT INTO geo_abuse_events
       (post_id, country_code, city, asn, score, is_geo_targeted, signals, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, unixepoch())`,
  ).bind(
    postId,
    geo.countryCode,
    geo.city,
    geo.asn,
    harassment.score,
    harassment.isGeoTargeted ? 1 : 0,
    JSON.stringify(harassment.signals),
  ).run();

  if (harassment.isGeoTargeted && body.targetUserId) {
    // Increment burst counter for this target
    const doId = env.GEO_BURST_COUNTER.idFromName(body.targetUserId);
    const stub = env.GEO_BURST_COUNTER.get(doId);
    const countResp = await stub.fetch('https://internal/record');
    const { count } = await countResp.json<{ count: number }>();

    if (count >= GEO_BURST_THRESHOLD) {
      await env.MODERATION_QUEUE.send({
        postId,
        action: 'geo_burst_restrict',
        targetUserId: body.targetUserId,
        burstCount: count,
        countryCode: geo.countryCode,
      });
    }
  }

  if (harassment.score >= SCORE_AUTO_RESTRICT) {
    await env.MODERATION_QUEUE.send({ postId, action: 'auto_restrict' });
    return Response.json({ postId, status: 'held' });
  }
  if (harassment.score >= SCORE_QUEUE_REVIEW) {
    await env.MODERATION_QUEUE.send({ postId, action: 'human_review' });
  }

  return Response.json({ postId, status: 'accepted' });
}
```

### 5. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS geo_abuse_events (
  post_id        TEXT PRIMARY KEY,
  country_code   TEXT NOT NULL,
  city           TEXT NOT NULL DEFAULT '',
  asn            TEXT NOT NULL DEFAULT '0',
  score          REAL NOT NULL DEFAULT 0.0,
  is_geo_targeted INTEGER NOT NULL DEFAULT 0,
  signals        TEXT,                          -- JSON array
  created_at     INTEGER NOT NULL,
  moderation_action TEXT                        -- nullable, filled after action
);

CREATE INDEX idx_geo_abuse_country ON geo_abuse_events(country_code, created_at DESC);
CREATE INDEX idx_geo_abuse_score   ON geo_abuse_events(score DESC, created_at DESC);

-- Jurisdiction-specific policy overrides
CREATE TABLE IF NOT EXISTS geo_policy_overrides (
  country_code   TEXT PRIMARY KEY,
  auto_restrict_threshold REAL NOT NULL DEFAULT 0.80,
  takedown_hours INTEGER NOT NULL DEFAULT 24,  -- DSA Art 17 / local law
  notes          TEXT
);

INSERT OR IGNORE INTO geo_policy_overrides VALUES ('DE', 0.65, 4, 'NetzDG 24h rule');
INSERT OR IGNORE INTO geo_policy_overrides VALUES ('AU', 0.70, 24, 'Online Safety Act 2021');
INSERT OR IGNORE INTO geo_policy_overrides VALUES ('GB', 0.70, 24, 'Online Safety Act 2023');
```

---

## Anti-patterns

- **Treating all harassment the same regardless of geography** — a post referencing a user's suburb
  alongside a threatening phrase is categorically more dangerous than generic hate speech; the burst
  counter must be scoped per `(targetUserId, countryCode)` to catch region-specific pile-ons.
- **Relying on `CF-IPCountry` as attacker location** — a VPN user's declared country is fictitious;
  use it only as one signal, not as a definitive geographic origin.
- **Applying a single moderation threshold globally** — `geo_policy_overrides` table allows
  per-country thresholds; Germany's NetzDG mandates a much shorter removal window than most.
- **Notifying the attacker of geo-burst restriction** — doing so teaches attackers to stay below
  the burst threshold.

---

## Gotchas

- `request.cf` is available only in production Workers; in `wrangler dev` it returns `undefined`.
  Always provide fallback values (`'XX'`, `''`) to prevent null-pointer errors in local testing.
- Durable Object IDs derived from `targetUserId` must be stable. If user IDs are rotated (anonymous
  session refresh), the counter resets — consider hashing the canonical account token instead.
- DSA Art. 17 requires a reason to be given to the content creator when content is restricted; the
  moderation action queue consumer must include this notification step.
- `CF-IPCity` is not always populated (cellular carriers, some ISPs aggregate to country only).
  Fall back gracefully: score on available signals, do not hard-fail.

---

## Verification

```sql
-- Top target cities receiving geo-targeted posts in last 6 hours
SELECT city, country_code, COUNT(*) AS posts,
       AVG(score) AS avg_score
FROM geo_abuse_events
WHERE is_geo_targeted = 1
  AND created_at > unixepoch() - 21600
GROUP BY city, country_code
ORDER BY posts DESC
LIMIT 20;

-- Jurisdiction SLA compliance check (takedown within required hours)
SELECT g.country_code,
       o.takedown_hours,
       COUNT(*) FILTER (WHERE g.moderation_action IS NULL
         AND (unixepoch() - g.created_at) / 3600 > o.takedown_hours) AS overdue
FROM geo_abuse_events g
JOIN geo_policy_overrides o ON g.country_code = o.country_code
WHERE g.score >= o.auto_restrict_threshold
GROUP BY g.country_code;
```

---

## Related

- `cross-border-data-localization-user-content.md` — data residency requirements
- `harassment-pattern-detection-durable-objects.md` — general harassment burst detection
- `vpn-proxy-detection-geo-restrictions.md` — VPN/proxy evasion detection
- `court-ordered-geo-blocking-injunction-compliance-d1.md` — compelled geo-blocks
- `hate-speech-detection-multilingual-workers-ai.md` — multilingual hate speech

---

## Sources

- Cloudflare Workers — request.cf properties: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- DSA Art. 17 — Statement of Reasons: https://digital-strategy.ec.europa.eu/en/policies/digital-services-act-package
- UK Online Safety Act 2023: https://www.legislation.gov.uk/ukpga/2023/50
- Australian Online Safety Act 2021: https://www.legislation.gov.au/Details/C2021A00076
- German NetzDG (Network Enforcement Act): https://www.gesetze-im-internet.de/netzdg/
