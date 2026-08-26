# Crisis Hoax and False Emergency Detection with Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

False emergency posts — fabricated active-shooter alerts, fake natural disaster warnings, hoax evacuation orders, fabricated mass-casualty reports — cause real-world harm: misdirected first responders, public panic, donation fraud, and suppression of accurate emergency information. These posts spread faster than any other category of misinformation because users share them reflexively before verifying. Standard spam and toxicity classifiers are not calibrated for this pattern because the text is neither offensive nor spammy — it is written to sound credible and urgent.

## Context

example project runs a dedicated crisis-hoax detection pipeline separate from its general misinformation stack. The pipeline operates in three tiers:

1. **Lexical gate** — synchronous in the Post Worker; catches obvious patterns (format mimicry, urgency templates) with < 5 ms overhead.
2. **AI classifier** — asynchronous via Workers AI; deeper semantic analysis for ambiguous posts.
3. **Graph amplification detector** — Cron Trigger every 5 minutes; spots hoax posts that are spreading abnormally fast relative to the account's historical reach.

Confirmed hoax posts are labelled with a platform warning card. High-confidence cases are additionally reach-limited for 24 hours while human review completes. Posts that impersonate official emergency accounts (FEMA, local emergency management, police) are removed immediately.

---

## Lexical Gate — Synchronous First Pass

```typescript
// workers/post-create/crisis-gate.ts

interface CrisisLexicalResult {
  flagged: boolean;
  matchedPatterns: string[];
  urgencyScore: number;  // 0–1
}

const OFFICIAL_IMPERSONATION_TERMS = [
  'fema', 'emergency management', 'police department', 'fire department',
  'national guard', '911 dispatch', 'ems', 'sheriff',
];

const EMERGENCY_TEMPLATES = [
  /active[\s-]?shooter/i,
  /mass[\s-]?casualty/i,
  /evacuate\s+immediately/i,
  /bomb\s+threat/i,
  /tsunami\s+warning/i,
  /shelter[\s-]?in[\s-]?place/i,
  /\bdo\s+not\s+go\s+to\b.{0,40}\bschool\b/i,
  /\bstay\s+away\s+from\b.{0,40}\bcampus\b/i,
];

const URGENCY_AMPLIFIERS = [
  'this is real', 'not a drill', 'confirmed', 'breaking', 'urgent',
  'share this now', 'spread the word', 'happening right now',
];

export function lexicalGate(body: string): CrisisLexicalResult {
  const lower = body.toLowerCase();
  const matchedPatterns: string[] = [];
  let urgencyScore = 0;

  // Emergency template match
  for (const pattern of EMERGENCY_TEMPLATES) {
    if (pattern.test(body)) {
      matchedPatterns.push(pattern.source);
      urgencyScore += 0.3;
    }
  }

  // Official account impersonation language
  for (const term of OFFICIAL_IMPERSONATION_TERMS) {
    if (lower.includes(term)) {
      matchedPatterns.push(`impersonation:${term}`);
      urgencyScore += 0.2;
    }
  }

  // Urgency amplifiers
  for (const amp of URGENCY_AMPLIFIERS) {
    if (lower.includes(amp)) {
      urgencyScore += 0.1;
    }
  }

  return {
    flagged: urgencyScore >= 0.4,
    matchedPatterns,
    urgencyScore: Math.min(urgencyScore, 1),
  };
}
```

---

## Workers AI Semantic Classifier

```typescript
// workers/post-create/crisis-ai-classify.ts
import { Env } from '../../types';

export interface CrisisAIResult {
  isHoax: boolean;
  hoaxConfidence: number;
  impersonatesOfficial: boolean;
  category: 'shooting' | 'disaster' | 'bomb' | 'public_health' | 'other' | 'none';
}

const SYSTEM_PROMPT = `You are a content safety classifier for a social platform.
Your task: determine if the following post is a fabricated crisis or emergency hoax.
A hoax post claims a real emergency is occurring but is false, unverified, or designed to cause panic.
Legitimate posts discussing emergencies, news reporting, or policy debate are NOT hoaxes.

Respond with a JSON object only:
{
  "is_hoax": boolean,
  "hoax_confidence": number between 0 and 1,
  "impersonates_official": boolean,
  "category": "shooting" | "disaster" | "bomb" | "public_health" | "other" | "none"
}`;

export async function classifyWithAI(
  postBody: string,
  env: Env
): Promise<CrisisAIResult> {
  const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      { role: 'system', content: SYSTEM_PROMPT },
      { role: 'user', content: postBody.slice(0, 2000) },  // cap input length
    ],
    max_tokens: 150,
    temperature: 0,
  }) as { response: string };

  let parsed: CrisisAIResult;
  try {
    // Extract JSON from model output — llama-3.1 sometimes wraps in markdown
    const jsonMatch = response.response.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('No JSON in response');
    const raw = JSON.parse(jsonMatch[0]);
    parsed = {
      isHoax: Boolean(raw.is_hoax),
      hoaxConfidence: Number(raw.hoax_confidence ?? 0),
      impersonatesOfficial: Boolean(raw.impersonates_official),
      category: raw.category ?? 'none',
    };
  } catch {
    // Model output unparseable — treat as low-confidence inconclusive
    parsed = { isHoax: false, hoaxConfidence: 0, impersonatesOfficial: false, category: 'none' };
  }

  return parsed;
}
```

