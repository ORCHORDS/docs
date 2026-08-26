# Spam Link Domain Reputation Scoring with Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project users post shortened URLs and redirecting links that resolve to phishing pages,
scam storefronts, cryptocurrency fraud, or malware distribution networks. Exact-match
blocklists catch known-bad domains but miss newly registered or fast-flux domains. A
domain reputation system combines static blocklist lookup, registration-age heuristics,
redirect chain resolution, and historical violation counts (stored in D1) to produce a
per-domain risk score that the post-creation pipeline queries synchronously.

---

## Context

Every URL extracted from a post body is normalized and its apex domain resolved to a risk
tier. The lookup runs inside a Cloudflare Worker with a D1 violation-history store and a
KV-cached reputation index. Domains scoring above the HIGH threshold are suppressed from
the post; MEDIUM-risk links are rendered without preview and flagged for async review via
a Queue. The pipeline resolves redirect chains (up to 5 hops) before scoring, so link
shorteners do not evade the check.

---

## 1. URL Extraction and Normalization

```typescript
// lib/url-extractor.ts

const URL_PATTERN = /https?:\/\/[^\s<>"']+/gi;

export interface ExtractedLink {
  raw: string;
  normalized: string;
  apexDomain: string;
}

export function extractLinks(text: string): ExtractedLink[] {
  const matches = text.match(URL_PATTERN) ?? [];
  const seen = new Set<string>();
  const results: ExtractedLink[] = [];

  for (const raw of matches) {
    try {
      const url = new URL(raw);
      const normalized = `${url.protocol}//${url.hostname}${url.pathname}`;
      const apexDomain = extractApexDomain(url.hostname);

      if (!seen.has(apexDomain)) {
        seen.add(apexDomain);
        results.push({ raw, normalized, apexDomain });
      }
    } catch {
      // Malformed URL — skip
    }
  }

  return results;
}

function extractApexDomain(hostname: string): string {
  // Naive public-suffix extraction: last two labels
  // Replace with publicsuffix.org list for production accuracy
  const parts = hostname.split('.');
  if (parts.length <= 2) return hostname;
  return parts.slice(-2).join('.');
}
```

---

## 2. Redirect Chain Resolver

```typescript
// lib/redirect-resolver.ts

const MAX_HOPS = 5;
const TIMEOUT_MS = 3000;

export async function resolveRedirectChain(url: string): Promise<string[]> {
  const chain: string[] = [url];
  let current = url;

  for (let i = 0; i < MAX_HOPS; i++) {
    let res: Response;
    try {
      res = await fetch(current, {
        method: 'HEAD',
        redirect: 'manual',
        signal: AbortSignal.timeout(TIMEOUT_MS),
        headers: { 'User-Agent': 'example project SafeLink/1.0 (moderation probe)' },
      });
    } catch {
      break; // Network error or timeout — score what we have
    }

    if (res.status >= 300 && res.status < 400) {
      const location = res.headers.get('Location');
      if (!location || location === current) break;
      current = location.startsWith('http') ? location : new URL(location, current).toString();
      chain.push(current);
    } else {
      break;
    }
  }

  return chain; // Final element is the resolved destination
}
```

---

## 3. D1 Domain Violation History

```sql
-- migration 0021_domain_reputation.sql
CREATE TABLE IF NOT EXISTS domain_violations (
  apex_domain      TEXT    NOT NULL,
  violation_type   TEXT    NOT NULL,   -- 'phishing' | 'malware' | 'scam' | 'spam'
  reported_at      INTEGER NOT NULL,
  reporter_weight  REAL    NOT NULL DEFAULT 1.0,  -- 0.1 for unverified, 1.0 for trusted feed
  PRIMARY KEY (apex_domain, reported_at, violation_type)
);

CREATE INDEX IF NOT EXISTS idx_dv_domain ON domain_violations (apex_domain, reported_at DESC);

CREATE TABLE IF NOT EXISTS domain_reputation_cache (
  apex_domain   TEXT    PRIMARY KEY,
  risk_score    REAL    NOT NULL,
  risk_tier     TEXT    NOT NULL,   -- 'safe' | 'low' | 'medium' | 'high' | 'blocked'
  computed_at   INTEGER NOT NULL
);
```

---

## 4. Domain Risk Scorer

```typescript
// lib/domain-scorer.ts
export interface Env {
  DB: D1Database;
  DOMAIN_BLOCKLIST: KVNamespace;
}

export type RiskTier = 'safe' | 'low' | 'medium' | 'high' | 'blocked';

export interface DomainRisk {
  apexDomain: string;
  score: number;
  tier: RiskTier;
  reasons: string[];
}

const CACHE_TTL_MS = 30 * 60 * 1000;     // 30-minute reputation cache
const BLOCKLIST_SCORE = 100;
const VIOLATION_WINDOW_DAYS = 30;
const VIOLATION_WEIGHT_MAP: Record<string, number> = {
  phishing: 30,
  malware:  25,
  scam:     20,
  spam:     10,
};

