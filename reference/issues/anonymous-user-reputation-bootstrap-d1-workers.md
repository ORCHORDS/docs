# Anonymous User Reputation Bootstrap — D1 + Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

New anonymous sessions on example project arrive with zero trust context. Without a reputation
history, the platform cannot distinguish a genuine first-time user from a ban evader spinning
up a fresh session, a bot registering a new identity, or a sybil operator seeding a network.
Granting full posting privileges immediately exposes the platform to spam floods; withholding
them degrades the new-user experience and drives organic users away. This article describes a
reputation bootstrap system that builds an initial trust score from observable session
behaviour, device signals, and early content quality — all without requiring account
registration or persistent identity.

---

## Context

Reputation bootstrap must solve a cold-start problem under adversarial conditions:
- Legitimate users arrive with no history but behave organically.
- Adversarial users arrive with no history but exhibit structured, automated patterns.
- The platform has no name, email, or phone to anchor identity.

The bootstrap pipeline uses three layers:
1. **Passive signals** — timing entropy, scroll patterns, interaction sequencing.
2. **Content quality signals** — Workers AI scores the first N posts for coherence and
   engagement bait.
3. **Social graph signals** — early interactions with established (non-flagged) sessions
   confer partial trust.

Trust accumulates in D1, stored against a short-lived session fingerprint, and graduates to
a longer-lived anonymous reputation token once a threshold is crossed.

---

## Schema

```sql
CREATE TABLE anon_reputation (
  session_fp   TEXT PRIMARY KEY,   -- 32-hex device+session fingerprint
  trust_score  REAL DEFAULT 0.0,   -- 0..1
  signals      TEXT,               -- JSON blob of contributing signals
  graduated    INTEGER DEFAULT 0,  -- 1 = issued long-lived rep token
  created_at   INTEGER NOT NULL,
  updated_at   INTEGER NOT NULL
);

CREATE TABLE rep_events (
  id           TEXT PRIMARY KEY,
  session_fp   TEXT NOT NULL,
  event_type   TEXT NOT NULL,  -- e.g. "first_post", "positive_reaction", "bot_pattern"
  delta        REAL NOT NULL,  -- trust delta (positive or negative)
  created_at   INTEGER NOT NULL
);

CREATE INDEX idx_rep_events_fp ON rep_events (session_fp, created_at);
```

---

## 1. Passive Timing Entropy

Humans exhibit jitter in their action timing; bots tend to fire at regular intervals.
Measure Shannon entropy of inter-action intervals for the first 20 actions.

```typescript
function timingEntropy(timestamps: number[]): number {
  if (timestamps.length < 3) return 0.5; // insufficient data — neutral

  const intervals = timestamps
    .slice(1)
    .map((t, i) => t - timestamps[i])
    .filter((d) => d > 0);

  // Bucket intervals into 100ms bins
  const buckets = new Map<number, number>();
  for (const iv of intervals) {
    const bin = Math.floor(iv / 100);
    buckets.set(bin, (buckets.get(bin) ?? 0) + 1);
  }

  const total = intervals.length;
  let entropy = 0;
  for (const count of buckets.values()) {
    const p = count / total;
    entropy -= p * Math.log2(p);
  }

  // Normalise: max entropy for 20 actions ≈ log2(20) ≈ 4.32
  return Math.min(1, entropy / 4.32);
}
```

---

## 2. First-Post Content Quality via Workers AI

Score the first post for naturalness. Low-quality, repetitive, or templated first posts are
strong bot signals.

```typescript
async function scoreFirstPost(
  ai: Ai,
  text: string
): Promise<number> {
  // Use sentiment as a proxy for coherent natural language
  const result = await ai.run("@cf/huggingface/distilbert-sst-2-int8", {
    text,
  });

  // A coherent post (even negative sentiment) scores > 0.5 for its top label
  const topScore = result[0]?.score ?? 0;
  // Very short, URL-only, or all-caps posts are penalised separately
  const lengthPenalty = text.length < 20 || text === text.toUpperCase() ? 0.3 : 0;
  return Math.max(0, topScore - lengthPenalty);
}
```

---

## 3. Social Graph Trust Transfer

When a new session interacts positively (reaction, comment) with a post from a high-trust
session, partial trust transfers.

```typescript
async function applyTrustTransfer(
  db: D1Database,
  newFp: string,
  authorFp: string,
  interactionType: "reaction" | "comment"
): Promise<void> {
  const author = await db
    .prepare(`SELECT trust_score FROM anon_reputation WHERE session_fp = ?`)
    .bind(authorFp)
    .first<{ trust_score: number }>();

  if (!author) return;

  // Transfer 10% of the author's score, capped at 0.1
  const delta = Math.min(0.1, author.trust_score * 0.1) * (interactionType === "comment" ? 1.5 : 1);

  await applyRepDelta(db, newFp, delta, `trust_transfer_${interactionType}`);
}
```

---

## 4. Core Trust Delta Application

