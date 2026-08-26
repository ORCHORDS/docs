# Anonymous Confession Trust Scoring with D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A confession or anonymous-sharing feature allows users to post sensitive personal disclosures without identity. Without a trust signal attached to each submission, moderation queues fill with fabricated shock content, coordinated story-planting, and AI-generated confessional spam. Reviewers cannot distinguish a genuine vulnerable user from a bad-faith actor.

## Context

example project confession boards run as anonymous channels: no persistent user identity is stored client-side beyond a rotating ephemeral token. Trust scoring must therefore derive entirely from behavioural signals captured at submission time — device posture, network reputation, writing style, submission cadence, and cross-post similarity — persisted in D1, and consumed by both the real-time moderation Worker and the human review queue.

Trust is a 0–100 integer. Scores ≥ 70 are auto-approved into a soft-visible state (visible to the submitter and to 5 % of random peers for reaction sampling). Scores 40–69 enter the human queue. Scores < 40 are shadow-dropped with a plausible no-op response returned to the client.

---

## Schema

```sql
-- D1 migration: 0012_confession_trust.sql
CREATE TABLE IF NOT EXISTS confession_submissions (
  id            TEXT PRIMARY KEY,          -- ULID
  ephemeral_token TEXT NOT NULL,           -- rotated per-device, 30 day TTL
  submitted_at  INTEGER NOT NULL,          -- Unix ms
  trust_score   INTEGER NOT NULL DEFAULT 0,
  score_detail  TEXT NOT NULL DEFAULT '{}',-- JSON breakdown per signal
  visibility    TEXT NOT NULL DEFAULT 'pending', -- pending | soft | queue | shadow
  content_hash  TEXT NOT NULL,             -- SHA-256 of normalised body
  word_count    INTEGER NOT NULL,
  review_by     TEXT,                      -- reviewer user ID when assigned
  reviewed_at   INTEGER
);

CREATE INDEX idx_conf_token   ON confession_submissions(ephemeral_token);
CREATE INDEX idx_conf_vis     ON confession_submissions(visibility, submitted_at DESC);
CREATE INDEX idx_conf_hash    ON confession_submissions(content_hash);
```

---

## Signal Collection at Submission

```typescript
// workers/confession-ingest.ts
import { Env } from '../types';

interface SubmissionPayload {
  body: string;
  ephemeralToken: string;
  clientHints: {
    cfThreatScore?: number;  // from CF-Threat-Score header
    asn?: number;
    country?: string;
    tor?: boolean;
    vpn?: boolean;
  };
}

export async function collectSignals(
  payload: SubmissionPayload,
  req: Request,
  env: Env
): Promise<Record<string, number>> {
  const signals: Record<string, number> = {};

  // 1. Cloudflare network reputation (0-100, higher = riskier)
  const cfThreat = payload.clientHints.cfThreatScore ?? 0;
  signals.network = Math.max(0, 50 - cfThreat);  // invert: low threat = high trust

  // 2. Tor / VPN penalty
  signals.anonymityLayer = payload.clientHints.tor || payload.clientHints.vpn ? -20 : 0;

  // 3. Submission cadence: how many confessions from this token in last 24 h
  const { results } = await env.DB.prepare(
    `SELECT COUNT(*) as cnt
       FROM confession_submissions
      WHERE ephemeral_token = ?
        AND submitted_at > ?`
  ).bind(payload.ephemeralToken, Date.now() - 86_400_000).all<{ cnt: number }>();
  const priorCount = results[0]?.cnt ?? 0;
  signals.cadence = priorCount === 0 ? 20 : priorCount === 1 ? 10 : priorCount < 5 ? 0 : -30;

  // 4. Near-duplicate detection via content_hash
  const normBody = payload.body.toLowerCase().replace(/\s+/g, ' ').trim();
  const hash = await sha256(normBody);
  const dupRow = await env.DB.prepare(
    `SELECT COUNT(*) as cnt FROM confession_submissions WHERE content_hash = ?`
  ).bind(hash).first<{ cnt: number }>();
  signals.duplicate = (dupRow?.cnt ?? 0) > 0 ? -50 : 10;

  // 5. Prose authenticity heuristic: word count in expected range
  const words = payload.body.trim().split(/\s+/).length;
  signals.length = words >= 30 && words <= 800 ? 15 : words < 10 ? -20 : 0;

  return signals;
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Scoring Aggregation and Persistence

```typescript
// workers/confession-ingest.ts (continued)
import { ulid } from 'ulidx';