export async function scoreDomain(apexDomain: string, env: Env): Promise<DomainRisk> {
  const reasons: string[] = [];
  let score = 0;

  // 1. KV hard blocklist (fastest path)
  const blocked = await env.DOMAIN_BLOCKLIST.get(apexDomain);
  if (blocked !== null) {
    return { apexDomain, score: BLOCKLIST_SCORE, tier: 'blocked', reasons: ['hard_blocklist'] };
  }

  // 2. D1 cache check
  const cached = await env.DB.prepare(`
    SELECT risk_score, risk_tier, computed_at FROM domain_reputation_cache
    WHERE apex_domain = ?1
  `).bind(apexDomain).first<{ risk_score: number; risk_tier: RiskTier; computed_at: number }>();

  if (cached && (Date.now() - cached.computed_at) < CACHE_TTL_MS) {
    return { apexDomain, score: cached.risk_score, tier: cached.risk_tier, reasons: ['cache_hit'] };
  }

  // 3. D1 violation history
  const cutoff = Date.now() - VIOLATION_WINDOW_DAYS * 24 * 60 * 60 * 1000;
  const { results: violations } = await env.DB.prepare(`
    SELECT violation_type, reporter_weight FROM domain_violations
    WHERE apex_domain = ?1 AND reported_at >= ?2
  `).bind(apexDomain, cutoff).all<{ violation_type: string; reporter_weight: number }>();

  for (const v of violations ?? []) {
    const weight = VIOLATION_WEIGHT_MAP[v.violation_type] ?? 5;
    score += weight * v.reporter_weight;
    reasons.push(v.violation_type);
  }

  // 4. Heuristic: newly registered domains (WHOIS not available in Workers;
  //    use registration-age API or Cloudflare Radar as a subrequest)
  const ageScore = await checkDomainAge(apexDomain);
  if (ageScore > 0) {
    score += ageScore;
    reasons.push('new_domain');
  }

  const tier = scoreTier(score);

  // 5. Write back to cache
  await env.DB.prepare(`
    INSERT INTO domain_reputation_cache (apex_domain, risk_score, risk_tier, computed_at)
    VALUES (?1, ?2, ?3, ?4)
    ON CONFLICT (apex_domain) DO UPDATE
      SET risk_score = excluded.risk_score, risk_tier = excluded.risk_tier, computed_at = excluded.computed_at
  `).bind(apexDomain, score, tier, Date.now()).run();

  return { apexDomain, score, tier, reasons: [...new Set(reasons)] };
}

function scoreTier(score: number): RiskTier {
  if (score >= 80) return 'high';
  if (score >= 40) return 'medium';
  if (score >= 15) return 'low';
  return 'safe';
}

async function checkDomainAge(_domain: string): Promise<number> {
  // Placeholder: call Cloudflare Radar domain age endpoint or WHOIS microservice
  // Returns 0 if domain is > 90 days old, 20 if < 30 days old, 10 if 30-90 days
  return 0;
}
```

---

## 5. Post-Creation Link Gate Worker

```typescript
// workers/post-link-gate.ts
import { extractLinks } from '../lib/url-extractor';
import { resolveRedirectChain } from '../lib/redirect-resolver';
import { scoreDomain, DomainRisk } from '../lib/domain-scorer';
import { extractApexDomain } from '../lib/url-extractor';

export interface Env {
  DB: D1Database;
  DOMAIN_BLOCKLIST: KVNamespace;
  LINK_REVIEW_QUEUE: Queue<LinkReviewEvent>;
}

export interface LinkReviewEvent {
  postId: string;
  links: Array<{ domain: string; score: number; tier: string }>;
  ts: number;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { postId, body } = await req.json<{ postId: string; body: string }>();
    const links = extractLinks(body);

    if (links.length === 0) {
      return new Response(JSON.stringify({ allowed: true, links: [] }), { status: 200 });
    }

    const scores: DomainRisk[] = [];
    let hardBlocked = false;

    for (const link of links) {
      // Resolve redirects first
      const chain = await resolveRedirectChain(link.raw);
      const finalDomain = extractApexDomain(new URL(chain.at(-1) ?? link.raw).hostname);

      const risk = await scoreDomain(finalDomain, env);
      scores.push(risk);

      if (risk.tier === 'blocked' || risk.tier === 'high') {
        hardBlocked = true;
      }
    }

    if (hardBlocked) {
      return new Response(JSON.stringify({ allowed: false, reason: 'unsafe_link' }), { status: 451 });
    }

    const hasMedium = scores.some((s) => s.tier === 'medium');
    if (hasMedium) {
      await env.LINK_REVIEW_QUEUE.send({
        postId,
        links: scores.map((s) => ({ domain: s.apexDomain, score: s.score, tier: s.tier })),
        ts: Date.now(),
      });
    }