```typescript
async function applyRepDelta(
  db: D1Database,
  sessionFp: string,
  delta: number,
  eventType: string
): Promise<void> {
  const now = Date.now();
  await db.batch([
    db.prepare(
      `INSERT INTO anon_reputation (session_fp, trust_score, signals, created_at, updated_at)
       VALUES (?, MAX(0, MIN(1, ?)), '{}', ?, ?)
       ON CONFLICT(session_fp) DO UPDATE SET
         trust_score = MAX(0, MIN(1, trust_score + ?)),
         updated_at = ?`
    ).bind(sessionFp, delta, now, now, delta, now),
    db.prepare(
      `INSERT INTO rep_events (id, session_fp, event_type, delta, created_at)
       VALUES (?, ?, ?, ?, ?)`
    ).bind(crypto.randomUUID(), sessionFp, eventType, delta, now),
  ]);
}
```

---

## 5. Graduation to Long-Lived Reputation Token

Once a session crosses a trust threshold, issue a signed reputation token stored in a KV
namespace so it survives session rotation.

```typescript
async function maybeGraduate(
  db: D1Database,
  kv: KVNamespace,
  sessionFp: string,
  threshold = 0.55
): Promise<string | null> {
  const rep = await db
    .prepare(`SELECT trust_score, graduated FROM anon_reputation WHERE session_fp = ?`)
    .bind(sessionFp)
    .first<{ trust_score: number; graduated: number }>();

  if (!rep || rep.graduated || rep.trust_score < threshold) return null;

  const repToken = crypto.randomUUID();
  const payload = JSON.stringify({ fp: sessionFp, score: rep.trust_score, issuedAt: Date.now() });

  // Store token for 90 days
  await kv.put(`rep:${repToken}`, payload, { expirationTtl: 90 * 86400 });
  await db
    .prepare(`UPDATE anon_reputation SET graduated = 1, updated_at = ? WHERE session_fp = ?`)
    .bind(Date.now(), sessionFp)
    .run();

  return repToken;
}
```

---

## 6. Bootstrap Decision Gate

Check trust score before allowing elevated actions (posting images, creating polls, DMs).

```typescript
async function allowElevatedAction(
  db: D1Database,
  kv: KVNamespace,
  sessionFp: string,
  repToken?: string
): Promise<{ allow: boolean; score: number }> {
  // Long-lived rep token takes priority
  if (repToken) {
    const stored = await kv.get(`rep:${repToken}`);
    if (stored) {
      const payload = JSON.parse(stored) as { score: number };
      return { allow: payload.score >= 0.45, score: payload.score };
    }
  }

  const rep = await db
    .prepare(`SELECT trust_score FROM anon_reputation WHERE session_fp = ?`)
    .bind(sessionFp)
    .first<{ trust_score: number }>();

  const score = rep?.trust_score ?? 0;
  return { allow: score >= 0.4, score };
}
```

---

## Anti-patterns

- **Hard-blocking all new sessions until trust threshold** — use graduated feature gating
  (text posts allowed immediately, images after 0.3, polls after 0.5).
- **Storing the full device fingerprint as a primary key** — hash it with a rotating pepper
  so raw fingerprints cannot be reversed to device identifiers.
- **Trusting timing entropy alone** — sophisticated bots now introduce artificial jitter;
  combine multiple independent signals.
- **Never expiring trust scores** — a 0-score session that is months old is different from
  a brand-new one; add time-to-live logic for inactive sessions.

---

## Gotchas

- D1 `ON CONFLICT DO UPDATE` requires that the target column be either a PRIMARY KEY or have
  a UNIQUE constraint — verify the schema before using upsert.
- `@cf/huggingface/distilbert-sst-2-int8` is a sentiment model, not a bot-detection model;
  it is a proxy for linguistic coherence, not a definitive signal.
- KV `expirationTtl` is in seconds. `90 * 86400` = 7,776,000 — double-check if adjusting TTL.
- Reputation tokens issued before a ban event must be revoked proactively; KV delete is O(1)
  but requires the token to be tracked in D1 for revocation sweeps.

---

## Verification

```bash
# Simulate a new session accumulating trust
curl -X POST https://example project.example.com/api/rep/event \
  -H "Content-Type: application/json" \
  -d '{"fp":"aabbccdd...","event":"first_post","text":"Hello world, excited to be here!"}'

# Check trust score
wrangler d1 execute example project_DB --command \
  "SELECT session_fp, trust_score, graduated FROM anon_reputation WHERE session_fp='aabbccdd...'"

# Simulate graduation
wrangler d1 execute example project_DB --command \
  "UPDATE anon_reputation SET trust_score=0.6 WHERE session_fp='aabbccdd...'"
# Then call maybeGraduate and verify KV entry is written
```

---

## Related

- `ban-evasion-device-fingerprint-detection-d1.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `anonymous-gift-economy-fraud-prevention-d1-workers.md`
- `repeat-offender-detection-anonymous-sessions.md`

---

## Sources

- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare KV — https://developers.cloudflare.com/kv/
- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- "Cold-Start Trust on Anonymous Platforms" — USENIX Security 2024
- example project internal reputation design spec v1.7
