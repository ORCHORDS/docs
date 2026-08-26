# Radicalization Pathway Detection Using Workers AI Sequence Analysis

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Individual posts pass content moderation review but users are progressing through a
radicalization content funnel — gateway content, grievance amplification, in-group
identity, then explicit incitement — without the sequence itself triggering any alert.

## Context
Radicalization is a journey, not a single piece of content. Researchers (Moonshot CVE,
RAND, ISD) consistently find that the path matters as much as any endpoint: a user
consuming mildly conspiratorial content, then outgroup-dehumanizing content, then
organized-group recruitment content is a materially different risk than isolated exposure
to any one of those categories. Workers AI classifies individual posts; D1 stores behavioral
sequences as a sliding window; a Cron Trigger runs pathway scoring against known radicalization
archetypes. This is a signal-to-human-review pipeline, not an automated action system —
final decisions are made by trust and safety reviewers.

## D1 Behavioral Sequence Schema

```sql
-- migrations/0020_radicalization_pathway.sql
CREATE TABLE content_exposure_log (
  id              TEXT PRIMARY KEY,
  session_id      TEXT NOT NULL,   -- anonymous session, not user ID
  content_id      TEXT NOT NULL,
  risk_category   TEXT,            -- populated by Workers AI classifier
  risk_score      REAL,            -- 0.0–1.0
  exposure_type   TEXT NOT NULL    -- 'view' | 'share' | 'comment' | 'save'
    CHECK (exposure_type IN ('view','share','comment','save')),
  logged_at       INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_exposure_session ON content_exposure_log(session_id, logged_at);
CREATE INDEX idx_exposure_risk    ON content_exposure_log(risk_category, logged_at)
  WHERE risk_score > 0.5;

CREATE TABLE radicalization_pathway_alerts (
  id              TEXT PRIMARY KEY,
  session_id      TEXT NOT NULL,
  archetype       TEXT NOT NULL,   -- e.g. 'conspiracy_to_violence', 'religious_extremism'
  pathway_score   REAL NOT NULL,   -- composite 0–100
  window_start    INTEGER NOT NULL,
  window_end      INTEGER NOT NULL,
  reviewed_by     TEXT,
  disposition     TEXT CHECK (disposition IN ('false_positive','escalated','actioned',NULL)),
  created_at      INTEGER NOT NULL DEFAULT (unixepoch())
);
```

## Workers AI Content Classification on Ingestion

Tag every piece of content at view-time with a radicalization risk category and score,
without blocking the response — classification runs in a `waitUntil` task.

```typescript
// src/lib/classify-content.ts
import type { Env } from '../env';

export type RiskCategory =
  | 'benign'
  | 'conspiracy_gateway'
  | 'outgroup_grievance'
  | 'dehumanization'
  | 'in_group_identity'
  | 'recruitment_call'
  | 'explicit_incitement';

const CATEGORY_LABELS: Record<RiskCategory, string> = {
  benign:               'Content that poses no radicalization risk',
  conspiracy_gateway:   'Mildly conspiratorial content; gateway exposure',
  outgroup_grievance:   'Content framing outgroup as source of personal/collective harm',
  dehumanization:       'Language that strips humanity from a group',
  in_group_identity:    'Content reinforcing us-vs-them in-group solidarity',
  recruitment_call:     'Content inviting users to join an organized movement',
  explicit_incitement:  'Direct call for violence or illegal action against a group',
};

export async function classifyRadicalizationRisk(
  text: string,
  env: Env,
): Promise<{ category: RiskCategory; score: number }> {
  const labels   = Object.values(CATEGORY_LABELS);
  const result   = await env.AI.run('@cf/huggingface/distilbert-sst-2-int8', {
    // Use zero-shot classification with radicalization-specific labels
    inputs: {
      text,
      candidate_labels: labels,
    },
  }) as { labels: string[]; scores: number[] };

  // Map the highest-scoring label back to its category key
  const topIdx   = result.scores.indexOf(Math.max(...result.scores));
  const topLabel = result.labels[topIdx];
  const category = (Object.keys(CATEGORY_LABELS) as RiskCategory[])
    .find(k => CATEGORY_LABELS[k] === topLabel) ?? 'benign';

  return { category, score: result.scores[topIdx] };
}
```

