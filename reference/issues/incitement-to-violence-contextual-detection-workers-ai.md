# Incitement to Violence — Contextual Detection with Workers AI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Anonymous posts on example project contain language that, read literally, might appear as political
commentary or hyperbole ("someone should do something about X"), but in context — combined with a
named individual, a referenced location, a timing signal (an upcoming event), or a thread
continuation — constitutes credible incitement to violence. Simple keyword blocklists generate too
many false positives (satire, news quotation) and miss contextual incitement that uses coded or
indirect language.

---

## Context

Incitement to violence differs from hate speech in that it calls for a specific action (harm)
against a specific target. Legal definitions vary:

- **EU DSA / Framework Decision 2008/913/JHA** — "public provocation to commit a terrorist offence"
  must be removed within 1 hour of a law enforcement referral.
- **US 18 U.S.C. § 875(c)** — threatening communications in interstate commerce.
- **Brandenburg v. Ohio** (US Supreme Court) — speech is only incitement if directed to producing
  imminent lawless action and is likely to produce such action.

Key signals that elevate a post from offensive speech to incitement:
1. Named or described individual target
2. Specific method or weapon referenced
3. Time/location specificity ("tomorrow at the rally")
4. Call-to-action phrasing ("someone needs to", "who will stop X")
5. Thread context: post is a reply to a post about a real person

Workers AI can score each signal in isolation and as a combination. The pipeline must pass
**thread context** (parent posts) to the VLM so it can evaluate the cumulative signal, not just
the leaf post.

---

## Architecture

```
New post → Worker (context-fetch → incitement score → threshold dispatch)
         → D1 (incitement_events)
         → Queues (high-priority moderation queue)
             → auto-remove / law-enforcement-flag / human-review
```

---

## Implementation

### 1. Context Assembler — Fetch Thread for LLM

```typescript
// src/context/thread-assembler.ts
import type { Env } from '../types';

export interface ThreadPost {
  postId: string;
  content: string;
  authorToken: string; // anonymised hash, not real user ID
}

/**
 * Fetch up to MAX_CONTEXT_POSTS ancestor posts so the classifier
 * can evaluate incitement in context, not in isolation.
 */
const MAX_CONTEXT_POSTS = 5;

export async function assembleThreadContext(
  postId: string,
  env: Env,
): Promise<ThreadPost[]> {
  // Walk the parent chain using a recursive CTE for efficiency
  const rows = await env.DB.prepare(
    `WITH RECURSIVE thread(post_id, content, author_token, parent_id, depth) AS (
       SELECT post_id, content, author_token, parent_id, 0
       FROM posts WHERE post_id = ?
       UNION ALL
       SELECT p.post_id, p.content, p.author_token, p.parent_id, t.depth + 1
       FROM posts p
       JOIN thread t ON p.post_id = t.parent_id
       WHERE t.depth < ?
     )
     SELECT post_id, content, author_token FROM thread ORDER BY depth DESC`,
  )
    .bind(postId, MAX_CONTEXT_POSTS)
    .all<ThreadPost>();

  return rows.results;
}
```

### 2. Incitement Scorer

```typescript
// src/scoring/incitement.ts
import type { Env } from '../types';
import type { ThreadPost } from '../context/thread-assembler';

export interface IncitementScore {
  score: number;           // 0.0 – 1.0
  isIncitement: boolean;
  signals: IncitementSignal[];
  urgency: 'low' | 'medium' | 'high' | 'critical';
}

export interface IncitementSignal {
  type: 'named_target' | 'specific_method' | 'time_location' | 'call_to_action' | 'thread_escalation';
  present: boolean;
  detail: string;
}

function buildPrompt(thread: ThreadPost[], newContent: string): string {
  const threadSummary = thread
    .map((p, i) => `[${i + 1}] ${p.content}`)
    .join('\n');

  return `
You are a content-safety classifier specialising in incitement to violence detection.

Conversation thread (oldest first):
${threadSummary}

New post to evaluate:
"""${newContent}"""

Assess whether the new post, in the context of this thread, constitutes incitement to violence.
Consider: named/described human targets, specific methods or weapons, time/place specificity,
explicit or implicit call-to-action, escalation from prior thread posts.

