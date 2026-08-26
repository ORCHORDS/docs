# Anonymous User Impersonation Detection — Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

On example project, a malicious session adopts a display handle, avatar hash, or writing style closely mimicking a well-known anonymous persona, then uses that borrowed identity to spread misinformation, solicit trust from followers, or conduct scams. Because example project allows pseudonyms without verification, impersonation is a primary vector for reputation hijacking even without persistent accounts.

## Context

example project anonymous personas are represented by a self-chosen handle and an optional avatar (stored as a perceptual hash in D1). Workers inspect every new session's handle and avatar against a protected-persona registry at session creation time and again on each post. Workers AI embedding similarity detects writing-style mimicry for high-value personas that have been flagged as impersonation targets. KV caches the protected-persona list with a 5-minute TTL to avoid D1 reads on every request.

## Detection — Handle and Avatar Similarity Scan

```typescript
// workers/impersonation-detector.ts
import { Ai } from "@cloudflare/ai";

interface Env {
  AI: Ai;
  DB: D1Database;
  PERSONA_KV: KVNamespace;     // cache of protected handles + avatar hashes
  ALERT_QUEUE: Queue;
}

interface SessionProfile {
  sessionId: string;
  handle: string;
  avatarPHash?: string;         // 64-bit perceptual hash hex string
  bio?: string;
}

interface ProtectedPersona {
  personaId: string;
  canonicalHandle: string;
  avatarPHash?: string;
  bioEmbedding?: number[];      // pre-computed; stored in D1 as JSON
  isVerified: boolean;
}

// Hamming distance between two 64-char hex strings (256-bit pHash)
function hammingDistance(a: string, b: string): number {
  let dist = 0;
  for (let i = 0; i < Math.min(a.length, b.length); i += 2) {
    const ba = parseInt(a.slice(i, i + 2), 16);
    const bb = parseInt(b.slice(i, i + 2), 16);
    let xor = ba ^ bb;
    while (xor) { dist += xor & 1; xor >>= 1; }
  }
  return dist;
}

// Edit distance for handle comparison (handles ≤ 32 chars)
function editDistance(a: string, b: string): number {
  const m = a.length, n = b.length;
  const dp = Array.from({ length: m + 1 }, (_, i) =>
    Array.from({ length: n + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i]![j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1]![j - 1]!
          : 1 + Math.min(dp[i - 1]![j]!, dp[i]![j - 1]!, dp[i - 1]![j - 1]!);
    }
  }
  return dp[m]![n]!;
}

async function loadProtectedPersonas(env: Env): Promise<ProtectedPersona[]> {
  const cached = await env.PERSONA_KV.get("protected_personas", "json") as ProtectedPersona[] | null;
  if (cached) return cached;

  const { results } = await env.DB.prepare(
    `SELECT persona_id, canonical_handle, avatar_phash, bio_embedding, is_verified
     FROM protected_personas WHERE active = 1`
  ).all<{
    persona_id: string;
    canonical_handle: string;
    avatar_phash: string | null;
    bio_embedding: string | null;
    is_verified: number;
  }>();

  const personas: ProtectedPersona[] = results.map((r) => ({
    personaId: r.persona_id,
    canonicalHandle: r.canonical_handle,
    avatarPHash: r.avatar_phash ?? undefined,
    bioEmbedding: r.bio_embedding ? JSON.parse(r.bio_embedding) : undefined,
    isVerified: r.is_verified === 1,
  }));

  await env.PERSONA_KV.put("protected_personas", JSON.stringify(personas), {
    expirationTtl: 300,
  });
  return personas;
}

function cosineSim(a: number[], b: number[]): number {
  const dot = a.reduce((s, v, i) => s + v * (b[i] ?? 0), 0);
  const na = Math.sqrt(a.reduce((s, v) => s + v * v, 0));
  const nb = Math.sqrt(b.reduce((s, v) => s + v * v, 0));
  return na && nb ? dot / (na * nb) : 0;
}

export async function scoreImpersonation(
  profile: SessionProfile,
  env: Env
): Promise<{ score: number; matchedPersonaId?: string; signals: string[] }> {
  const personas = await loadProtectedPersonas(env);
  const signals: string[] = [];
  let topScore = 0;
  let topPersona: string | undefined;

  // Normalise handle: lower-case, strip non-alphanumeric (homograph attack)
  const normHandle = profile.handle.toLowerCase().replace(/[^a-z0-9]/g, "");

  for (const persona of personas) {
    let pairScore = 0;
    const normCanon = persona.canonicalHandle.toLowerCase().replace(/[^a-z0-9]/g, "");

    // 1. Exact handle match after normalisation
    if (normHandle === normCanon) {
      pairScore += 0.9;
      signals.push(`exact_handle_match:${persona.personaId}`);
    } else {
      // 2. Edit distance ≤ 2 on short handles (typosquatting)
      const ed = editDistance(normHandle, normCanon);
      const maxLen = Math.max(normHandle.length, normCanon.length);
      if (ed <= 2 && maxLen >= 4) {
        pairScore += 0.4 * (1 - ed / maxLen);
        signals.push(`handle_edit_distance:${ed}:${persona.personaId}`);
      }
    }

    // 3. Avatar perceptual hash — Hamming distance ≤ 10 out of 256 bits
    if (profile.avatarPHash && persona.avatarPHash) {
      const hd = hammingDistance(profile.avatarPHash, persona.avatarPHash);
      if (hd <= 10) {
        pairScore += 0.5 * (1 - hd / 256);
        signals.push(`avatar_phash_match:hd=${hd}:${persona.personaId}`);
      }
    }

    // 4. Bio embedding similarity (only if persona has a stored embedding)
    if (profile.bio && persona.bioEmbedding && pairScore > 0) {
      const ai = new Ai(env.AI);
      const result = await ai.run("@cf/baai/bge-small-en-v1.5", { text: [profile.bio] });
      const bioVec = (result as { data: number[][] }).data[0]!;
      const sim = cosineSim(bioVec, persona.bioEmbedding);
      if (sim >= 0.88) {
        pairScore += 0.2 * sim;
        signals.push(`bio_embedding_sim:${sim.toFixed(3)}:${persona.personaId}`);
      }
    }

    if (pairScore > topScore) {
      topScore = pairScore;
      topPersona = persona.personaId;
    }
  }

  return { score: Math.min(topScore, 1), matchedPersonaId: topPersona, signals };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const profile = await request.json<SessionProfile>();
    const { score, matchedPersonaId, signals } = await scoreImpersonation(profile, env);

    // Persist detection result
    await env.DB.prepare(
      `INSERT OR IGNORE INTO impersonation_checks
         (session_id, handle, risk_score, matched_persona_id, signals, checked_at)
       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
    )
      .bind(profile.sessionId, profile.handle, score, matchedPersonaId ?? null, JSON.stringify(signals))
      .run();

    if (score >= 0.7) {
      await env.ALERT_QUEUE.send({
        type: "IMPERSONATION_HIGH",
        sessionId: profile.sessionId,
        handle: profile.handle,
        matchedPersonaId,
        score,
        signals,
        ts: Date.now(),
      });
      return new Response(
        JSON.stringify({ action: "block", reason: "impersonation", score }),
        { status: 200 }
      );
    }

    if (score >= 0.4) {
      await env.ALERT_QUEUE.send({
        type: "IMPERSONATION_REVIEW",
        sessionId: profile.sessionId,
        handle: profile.handle,
        matchedPersonaId,
        score,
        signals,
        ts: Date.now(),
      });
    }

    return new Response(JSON.stringify({ action: "allow", score }), { status: 200 });
  },
};
```

## Response and Enforcement — Session Block and Handle Reservation

```typescript
// workers/impersonation-responder.ts
interface ImpersonationAlert {
  type: "IMPERSONATION_HIGH" | "IMPERSONATION_REVIEW";
  sessionId: string;
  handle: string;
  matchedPersonaId?: string;
  score: number;
  signals: string[];
  ts: number;
}