export async function scoreAndPersist(
  payload: SubmissionPayload,
  signals: Record<string, number>,
  env: Env
): Promise<{ id: string; score: number; visibility: string }> {
  const base = 35; // neutral baseline
  const delta = Object.values(signals).reduce((a, b) => a + b, 0);
  const score = Math.min(100, Math.max(0, base + delta));

  const visibility =
    score >= 70 ? 'soft' :
    score >= 40 ? 'queue' :
                  'shadow';

  const id = ulid();
  const normBody = payload.body.toLowerCase().replace(/\s+/g, ' ').trim();
  const hash = await sha256(normBody);

  await env.DB.prepare(
    `INSERT INTO confession_submissions
       (id, ephemeral_token, submitted_at, trust_score, score_detail,
        visibility, content_hash, word_count)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    id,
    payload.ephemeralToken,
    Date.now(),
    score,
    JSON.stringify(signals),
    visibility,
    hash,
    payload.body.trim().split(/\s+/).length
  ).run();

  return { id, score, visibility };
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Review Queue Worker

```typescript
// workers/confession-review.ts
export async function fetchQueue(
  env: Env,
  reviewerId: string,
  limit = 20
): Promise<Array<{ id: string; body: string; score: number; detail: Record<string, number> }>> {
  // Assign unassigned queue items atomically with a short lock window
  const lockExpiry = Date.now() + 5 * 60_000; // 5 minute lock

  const rows = await env.DB.prepare(
    `SELECT id FROM confession_submissions
      WHERE visibility = 'queue'
        AND (review_by IS NULL OR reviewed_at < ?)
      ORDER BY submitted_at ASC
      LIMIT ?`
  ).bind(Date.now() - 5 * 60_000, limit).all<{ id: string }>();

  if (rows.results.length === 0) return [];

  const ids = rows.results.map(r => r.id);
  // Claim rows
  const placeholders = ids.map(() => '?').join(',');
  await env.DB.prepare(
    `UPDATE confession_submissions
        SET review_by = ?, reviewed_at = ?
      WHERE id IN (${placeholders})
        AND visibility = 'queue'`
  ).bind(reviewerId, Date.now(), ...ids).run();

  const claimed = await env.DB.prepare(
    `SELECT id, trust_score, score_detail FROM confession_submissions WHERE id IN (${placeholders})`
  ).bind(...ids).all<{ id: string; trust_score: number; score_detail: string }>();

  return claimed.results.map(r => ({
    id: r.id,
    body: '[fetched separately from R2]',
    score: r.trust_score,
    detail: JSON.parse(r.score_detail),
  }));
}

export async function adjudicate(
  id: string,
  decision: 'approve' | 'reject',
  env: Env
): Promise<void> {
  const visibility = decision === 'approve' ? 'soft' : 'shadow';
  await env.DB.prepare(
    `UPDATE confession_submissions SET visibility = ?, reviewed_at = ? WHERE id = ?`
  ).bind(visibility, Date.now(), id).run();
}
```

---

## Score Re-evaluation on Appeal

If a shadow-dropped confession receives an appeal signal (user taps a discreet "not received?" affordance three times), a lightweight re-evaluation runs without exposing the trust system to the user.

```typescript
export async function maybeReevaluate(id: string, env: Env): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT trust_score, visibility FROM confession_submissions WHERE id = ?`
  ).bind(id).first<{ trust_score: number; visibility: string }>();

  if (!row || row.visibility !== 'shadow') return;

  // Mild score boost for persisting users (capped so cannot self-promote past threshold)
  const boosted = Math.min(row.trust_score + 8, 55);
  const newVisibility = boosted >= 40 ? 'queue' : 'shadow';

  await env.DB.prepare(
    `UPDATE confession_submissions SET trust_score = ?, visibility = ? WHERE id = ?`
  ).bind(boosted, newVisibility, id).run();
}
```

---

## Anti-patterns

- **Exposing the score to the submitter.** Any leaked trust signal teaches adversaries to reverse-engineer thresholds. Return only a generic success or neutral-delay response regardless of outcome.
- **Using account age as a primary signal.** Confession features are inherently account-light; age signals are meaningless or easy to farm.
- **Storing raw confession text in D1.** D1 rows are scanned in compliance tooling. Store confession body in R2 (encrypted at rest, access-logged) and keep only the hash in D1.
- **Hard-coding thresholds in Worker code.** Thresholds should be KV-resident so they can be adjusted without a deploy when adversary behaviour shifts.

---

## Gotchas

- `CF-Threat-Score` is only populated on zones with Bot Management or WAF rules enabled; fall back to `0` gracefully.
- D1 `COUNT(*)` in a transaction with a subsequent `INSERT` is not atomic by default — use a WAL-mode journal and accept the occasional phantom read rather than locking rows for a confession flow.
- Ephemeral tokens rotate on a 30-day schedule. A user who submits on day 29 and re-submits on day 31 under a new token will appear as a first-time submitter; cadence signal resets cleanly, which is the desired privacy property.
- SHA-256 collisions on very short confessions (< 10 words) are a real duplicate-detection concern because normalisation strips punctuation. Apply duplicate check only when `word_count > 20`.

---

## Verification

```bash
# Confirm score range is bounded
wrangler d1 execute example project-prod --command \
  "SELECT MIN(trust_score), MAX(trust_score) FROM confession_submissions"

# Verify shadow-drop rate is not runaway (should be < 30 % in steady state)
wrangler d1 execute example project-prod --command \
  "SELECT visibility, COUNT(*) FROM confession_submissions GROUP BY visibility"

# Check duplicate-hash detection is firing
wrangler d1 execute example project-prod --command \
  "SELECT content_hash, COUNT(*) as c FROM confession_submissions GROUP BY content_hash HAVING c > 1 LIMIT 10"
```

---

## Related

- `anonymous-user-reputation-bootstrap-d1-workers.md`
- `repeat-offender-detection-anonymous-sessions.md`
- `shadow-banning-reach-limiting-d1-workers.md`
- `sybil-attack-detection-workers-ai-behavioral.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- CF-Threat-Score header reference — https://developers.cloudflare.com/fundamentals/reference/http-request-headers/
- ULID spec — https://github.com/ulid/spec
- example project internal trust-signal taxonomy v3 (internal wiki, 2026-Q2)