Respond ONLY with this JSON schema:
{
  "score": <0.0–1.0>,
  "is_incitement": <boolean>,
  "urgency": <"low"|"medium"|"high"|"critical">,
  "signals": [
    {
      "type": <"named_target"|"specific_method"|"time_location"|"call_to_action"|"thread_escalation">,
      "present": <boolean>,
      "detail": <string>
    }
  ]
}

Score guide:
- 0.0–0.3: No meaningful incitement signal
- 0.3–0.6: Ambiguous / monitor
- 0.6–0.8: Probable incitement — human review required
- 0.8–1.0: Clear incitement — immediate action required, urgency=critical
`.trim();
}

export async function scoreIncitement(
  thread: ThreadPost[],
  newContent: string,
  env: Env,
): Promise<IncitementScore> {
  const prompt = buildPrompt(thread, newContent);

  const result = await env.AI.run('@cf/meta/llama-3.3-70b-instruct-fp8-fast', {
    prompt,
    max_tokens: 400,
  });

  try {
    const parsed = JSON.parse((result as { response: string }).response);
    return {
      score:        Number(parsed.score ?? 0),
      isIncitement: Boolean(parsed.is_incitement),
      signals:      Array.isArray(parsed.signals) ? parsed.signals : [],
      urgency:      parsed.urgency ?? 'low',
    };
  } catch {
    return { score: 0, isIncitement: false, signals: [], urgency: 'low' };
  }
}
```

### 3. Main Post Handler — Orchestrated Gate

```typescript
// src/handlers/post-incitement-gate.ts
import { assembleThreadContext } from '../context/thread-assembler';
import { scoreIncitement } from '../scoring/incitement';
import type { Env } from '../types';

const THRESHOLD_AUTO_REMOVE  = 0.80;
const THRESHOLD_HUMAN_REVIEW = 0.55;
const THRESHOLD_LAW_FLAG     = 0.90; // critical + time-location signal

export async function handlePostWithIncitementGate(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<{ content: string; parentPostId?: string }>();
  const postId = crypto.randomUUID();

  // Fetch thread context (ancestor chain)
  const thread = body.parentPostId
    ? await assembleThreadContext(body.parentPostId, env)
    : [];

  const incitement = await scoreIncitement(thread, body.content, env);

  // Persist event for audit and reporting
  await env.DB.prepare(
    `INSERT INTO incitement_events
       (post_id, parent_post_id, score, is_incitement, urgency, signals, created_at)
     VALUES (?, ?, ?, ?, ?, ?, unixepoch())`,
  ).bind(
    postId,
    body.parentPostId ?? null,
    incitement.score,
    incitement.isIncitement ? 1 : 0,
    incitement.urgency,
    JSON.stringify(incitement.signals),
  ).run();

  // Critical + specific time/location → law enforcement flag
  const hasTimeLocation = incitement.signals.some(
    (s) => s.type === 'time_location' && s.present,
  );
  if (incitement.score >= THRESHOLD_LAW_FLAG && hasTimeLocation) {
    await env.MODERATION_QUEUE.send({
      postId,
      action: 'law_enforcement_flag',
      urgency: 'critical',
      score: incitement.score,
    });
  }

  if (incitement.score >= THRESHOLD_AUTO_REMOVE) {
    await env.MODERATION_QUEUE.send({ postId, action: 'auto_remove', urgency: incitement.urgency });
    return Response.json({ postId, status: 'rejected' }, { status: 202 });
  }

  if (incitement.score >= THRESHOLD_HUMAN_REVIEW) {
    await env.MODERATION_QUEUE.send({ postId, action: 'human_review', urgency: incitement.urgency });
  }

  // Store post (may be held for review but saved for audit)
  await env.DB.prepare(
    `INSERT INTO posts (post_id, content, parent_id, created_at) VALUES (?, ?, ?, unixepoch())`,
  ).bind(postId, body.content, body.parentPostId ?? null).run();

  return Response.json({ postId, status: 'accepted' });
}
```

### 4. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS posts (
  post_id    TEXT PRIMARY KEY,
  content    TEXT NOT NULL,
  parent_id  TEXT REFERENCES posts(post_id),
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_posts_parent ON posts(parent_id);