export default {
  async queue(batch: MessageBatch<ImpersonationAlert>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const evt = msg.body;

      if (evt.type === "IMPERSONATION_HIGH") {
        // 1. Block handle for this session
        await env.DB.prepare(
          `UPDATE anonymous_sessions
             SET status = 'handle_blocked', handle = NULL,
                 block_reason = 'impersonation', blocked_at = CURRENT_TIMESTAMP
           WHERE session_id = ?`
        ).bind(evt.sessionId).run();

        // 2. Add handle to temporary blocklist (30-day)
        await env.DB.prepare(
          `INSERT OR IGNORE INTO blocked_handles
             (handle_normalised, blocked_at, expires_at, reason, matched_persona_id)
           VALUES (?, CURRENT_TIMESTAMP,
                   datetime('now', '+30 days'), 'impersonation', ?)`
        )
          .bind(
            evt.handle.toLowerCase().replace(/[^a-z0-9]/g, ""),
            evt.matchedPersonaId ?? null
          )
          .run();

        // 3. Invalidate protected-persona KV cache so blocklist is fresh
        await env.PERSONA_KV.delete("protected_personas");
      }

      msg.ack();
    }
  },
};
```

## Audit and Compliance — Schema

```sql
-- D1 migration
CREATE TABLE IF NOT EXISTS protected_personas (
  persona_id        TEXT PRIMARY KEY,
  canonical_handle  TEXT NOT NULL UNIQUE,
  avatar_phash      TEXT,
  bio_embedding     TEXT,   -- JSON array of floats
  is_verified       INTEGER DEFAULT 0,
  active            INTEGER DEFAULT 1,
  created_at        TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS impersonation_checks (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id        TEXT NOT NULL,
  handle            TEXT NOT NULL,
  risk_score        REAL NOT NULL,
  matched_persona_id TEXT,
  signals           TEXT,  -- JSON array
  checked_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blocked_handles (
  handle_normalised TEXT PRIMARY KEY,
  blocked_at        TEXT NOT NULL,
  expires_at        TEXT NOT NULL,
  reason            TEXT NOT NULL,
  matched_persona_id TEXT
);

-- Daily impersonation trend
SELECT
  date(checked_at) AS day,
  COUNT(*)          AS checks,
  SUM(risk_score >= 0.7) AS high_risk,
  SUM(risk_score >= 0.4 AND risk_score < 0.7) AS review
FROM impersonation_checks
GROUP BY day
ORDER BY day DESC
LIMIT 30;
```

## Anti-patterns

- **Storing raw avatar image bytes in D1** — only perceptual hashes belong in D1; images go to R2 with access controls.
- **Blocking on handle similarity alone without a size guard** — single-character handles ("a", "x") would match everything; require `maxLen >= 4` before applying edit-distance.
- **Caching the protected-persona list indefinitely** — a 5-minute TTL ensures newly registered personas (and newly blocked handles) propagate quickly.
- **Blocking the session globally** on impersonation detection — only strip the handle; the session may not be malicious, merely chosen a conflicting name.
- **Embedding every bio on every check** — the embedding call fires only when a prior signal (`pairScore > 0`) already suggests a candidate match, avoiding unnecessary AI inference.

## Gotchas

- Homograph attacks use Unicode lookalike characters (е vs e, ⓗ vs h); normalise to ASCII with `replace(/[^a-z0-9]/g, "")` **before** comparison, not after.
- Perceptual hash Hamming distance depends on bit-width of the hash — verify whether the stored hashes are 64-bit (16 hex chars) or 256-bit (64 hex chars) and adjust the distance threshold accordingly.
- `bio_embedding` stored as a JSON TEXT column must be parsed each time; for large persona registries (>1 000), consider a vector index or precomputed similarity batch job.
- Workers AI `bge-small-en-v1.5` returns 384-dimensional vectors; confirm dimension parity if you switch models.
- `blocked_handles` rows with past `expires_at` are not auto-deleted by D1 — schedule a cleanup Worker to purge expired rows daily.

## Verification

```bash
# Register a protected persona
wrangler d1 execute example project-db --command \
  "INSERT INTO protected_personas (persona_id, canonical_handle, is_verified, created_at)
   VALUES ('p1', 'trustednews', 1, CURRENT_TIMESTAMP);"

# Attempt impersonation via typosquatting (edit distance 1)
curl -X POST https://example.com/internal/impersonation-check \
  -H "Content-Type: application/json" \
  -d '{"sessionId":"evil1","handle":"tr0stednews","avatarPHash":null}'
# Expect: action=block or review, score > 0

# Confirm block row
wrangler d1 execute example project-db --command \
  "SELECT handle_normalised, reason FROM blocked_handles;"

# Confirm session handle cleared
wrangler d1 execute example project-db --command \
  "SELECT status, handle, block_reason FROM anonymous_sessions WHERE session_id='evil1';"

# Legitimate distinct handle should pass
curl -X POST https://example.com/internal/impersonation-check \
  -H "Content-Type: application/json" \
  -d '{"sessionId":"legit1","handle":"completelydifferent"}'
# Expect: action=allow, score ~0
```

## Related

- `ban-evasion-device-fingerprint-detection-d1.md`
- `sock-puppet-network-detection.md`
- `brand-impersonation-detection-takedown.md`
- `synthetic-identity-fraud-detection-workers-ai.md`

## Sources

- https://transparency.meta.com/policies/community-standards/misrepresentation/
- https://help.twitter.com/en/rules-and-policies/twitter-impersonation-policy
- https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/