```typescript
// src/handlers/content-view.ts — log exposure asynchronously
export async function handleContentView(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const { contentId, sessionId, text } = await req.json<{
    contentId: string; sessionId: string; text: string;
  }>();

  ctx.waitUntil(logExposure(contentId, sessionId, text, env));

  return Response.json({ ok: true });
}

async function logExposure(
  contentId: string,
  sessionId: string,
  text: string,
  env: Env,
): Promise<void> {
  const { category, score } = await classifyRadicalizationRisk(text, env);
  const { nanoid }          = await import('nanoid');

  await env.DB.prepare(
    `INSERT INTO content_exposure_log (id, session_id, content_id, risk_category, risk_score, exposure_type)
     VALUES (?, ?, ?, ?, ?, 'view')`
  ).bind(nanoid(), sessionId, contentId, category, score).run();
}
```

## Pathway Archetype Scoring via Cron

A known radicalization pathway is a sequence of risk categories consumed in order within
a rolling time window. Score sessions against multiple archetype templates.

```typescript
// src/jobs/pathway-scoring.ts
import type { Env } from '../env';
import { nanoid } from 'nanoid';

interface PathwayArchetype {
  name:     string;
  sequence: string[];   // ordered risk_category values
  windowSeconds: number;
  minScore: number;     // threshold to generate an alert
}

// Based on published radicalization literature (Moonshot CVE "3 Pillars" model)
const ARCHETYPES: PathwayArchetype[] = [
  {
    name: 'conspiracy_to_violence',
    sequence: ['conspiracy_gateway', 'outgroup_grievance', 'dehumanization', 'explicit_incitement'],
    windowSeconds: 7 * 86400,  // 7-day window
    minScore: 60,
  },
  {
    name: 'online_recruitment',
    sequence: ['outgroup_grievance', 'in_group_identity', 'recruitment_call'],
    windowSeconds: 14 * 86400,
    minScore: 55,
  },
  {
    name: 'rapid_escalation',
    sequence: ['conspiracy_gateway', 'dehumanization', 'explicit_incitement'],
    windowSeconds: 48 * 3600,  // 48-hour window — faster is worse
    minScore: 70,
  },
];

export async function scoreRadicalizationPathways(env: Env): Promise<void> {
  const now    = Math.floor(Date.now() / 1000);

  // Get active sessions with any elevated-risk exposure in the last 14 days
  const { results: sessions } = await env.DB.prepare(
    `SELECT DISTINCT session_id FROM content_exposure_log
     WHERE risk_score > 0.5
       AND logged_at > ?
       AND session_id NOT IN (
         SELECT session_id FROM radicalization_pathway_alerts
         WHERE created_at > ? AND disposition IS NULL  -- already pending review
       )`
  ).bind(now - 14 * 86400, now - 86400).all<{ session_id: string }>();

  for (const { session_id } of sessions) {
    for (const archetype of ARCHETYPES) {
      const score = await scoreArchetype(session_id, archetype, now, env);
      if (score >= archetype.minScore) {
        const window = archetype.windowSeconds;
        await env.DB.prepare(
          `INSERT INTO radicalization_pathway_alerts
             (id, session_id, archetype, pathway_score, window_start, window_end)
           VALUES (?, ?, ?, ?, ?, ?)`
        ).bind(nanoid(), session_id, archetype.name, score, now - window, now).run();
        // One alert per archetype per session — don't spam the queue
        break;
      }
    }
  }
}

async function scoreArchetype(
  sessionId: string,
  archetype: PathwayArchetype,
  now: number,
  env: Env,
): Promise<number> {
  const windowStart = now - archetype.windowSeconds;

  const { results } = await env.DB.prepare(
    `SELECT risk_category, MAX(risk_score) as peak_score, MIN(logged_at) as first_seen
     FROM content_exposure_log
     WHERE session_id = ?
       AND logged_at BETWEEN ? AND ?
       AND risk_category IN (${archetype.sequence.map(() => '?').join(',')})
     GROUP BY risk_category
     ORDER BY first_seen`
  ).bind(sessionId, windowStart, now, ...archetype.sequence).all<{
    risk_category: string; peak_score: number; first_seen: number;
  }>();

  const categoryMap = new Map(results.map(r => [r.risk_category, r]));

  // Sequence completion score: each step in order is worth (100 / steps) points
  // Weighted by peak_score and whether temporal order is preserved
  let score         = 0;
  let lastSeen      = 0;
  const stepValue   = 100 / archetype.sequence.length;

  for (const category of archetype.sequence) {
    const row = categoryMap.get(category);
    if (!row) continue;
    if (row.first_seen >= lastSeen) {
      score   += stepValue * row.peak_score;
      lastSeen = row.first_seen;
    } else {
      // Out-of-order exposure counts for less
      score   += stepValue * row.peak_score * 0.4;
    }
  }

  return Math.min(score, 100);
}
```