---

## Combined Verdict and Enforcement

```typescript
// workers/post-create/crisis-enforce.ts
import { Env } from '../../types';
import type { CrisisLexicalResult } from './crisis-gate';
import type { CrisisAIResult } from './crisis-ai-classify';
import { ulid } from 'ulidx';

export type CrisisEnforcementAction =
  | 'none'
  | 'label'
  | 'reach_limit'
  | 'remove';

export async function enforcePost(
  postId: string,
  authorId: string,
  lexical: CrisisLexicalResult,
  ai: CrisisAIResult | null,  // null if AI pass was skipped
  env: Env
): Promise<CrisisEnforcementAction> {
  const now = Date.now();

  // Determine action
  let action: CrisisEnforcementAction = 'none';

  if (ai?.impersonatesOfficial && (ai.hoaxConfidence >= 0.75 || lexical.urgencyScore >= 0.8)) {
    action = 'remove';
  } else if (ai?.isHoax && ai.hoaxConfidence >= 0.70) {
    action = 'reach_limit';
  } else if (lexical.flagged || (ai?.isHoax && ai.hoaxConfidence >= 0.45)) {
    action = 'label';
  }

  // Persist to audit log
  await env.DB.prepare(
    `INSERT INTO crisis_hoax_verdicts
       (id, post_id, author_id, decided_at, lexical_score, ai_confidence,
        ai_category, impersonates_official, action)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    ulid(), postId, authorId, now,
    lexical.urgencyScore,
    ai?.hoaxConfidence ?? null,
    ai?.category ?? null,
    ai?.impersonatesOfficial ? 1 : 0,
    action
  ).run();

  // Apply enforcement
  switch (action) {
    case 'remove':
      await env.DB.prepare(
        `UPDATE posts SET removed = 1, removed_reason = 'crisis_hoax_impersonation', removed_at = ? WHERE id = ?`
      ).bind(now, postId).run();
      await env.REVIEW_QUEUE.send({ postId, authorId, action, priority: 'high', sla: now + 2 * 3_600_000 });
      break;

    case 'reach_limit':
      await env.DB.prepare(
        `UPDATE posts SET reach_limited = 1, reach_limit_reason = 'crisis_hoax', reach_limit_until = ? WHERE id = ?`
      ).bind(now + 24 * 3_600_000, postId).run();
      await env.REVIEW_QUEUE.send({ postId, authorId, action, priority: 'medium', sla: now + 4 * 3_600_000 });
      break;

    case 'label':
      await env.DB.prepare(
        `UPDATE posts SET crisis_label = 1 WHERE id = ?`
      ).bind(postId).run();
      break;

    case 'none':
      break;
  }

  return action;
}
```

---

## D1 Schema

```sql
-- D1 migration: 0019_crisis_hoax.sql
CREATE TABLE IF NOT EXISTS crisis_hoax_verdicts (
  id                   TEXT PRIMARY KEY,
  post_id              TEXT NOT NULL,
  author_id            TEXT NOT NULL,
  decided_at           INTEGER NOT NULL,
  lexical_score        REAL NOT NULL,
  ai_confidence        REAL,
  ai_category          TEXT,
  impersonates_official INTEGER NOT NULL DEFAULT 0,
  action               TEXT NOT NULL CHECK(action IN ('none','label','reach_limit','remove')),
  reviewed             INTEGER NOT NULL DEFAULT 0,
  reviewer_id          TEXT,
  reviewer_note        TEXT,
  final_action         TEXT
);

CREATE INDEX idx_chv_post    ON crisis_hoax_verdicts(post_id);
CREATE INDEX idx_chv_action  ON crisis_hoax_verdicts(action, decided_at DESC);
CREATE INDEX idx_chv_review  ON crisis_hoax_verdicts(reviewed, decided_at ASC);
```

---

## Amplification Detector Cron Worker

```typescript
// workers/cron/crisis-amplification.ts
/**
 * Detects posts that are spreading abnormally fast relative to the
 * author's historical average. Abnormal spread of a crisis-labelled
 * post elevates the enforcement to reach_limit regardless of initial classification.
 */
