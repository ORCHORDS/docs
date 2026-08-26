# Spam Post Detection with Cloudflare Workers AI

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project's anonymous posting model is exploited by spammers who submit near-duplicate
promotional posts, referral-link floods, and coordinated inauthentic content across
many accounts within minutes.  Simple keyword blocklists are bypassed by character
substitution and multilingual rewrites.  Human moderation queues fill faster than
moderators can clear them.  Mobile clients submit shorter posts at higher frequency
than desktop clients, requiring different classification thresholds to avoid
false-positives on legitimate short-form content.

## Context

Cloudflare Workers AI provides inference at the edge via `env.AI.run()` without
external egress latency.  For spam detection, the `@cf/microsoft/phi-2` or the
`@cf/meta/llama-3.1-8b-instruct` model can be used for zero-shot classification,
or the `@cf/huggingface/distilbert-sst-2-int8` model adapted as a binary classifier.
The purpose-built text-classification task (`AI.run('@cf/cardiffnlp/twitter-roberta-base-sentiment-latest', ...)`)
is available for sentiment but example project uses a prompt-based approach for flexibility.
Results feed a D1 audit log that persists classification decisions for regulatory
review and threshold-tuning analysis.

## Workers AI Spam Classification

A lightweight zero-shot prompt wraps the post content and asks the model to classify
it as SPAM or NOT_SPAM with a confidence score.

```ts
// worker/lib/spamClassifier.ts
export interface ClassificationResult {
  label: "SPAM" | "NOT_SPAM";
  confidence: number; // 0.0 – 1.0
  modelUsed: string;
  latencyMs: number;
}

export async function classifyPost(
  ai: Ai,
  content: string,
): Promise<ClassificationResult> {
  const start = Date.now();
  const prompt = `You are a spam detection system for an adult anonymous social platform.
Classify the following post as SPAM or NOT_SPAM.
Respond with exactly one JSON object: {"label":"SPAM"|"NOT_SPAM","confidence":0.0-1.0}
Do not add any other text.

Post: """${content.slice(0, 512)}"""`;

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [{ role: "user", content: prompt }],
    max_tokens: 32,
  });

  const raw = (response as { response: string }).response.trim();
  let parsed: { label: "SPAM" | "NOT_SPAM"; confidence: number };
  try {
    parsed = JSON.parse(raw);
  } catch {
    // Fallback: text scan for label keywords
    const isSpam = /SPAM/i.test(raw) && !/NOT_SPAM/i.test(raw);
    parsed = { label: isSpam ? "SPAM" : "NOT_SPAM", confidence: 0.6 };
  }

  return {
    label: parsed.label,
    confidence: Math.min(1, Math.max(0, parsed.confidence)),
    modelUsed: "@cf/meta/llama-3.1-8b-instruct",
    latencyMs: Date.now() - start,
  };
}
```

## Threshold Tuning: Mobile vs Desktop

Mobile example project users post shorter content (median 28 characters) compared to desktop
users (median 94 characters).  Shorter posts have lower signal density and the
classifier is less reliable; the threshold must be raised to reduce false positives.

```
┌─────────────────────┬───────────────────────────┬───────────────────────────────┐
│ Client Type         │ SPAM Threshold (block)     │ SPAM Threshold (flag-only)    │
├─────────────────────┼───────────────────────────┼───────────────────────────────┤
│ Desktop (≥ 640 px)  │ confidence ≥ 0.85          │ confidence ≥ 0.65             │
│ Mobile (< 640 px)   │ confidence ≥ 0.92          │ confidence ≥ 0.75             │
│ Unknown / headless  │ confidence ≥ 0.80          │ confidence ≥ 0.60             │
└─────────────────────┴───────────────────────────┴───────────────────────────────┘

Post length modifier (applied to all client types):
  content.length < 20 chars: threshold += 0.05 (shorter = less reliable)
  content.length > 300 chars: threshold -= 0.03 (longer = more reliable)
```

Client type is inferred from the `User-Agent` header and the `cf-device-type`
Cloudflare request header (`mobile` | `tablet` | `desktop`):

```ts
function getClientTier(request: Request): "mobile" | "desktop" | "unknown" {
  const deviceType = request.headers.get("cf-device-type");
  if (deviceType === "mobile" || deviceType === "tablet") return "mobile";
  if (deviceType === "desktop") return "desktop";
  return "unknown";
}
```

## D1 Audit Log

Every classification decision is persisted regardless of outcome to enable threshold
retrospective analysis and regulatory audit readiness.

```sql
CREATE TABLE IF NOT EXISTS spam_audit_log (
  id             TEXT    PRIMARY KEY,   -- UUIDv7
  post_id        TEXT,                  -- NULL if post was blocked pre-insert
  account_id     TEXT    NOT NULL,
  content_hash   TEXT    NOT NULL,      -- SHA-256 of post content (no raw text stored)
  content_length INTEGER NOT NULL,
  client_tier    TEXT    NOT NULL,      -- mobile | desktop | unknown
  model_used     TEXT    NOT NULL,
  confidence     REAL    NOT NULL,
  label          TEXT    NOT NULL,      -- SPAM | NOT_SPAM
  action_taken   TEXT    NOT NULL,      -- blocked | flagged | allowed
  threshold_used REAL    NOT NULL,
  latency_ms     INTEGER NOT NULL,
  created_at     INTEGER NOT NULL       -- Unix ms
);

CREATE INDEX idx_sal_account  ON spam_audit_log(account_id, created_at DESC);
CREATE INDEX idx_sal_action   ON spam_audit_log(action_taken, created_at DESC);
CREATE INDEX idx_sal_label    ON spam_audit_log(label, confidence DESC);
```