CREATE TABLE IF NOT EXISTS incitement_events (
  post_id        TEXT PRIMARY KEY REFERENCES posts(post_id),
  parent_post_id TEXT,
  score          REAL NOT NULL DEFAULT 0.0,
  is_incitement  INTEGER NOT NULL DEFAULT 0,
  urgency        TEXT NOT NULL DEFAULT 'low',
  signals        TEXT,           -- JSON array of IncitementSignal
  created_at     INTEGER NOT NULL,
  actioned_at    INTEGER,
  action_taken   TEXT            -- 'auto_remove' | 'human_review' | 'cleared' | 'law_flag'
);

CREATE INDEX idx_incitement_score  ON incitement_events(score DESC, created_at DESC);
CREATE INDEX idx_incitement_urgency ON incitement_events(urgency, created_at DESC);
```

---

## Anti-patterns

- **Evaluating only the leaf post** — incitement often builds across a thread; a post that says
  "someone should stop him" is benign alone but incitement after a prior post names a person and
  describes a location.
- **Using a keyword blocklist as the primary gate** — words like "kill", "attack", or "destroy" are
  common in video game, sports, and metaphorical contexts. VLM context scoring dramatically reduces
  false positives vs. keyword matching alone.
- **Single-step auto-removal for borderline scores** — 0.55–0.80 should always route to human
  review; premature auto-removal of political hyperbole creates user trust and DSA fairness issues.
- **Not logging signals** — regulators (DSA, Ofcom) may require explanation of automated removal
  decisions. Storing `signals` as JSON enables structured justification generation.

---

## Gotchas

- Thread depth is capped at `MAX_CONTEXT_POSTS` to stay within the LLM's effective context window
  and Worker CPU limits. Very long threads may omit early context.
- The recursive CTE `WITH RECURSIVE` is supported in D1 (SQLite-compatible); test explicitly
  because D1 workers on older schema versions have occasionally had query planner regressions.
- `urgency: 'critical'` must gate a law-enforcement notification workflow — this requires explicit
  legal review of your jurisdiction's mandatory reporting obligations before enabling.
- Workers AI inference latency for the 70B model can be 3–6 s per call. For high-traffic posts,
  consider gating: first run a lightweight classifier (keyword + pattern regex), then invoke VLM
  only if preliminary score ≥ 0.3.
- Do not surface the incitement score to the posting user; it teaches evasion strategies.

---

## Verification

```typescript
// Smoke test: a post with clear call-to-action and named target should score ≥ 0.80
const testCases = [
  {
    content: "Someone needs to deal with John Smith who lives on Elm Street permanently",
    expectScore: '>= 0.80',
    expectUrgency: 'critical',
  },
  {
    content: "I'm going to destroy you in chess tomorrow",
    expectScore: '< 0.30',
    expectUrgency: 'low',
  },
];
```

Ops monitoring query:

```sql
-- Critical incitement events not actioned within 1 hour
SELECT post_id, score, created_at,
       (unixepoch() - created_at) / 60 AS minutes_pending
FROM incitement_events
WHERE urgency = 'critical'
  AND action_taken IS NULL
  AND created_at > unixepoch() - 86400
ORDER BY created_at ASC;
```

---

## Related

- `hate-speech-detection-multilingual-workers-ai.md` — hate speech (non-incitement)
- `dog-whistle-coded-language-detection-workers-ai.md` — coded language
- `crisis-intervention-detection-workers-ai.md` — self-harm detection (different pipeline)
- `election-misinformation-detection-workers-ai.md` — political content policy
- `content-appeal-escalation-workflow-durable-objects.md` — appeal after removal

---

## Sources

- EU Framework Decision 2008/913/JHA on racism and xenophobia
- DSA Regulation (EU) 2022/2065 — Art. 26 risk assessment; Art. 34 systemic risk
- Terrorist Content Online Regulation (EU) 2021/784 — 1-hour removal obligation
- Brandenburg v. Ohio, 395 U.S. 444 (1969) — US incitement standard
- Cloudflare Workers AI model catalogue: https://developers.cloudflare.com/workers-ai/models/
