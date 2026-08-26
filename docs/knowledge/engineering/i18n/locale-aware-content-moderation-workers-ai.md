# Locale-Aware Content Moderation with Workers AI

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A UGC (user-generated content) platform operates in 20+ locales. Its single English-only
moderation model misses hate speech in Arabic, German, and Thai while simultaneously over-flagging
colloquial expressions in Portuguese. Teams need a moderation pipeline that runs at the edge,
applies locale-specific classifiers and word lists, and logs decisions to D1 for audit.

---

## Context

Cloudflare Workers AI provides text classification and zero-shot classification models that can be
instructed to evaluate content in any language. Combined with locale-specific deny lists in Workers
KV and decision logging in D1, a fully edge-native moderation pipeline requires no external SaaS
moderation API. The approach layers three signals: (1) KV deny-list fast-path, (2) AI classifier,
and (3) locale-specific threshold calibration stored in D1.

Workers AI models used in this guide:
- `@cf/huggingface/distilbert-sst-2-int8` — binary sentiment/toxicity proxy
- `@cf/mistral/mistral-7b-instruct-v0.1` — zero-shot multilingual classification prompt

---

## 1. Deny-List Fast-Path from KV

Each locale has its own KV namespace key holding a newline-delimited list of banned phrases.
The fast-path blocks obviously violating content before the more expensive AI call.

```typescript
// worker/moderation/denylist.ts
export async function matchesDenyList(
  env: Env,
  text: string,
  locale: string
): Promise<boolean> {
  const raw = await env.MODERATION_KV.get(`denylist:${locale}`);
  if (!raw) return false;

  const normalised = text.toLowerCase();
  for (const phrase of raw.split('\n')) {
    const trimmed = phrase.trim();
    if (trimmed && normalised.includes(trimmed.toLowerCase())) return true;
  }
  return false;
}
```

---

## 2. AI Classification with Locale-Specific Prompt

The LLM receives a system prompt instructing it to evaluate content strictly in the content's own
language. The locale tag is passed as context so the model applies culturally appropriate norms.

```typescript
// worker/moderation/classify.ts
interface ClassifyResult {
  flagged: boolean;
  category: string;   // "hate_speech" | "spam" | "harassment" | "safe"
  confidence: number; // 0.0–1.0
}

export async function classifyWithAI(
  env: Env,
  text: string,
  locale: string
): Promise<ClassifyResult> {
  const systemPrompt = `You are a content moderation assistant.
The content below is written in locale "${locale}".
Evaluate it for: hate_speech, spam, harassment, or safe.
Reply with a JSON object: {"category": "<label>", "confidence": <0-1>}.
Do not explain. Output only the JSON.`;

  const response = await env.AI.run('@cf/mistral/mistral-7b-instruct-v0.1', {
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: text },
    ],
    max_tokens: 60,
  });

  try {
    const parsed = JSON.parse(response.response.trim());
    return {
      flagged: parsed.category !== 'safe',
      category: parsed.category ?? 'safe',
      confidence: Number(parsed.confidence ?? 0),
    };
  } catch {
    // Parsing failure defaults to flagged for safety
    return { flagged: true, category: 'parse_error', confidence: 0 };
  }
}
```

---

## 3. Locale-Specific Threshold Calibration

Different locales have different false-positive rates. Thresholds are tuned per locale in D1 and
consulted before making the final moderation decision.

```typescript
// worker/moderation/thresholds.ts
interface ThresholdRow {
  locale: string;
  min_confidence: number; // AI confidence must exceed this to auto-block
  auto_block: number;     // 1 = block without human review, 0 = queue for review
}

export async function getThreshold(
  env: Env,
  locale: string
): Promise<ThresholdRow> {
  const row = await env.DB.prepare(
    `SELECT locale, min_confidence, auto_block
     FROM moderation_thresholds
     WHERE locale = ?
     LIMIT 1`
  )
    .bind(locale)
    .first<ThresholdRow>();

  // Fallback to conservative global default
  return row ?? { locale, min_confidence: 0.75, auto_block: 0 };
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS moderation_thresholds (
  locale        TEXT PRIMARY KEY,
  min_confidence REAL NOT NULL DEFAULT 0.75,
  auto_block    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS moderation_log (
  id            TEXT PRIMARY KEY,
  locale        TEXT NOT NULL,
  content_hash  TEXT NOT NULL,  -- SHA-256 hex, never store raw UGC text
  category      TEXT NOT NULL,
  confidence    REAL NOT NULL,
  decision      TEXT NOT NULL,  -- "blocked" | "queued" | "approved"
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 4. Composing the Moderation Pipeline

```typescript
// worker/moderation/pipeline.ts
import { matchesDenyList } from './denylist';
import { classifyWithAI } from './classify';
import { getThreshold } from './thresholds';