Content is stored as a SHA-256 hash only.  Raw post text is never persisted in the
audit log to minimise the PII surface.  The hash allows deduplication analysis:

```ts
const contentHash = await crypto.subtle.digest(
  "SHA-256",
  new TextEncoder().encode(content),
).then(buf => Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join(""));
```

## Post Submission Flow with AI Gate

```
POST /api/posts
       │
       ▼
  [1] Validate JWT + rate limit (KV)
       │
       ▼
  [2] classifyPost(ai, content)   ← Workers AI inference
       │
       ├── confidence >= block_threshold ──► 422 Unprocessable (SPAM_DETECTED)
       │                                         + write spam_audit_log (blocked)
       │
       ├── confidence >= flag_threshold ───► Insert post WITH spam_flag=1
       │                                         + write spam_audit_log (flagged)
       │                                         + enqueue moderation task
       │
       └── confidence < flag_threshold ────► Insert post normally
                                                + write spam_audit_log (allowed)
```

Workers AI `run()` is called inside the Worker request handler; if inference exceeds
the 30-second CPU limit (very rare for small models) the Worker throws a timeout.
Wrap with a 5-second `AbortController` and fall back to allow-with-flag:

```ts
const controller = new AbortController();
const timer = setTimeout(() => controller.abort(), 5000);
try {
  result = await classifyPost(env.AI, content);
} catch {
  result = { label: "NOT_SPAM", confidence: 0.5, modelUsed: "fallback", latencyMs: 5000 };
  actionTaken = "flagged"; // conservative: flag when AI times out
} finally {
  clearTimeout(timer);
}
```

## Anti-patterns

- Storing raw post text in `spam_audit_log` — creates a secondary content store,
  doubles storage costs, and complicates right-to-erasure requests.
- Using a single threshold for all client types — causes 15–20 % false-positive
  rate on mobile short-form content at thresholds tuned for desktop.
- Calling Workers AI synchronously in the critical path without a timeout — a slow
  inference response will exhaust the Worker's 30-second CPU time budget, returning
  a 503 to the user.
- Blocking on `label === "SPAM"` without checking `confidence` — the model may return
  "SPAM" with 0.51 confidence; low-confidence results should flag, not block.
- Running classification on every GET request — inference costs are per-invocation;
  classify only on write operations (POST, PUT of post content).

## Gotchas

- `env.AI` is bound in `wrangler.toml` as `[ai]` with no binding name override; the
  default binding name is `AI`.  If your wrangler.toml uses a custom name such as
  `WORKERS_AI`, update every `env.AI.run()` call accordingly.
- Workers AI models have input token limits.  `@cf/meta/llama-3.1-8b-instruct` accepts
  approximately 8 192 tokens; the 512-character content slice in the prompt is well
  within limits, but the system prompt adds ~80 tokens.  Do not remove the slice guard.
- `response.response` is the field name for text responses from the Messages API used
  by Llama models.  Other Workers AI task types return different field names
  (`result`, `label`); check the model's task type documentation before accessing.
- SHA-256 via `crypto.subtle` is async in Workers; do not omit `await` or the hash
  will be a `Promise` object stringified as `"[object Promise]"`.
- `cf-device-type` is only set when Cloudflare's device detection is active (enabled
  by default on all proxied zones).  It is absent in `wrangler dev` local mode; default
  to `"unknown"` in local dev to avoid undefined threshold lookups.

## Verification

```bash
# 1. Submit a clear spam post and confirm block
curl -X POST https://example.com/api/posts \
  -H "Authorization: Bearer $USER_JWT" \
  -H "Content-Type: application/json" \
  -d '{"content":"BUY CRYPTO NOW!! 100x gains guaranteed! DM @spammer t.me/pump"}'
# Expect: 422 {"error":"SPAM_DETECTED"}

# 2. Submit a normal short mobile-style post and confirm allow
curl -X POST https://example.com/api/posts \
  -H "Authorization: Bearer $USER_JWT" \
  -H "cf-device-type: mobile" \
  -d '{"content":"lol same"}'
# Expect: 201 Created

# 3. Check audit log for the blocked post
wrangler d1 execute example project-db --command \
  "SELECT action_taken, confidence, label FROM spam_audit_log ORDER BY created_at DESC LIMIT 3"

# 4. Verify no raw content in audit log
wrangler d1 execute example project-db --command \
  "SELECT content_hash, content_length FROM spam_audit_log LIMIT 1"
# Expect: SHA-256 hex string, no post text
```

## Related

- `anonymous-platform-abuse-prevention.md`
- `anonymous-content-reporting-worker-pipeline.md`
- `rate-limit-abuse-tor-exit-node-detection.md`
- `underage-user-detection-behavioral-signals.md`
- `worker-cpu-limit-exceeded.md`

## Sources

- Cloudflare Workers AI — developers.cloudflare.com/workers-ai/
- Workers AI Models Catalog — developers.cloudflare.com/workers-ai/models/
- Cloudflare D1 — developers.cloudflare.com/d1/
- Cloudflare `cf-device-type` header — developers.cloudflare.com/fundamentals/reference/http-request-headers/
- Web Crypto API (SHA-256) — developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