## Anti-patterns
- Automating account suspension on pathway score alone — this is a signal to human review, not a verdict
- Using a fixed 30-day window for all archetypes — rapid-escalation patterns compress into 24–72 hours
- Storing raw post text in `content_exposure_log` — retain only the content ID; fetch text from source on demand for review
- Running pathway scoring synchronously on every view — the scoring cron keeps it out of the hot path
- Conflating "viewed" with "endorsed" — viewing extremist content may mean a researcher or counter-extremism worker

## Gotchas
- `@cf/huggingface/distilbert-sst-2-int8` is a sentiment model, not a hate/radicalization model — production deployments should use a fine-tuned model (Jigsaw Perspective, Hive, or self-hosted) and treat the above as a template
- Session IDs on anonymous platforms rotate on cookie clear; a single user may appear as multiple sessions — link session IDs to device fingerprint hashes for continuity
- The `waitUntil` budget in Workers is 30 seconds; if AI classification exceeds this, offload via Queue
- False positive rates on "recruitment_call" are high for legitimate community-building content — tune archetype `minScore` per launch with T&S reviewers before enabling alerts
- GDPR/CCPA retention: behavioral logs are personal data; cap `content_exposure_log` to 90 days and enforce via a nightly DELETE

## Verification

```sql
-- Sessions currently flagged pending review
SELECT session_id, archetype, pathway_score,
       datetime(created_at, 'unixepoch') AS flagged_at
FROM radicalization_pathway_alerts
WHERE disposition IS NULL
ORDER BY pathway_score DESC
LIMIT 20;

-- False positive rate by archetype (last 30 days)
SELECT archetype,
       COUNT(*) FILTER (WHERE disposition = 'false_positive') AS fp,
       COUNT(*) FILTER (WHERE disposition = 'actioned') AS actioned,
       COUNT(*) TOTAL
FROM radicalization_pathway_alerts
WHERE created_at > unixepoch() - 30 * 86400
GROUP BY archetype;
```

## Related
- `incitement-to-violence-contextual-detection-workers-ai.md` — single-post incitement detection
- `hate-speech-detection-multilingual-workers-ai.md` — hate speech at the post level
- `gifct-hash-sharing-terrorist-content-tcap.md` — hash-based terrorist content matching
- `election-misinformation-detection-workers-ai.md` — radicalization intersects with political misinformation
- `dog-whistle-coded-language-detection-workers-ai.md` — coded language that scores low individually but signals high in sequence

## Sources
- https://moonshotcve.com/the-three-pillars-of-radicalization/
- https://www.rand.org/topics/radicalization-and-violent-extremism.html
- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