    return new Response(JSON.stringify({
      allowed: true,
      flagged: hasMedium,
      links: scores.map((s) => ({ domain: s.apexDomain, tier: s.tier })),
    }), { status: 200 });
  },
};
```

---

## 6. Violation Ingestion from External Feeds

```typescript
// workers/domain-feed-ingestor-cron.ts
export interface Env {
  DB: D1Database;
  DOMAIN_BLOCKLIST: KVNamespace;
  PHISHTANK_API_KEY: string;
}

export default {
  async scheduled(_: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    // PhishTank JSON feed
    const res = await fetch(`https://data.phishtank.com/data/${env.PHISHTANK_API_KEY}/online-valid.json`);
    if (!res.ok) throw new Error(`PhishTank fetch failed: ${res.status}`);

    const entries: Array<{ url: string; verified: boolean }> = await res.json();
    const stmts: D1PreparedStatement[] = [];
    const now = Date.now();

    for (const entry of entries.slice(0, 2000)) { // cap ingest per run
      try {
        const domain = new URL(entry.url).hostname.split('.').slice(-2).join('.');
        stmts.push(
          env.DB.prepare(`
            INSERT OR IGNORE INTO domain_violations (apex_domain, violation_type, reported_at, reporter_weight)
            VALUES (?1, 'phishing', ?2, ?3)
          `).bind(domain, now, entry.verified ? 1.0 : 0.5)
        );
      } catch { /* skip malformed entries */ }

      if (stmts.length >= 100) {
        await env.DB.batch(stmts.splice(0, 100));
      }
    }

    if (stmts.length > 0) await env.DB.batch(stmts);
    console.log(`[domain-feed] ingested ${Math.min(entries.length, 2000)} PhishTank entries`);
  },
};
```

---

## Anti-patterns

- **Checking only the posted URL without resolving redirects**: A `bit.ly` link to a phishing
  page scores 0 on apex-domain lookup. Always resolve the full chain before scoring.
- **Hard-blocking on MEDIUM risk**: MEDIUM domains frequently include legitimate sites with
  occasional user abuse (Pastebin, Google Docs). Queue for review; do not auto-block.
- **No cache on D1 lookups**: Popular domains can appear in hundreds of posts per minute.
  Cache scores in D1 or KV for at least 30 minutes to avoid read pressure.
- **Treating all external feeds as equally authoritative**: PhishTank community submissions
  are less reliable than verified entries. Apply `reporter_weight` to reflect feed quality.

---

## Gotchas

- **`fetch` in Workers follows redirects by default**: Use `redirect: 'manual'` explicitly
  for redirect chain resolution; the default `redirect: 'follow'` hides the chain.
- **`AbortSignal.timeout` is available in Workers runtime**: No need to `Promise.race` with
  a manual timeout — `AbortSignal.timeout(ms)` is the idiomatic pattern.
- **D1 `INSERT OR IGNORE`**: The phishing feed ingestion uses `INSERT OR IGNORE` rather than
  `ON CONFLICT DO NOTHING` for compatibility with older D1 driver versions. Both work; check
  your wrangler CLI version.
- **KV blocklist capacity**: KV supports up to 1 GB per namespace. Storing one key per domain
  at ~50 bytes each allows ~20 million entries — sufficient for most static blocklists.

---

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import { extractLinks } from '../lib/url-extractor';

describe('extractLinks', () => {
  it('extracts single URL', () => {
    const links = extractLinks('Check this out: https://example.com/page');
    expect(links).toHaveLength(1);
    expect(links[0].apexDomain).toBe('example.com');
  });

  it('deduplicates same apex domain', () => {
    const links = extractLinks('https://sub.evil.com/a and https://other.evil.com/b');
    expect(links).toHaveLength(1); // same apex: evil.com
  });

  it('handles malformed URL gracefully', () => {
    expect(() => extractLinks('not_a_url and http://')).not.toThrow();
  });
});

import { scoreTier } from '../lib/domain-scorer';

describe('scoreTier', () => {
  it('maps scores to tiers correctly', () => {
    expect(scoreTier(0)).toBe('safe');
    expect(scoreTier(15)).toBe('low');
    expect(scoreTier(40)).toBe('medium');
    expect(scoreTier(80)).toBe('high');
  });
});
```

---

## Related

- `content-farm-spam-network-detection-d1.md`
- `spam-post-detection-cloudflare-workers-ai.md`
- `cryptocurrency-fraud-detection-workers.md`
- `platform-abuse-rate-velocity-d1-workers.md`
- `nft-scam-detection-d1-workers.md`

---

## Sources

- PhishTank Data Feed: https://www.phishtank.com/developer_info.php
- Cloudflare Radar Domain Intelligence: https://radar.cloudflare.com/
- APWG eCrime Blocklist: https://www.antiphishing.org/resources/apwg-tools/
- "Link Spam Detection at Scale" — Twitter Engineering Blog, 2021
- Cloudflare KV — Limits: https://developers.cloudflare.com/kv/platform/limits/