export type ModerationDecision = 'blocked' | 'queued' | 'approved';

export async function moderate(
  env: Env,
  contentId: string,
  text: string,
  locale: string
): Promise<{ decision: ModerationDecision; category: string }> {
  // Layer 1: deny-list fast-path
  if (await matchesDenyList(env, text, locale)) {
    await logDecision(env, contentId, locale, 'hate_speech', 1.0, 'blocked');
    return { decision: 'blocked', category: 'hate_speech' };
  }

  // Layer 2: AI classifier
  const { flagged, category, confidence } = await classifyWithAI(env, text, locale);

  if (!flagged) {
    await logDecision(env, contentId, locale, category, confidence, 'approved');
    return { decision: 'approved', category };
  }

  // Layer 3: threshold calibration
  const threshold = await getThreshold(env, locale);
  const decision: ModerationDecision =
    confidence >= threshold.min_confidence && threshold.auto_block === 1
      ? 'blocked'
      : 'queued';

  await logDecision(env, contentId, locale, category, confidence, decision);
  return { decision, category };
}

async function logDecision(
  env: Env,
  contentId: string,
  locale: string,
  category: string,
  confidence: number,
  decision: ModerationDecision
): Promise<void> {
  const hash = await sha256Hex(contentId); // use content ID as audit ref
  await env.DB.prepare(
    `INSERT OR IGNORE INTO moderation_log
     (id, locale, content_hash, category, confidence, decision)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(contentId, locale, hash, category, confidence, decision)
    .run();
}

async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(input)
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

---

## 5. HTTP Handler

```typescript
// worker/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { contentId, text, locale } = await request.json<{
      contentId: string;
      text: string;
      locale: string;
    }>();

    if (!contentId || !text || !locale) {
      return new Response('Missing fields', { status: 400 });
    }

    const result = await moderate(env, contentId, text, locale);
    return Response.json(result);
  },
};
```

---

## Anti-patterns

- **Storing raw UGC text in the audit log** — store only the content ID or a hash; raw text
  introduces PII and legal risk.
- **Using a single English-only classifier for all locales** — sentiment and toxicity transfer
  poorly across languages; always pass locale context to the model.
- **Hard-coding thresholds in Worker code** — thresholds need live tuning by trust-and-safety
  teams; store them in D1 and reload without redeployment.
- **Blocking on AI latency for every request** — run the KV deny-list synchronously, but enqueue
  the AI call via Workers Queues for non-real-time moderation paths.

---

## Gotchas

- Workers AI LLM outputs are non-deterministic; the JSON parsing step must have a safe fallback
  (default to `flagged: true`) to avoid approving content on model errors.
- `@cf/mistral/mistral-7b-instruct-v0.1` has a cold-start latency on the first request in a
  region; keep Workers AI bindings warm with scheduled pings via Cron Triggers if P99 latency
  is a concern.
- KV deny-lists are eventually consistent; a phrase added to the list may not propagate to all
  edge nodes for up to 60 seconds.
- The D1 `moderation_log` table will grow unboundedly; add a Cron-triggered cleanup job to
  archive rows older than your retention policy.

---

## Verification

```bash
# Approved content
curl -X POST https://my-worker.example.com/moderate \
  -H "Content-Type: application/json" \
  -d '{"contentId":"c1","text":"I love this product!","locale":"en"}'
# Expected: {"decision":"approved","category":"safe"}

# Denied by deny-list (add a test phrase to KV key denylist:en first)
curl -X POST https://my-worker.example.com/moderate \
  -H "Content-Type: application/json" \
  -d '{"contentId":"c2","text":"<banned phrase>","locale":"en"}'
# Expected: {"decision":"blocked","category":"hate_speech"}

# Audit log check
wrangler d1 execute MY_DB \
  --command "SELECT * FROM moderation_log ORDER BY created_at DESC LIMIT 5;"
```

---

## Related

- `machine-translation-workers-ai-quality-scoring.md`
- `language-detection-workers-accept-language.md`
- `workers-queues-async-translation-pipeline.md`
- `i18n-ai-translation-pipelines-2026.md`

---

## Sources

- Cloudflare Workers AI documentation — https://developers.cloudflare.com/workers-ai/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Unicode CLDR locale data — https://cldr.unicode.org/