export async function detectAbnormalAmplification(env: Env): Promise<void> {
  const windowMs = 5 * 60_000;
  const now = Date.now();

  // Posts labelled as crisis that have share velocity > 5× author historical average
  const rows = await env.DB.prepare(
    `SELECT p.id, p.author_id,
            COUNT(s.id) as recent_shares,
            u.avg_shares_per_5min as baseline
       FROM posts p
       JOIN shares s ON s.post_id = p.id AND s.shared_at > ?
       JOIN user_share_baselines u ON u.user_id = p.author_id
      WHERE p.crisis_label = 1
        AND p.reach_limited = 0
        AND p.removed = 0
        AND p.created_at > ?
      GROUP BY p.id, p.author_id, u.avg_shares_per_5min
     HAVING recent_shares > (u.avg_shares_per_5min * 5) AND recent_shares > 20`
  ).bind(now - windowMs, now - 24 * 3_600_000)
   .all<{ id: string; author_id: string; recent_shares: number; baseline: number }>();

  for (const row of rows.results) {
    await env.DB.prepare(
      `UPDATE posts SET reach_limited = 1, reach_limit_reason = 'crisis_hoax_amplification',
         reach_limit_until = ? WHERE id = ?`
    ).bind(now + 24 * 3_600_000, row.id).run();

    await env.DB.prepare(
      `INSERT OR IGNORE INTO crisis_hoax_verdicts
         (id, post_id, author_id, decided_at, lexical_score, action)
       VALUES (?, ?, ?, ?, 0, 'reach_limit')`
    ).bind(ulid(), row.id, row.author_id, now).run();
  }
}
```

---

## Anti-patterns

- **Classifying news-reporting posts as hoaxes.** Legitimate journalists covering active emergencies use the same language patterns as hoaxers. Whitelist verified news account badges and apply zero enforcement even on high-scoring posts from verified accounts.
- **Removing all emergency-template posts without AI confirmation.** The lexical gate has high false-positive risk. Use it only for routing to the AI tier, never as a standalone removal signal.
- **Failing open when the AI model is unavailable.** If the AI call errors, default to `label` (not `none`) and queue for human review with high priority. A model outage during a real crisis hoax campaign is a known adversary tactic.
- **Treating every shoot-related term as a crisis hoax.** Sports posts ("Steph Curry shoots 45 points"), hunting content, and photography discussions match naive patterns. The AI tier distinguishes context; the lexical gate must not act alone.

---

## Gotchas

- `@cf/meta/llama-3.1-8b-instruct` occasionally outputs partial JSON when the post body approaches 2 000 characters. Always wrap the parse in a try/catch and fall back to a safe default (label, not remove).
- Reach-limitation `reach_limit_until` timestamps stored in D1 as Unix ms integers must be checked against `Date.now()` in the feed-ranking Worker; stale reach limits (passed expiry) that haven't been cleaned up will cause perpetually suppressed content.
- The amplification detector joins on `user_share_baselines`, a table that must be pre-populated by the daily analytics job. New accounts with no baseline will have `NULL` avg_shares_per_5min; guard with `COALESCE(u.avg_shares_per_5min, 1)`.
- False emergency posts often originate from newly created accounts. Combine crisis detection with account-age signals (< 7 days old + crisis label → automatic reach_limit regardless of confidence score).

---

## Verification

```bash
# Distribution of enforcement actions this week
wrangler d1 execute example project-prod --command \
  "SELECT action, COUNT(*) as n FROM crisis_hoax_verdicts
    WHERE decided_at > (strftime('%s','now') - 604800) * 1000
    GROUP BY action"

# Posts still reach-limited past their expiry (cleanup check)
wrangler d1 execute example project-prod --command \
  "SELECT COUNT(*) as stale FROM posts
    WHERE reach_limited = 1 AND reach_limit_until < (strftime('%s','now') * 1000)"

# Confirm removed impersonation posts are not serving
wrangler d1 execute example project-prod --command \
  "SELECT id, removed, removed_reason FROM posts
    WHERE id IN (SELECT post_id FROM crisis_hoax_verdicts WHERE action = 'remove')
      AND removed = 0"
```

---

## Related

- `election-misinformation-detection-workers-ai.md`
- `viral-misinformation-spread-containment-workers-queues.md`
- `crisis-intervention-detection-workers-ai.md`
- `safemessaging-compliance-response-workers.md`
- `emergency-content-takedown-circuit-breaker-queues.md`
- `brand-impersonation-detection-takedown.md`

---

## Sources

- First Draft — "Understanding Information Disorder" (2019) — https://firstdraftnews.org
- FEMA Emergency Alert System spoofing advisories — https://www.fema.gov/emergency-managers/practitioners/integrated-public-alert-warning-system
- Cloudflare Workers AI — @cf/meta/llama-3.1-8b-instruct — https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- example project crisis-content playbook v3 (internal wiki, 2026-Q2)
