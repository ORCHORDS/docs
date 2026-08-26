# Workers AI Hallucination Moderation False Positive Incident

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project users began reporting that valid, benign posts were being rejected by the content moderation pipeline with a generic "Community Guidelines violation" error. The rejection rate for first-time posts spiked from a baseline of ~0.8% to over 34% within 20 minutes of a Workers AI model routing change. Users could not publish posts, stories, or replies during the window.

## Context

The platform uses a Workers AI–backed moderation pipeline that classifies every user-generated post before it is persisted to D1. The pipeline calls `@cf/meta/llama-3-8b-instruct` via the `AI` binding and interprets the JSON output to make an allow/deny decision. A silent model routing update on Cloudflare's side changed the default quantisation tier for the model, altering its structured-output behaviour without any version-pin change on our end.

## Timeline

- **09:12 UTC** — Cloudflare silently rotates `@cf/meta/llama-3-8b-instruct` to a lower-quantisation variant for capacity reasons.
- **09:14 UTC** — First user reports of post rejection appear in Discord.
- **09:19 UTC** — Automated alert fires: `moderation_deny_rate > 5%` for 5 minutes.
- **09:22 UTC** — On-call engineer begins investigation; assumes user-generated spam spike.
- **09:31 UTC** — Engineer reviews raw AI responses in tail-worker logs; sees malformed JSON and unexpected label strings.
- **09:38 UTC** — Root cause identified: model returning `"SAFE"`, `"safe"`, and `"Safe"` inconsistently; parser treats anything other than `"SAFE"` as deny.
- **09:44 UTC** — Hotfix deployed: normalise model output to lowercase before comparison.
- **09:46 UTC** — Deny rate drops back to 0.9%; incident closed.
- **10:30 UTC** — Post-incident review scheduled.

## Root Cause

The moderation Worker parsed the AI classification response with a strict string equality check:

```typescript
// workers/moderation.ts — BUGGY VERSION
interface ModerationResult {
  label: "SAFE" | "UNSAFE" | "REVIEW";
  confidence: number;
  reason?: string;
}

async function classifyContent(text: string, ai: Ai): Promise<ModerationResult> {
  const response = await ai.run("@cf/meta/llama-3-8b-instruct", {
    messages: [
      {
        role: "system",
        content: `You are a content moderator. Classify the following post strictly as JSON:
{"label": "SAFE"|"UNSAFE"|"REVIEW", "confidence": 0.0-1.0, "reason": "..."}
Respond with JSON only. No markdown, no explanation.`,
      },
      { role: "user", content: text },
    ],
  });

  // PROBLEM: assumes response is always valid JSON with exact casing
  const result: ModerationResult = JSON.parse(response.response);

  // PROBLEM: strict equality — any casing variant fails to "SAFE" branch
  if (result.label !== "SAFE") {
    return { label: "UNSAFE", confidence: result.confidence ?? 1.0, reason: result.reason };
  }
  return result;
}
```

After the model routing change, the model occasionally returned:
- `{"label": "safe", ...}` (lowercase)
- `{"label": "Safe", ...}` (title case)
- Unparseable responses with markdown fences: `` ```json\n{"label": "SAFE"}\n``` ``

All of these caused the `!== "SAFE"` check to evaluate `true`, silently classifying legitimate content as unsafe.

## Impact

- **Duration:** 32 minutes (09:14 – 09:46 UTC)
- **Users affected:** ~4,200 active users attempting to post
- **Posts incorrectly rejected:** ~18,700 moderation decisions
- **Retry volume:** 3× normal queue depth as users retried rejected posts
- **Revenue impact:** None directly; trust impact with new users onboarding during the window

## Fix

```typescript
// workers/moderation.ts — FIXED VERSION
const SAFE_LABELS = new Set(["safe", "Safe", "SAFE", "safe_content"]);
const UNSAFE_LABELS = new Set(["unsafe", "Unsafe", "UNSAFE", "harmful", "violating"]);

function parseModerationResponse(raw: string): ModerationResult {
  // Strip markdown code fences if model wraps output
  const cleaned = raw.trim().replace(/^```(?:json)?\n?/, "").replace(/\n?```$/, "").trim();

  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(cleaned);
  } catch {
    // Non-parseable response: default to REVIEW for human inspection
    return { label: "REVIEW", confidence: 0.5, reason: "AI response unparseable" };
  }

  const rawLabel = String(parsed.label ?? "").toUpperCase().trim();
  const confidence = typeof parsed.confidence === "number" ? parsed.confidence : 0.5;
  const reason = typeof parsed.reason === "string" ? parsed.reason : undefined;

  if (rawLabel === "SAFE") return { label: "SAFE", confidence, reason };
  if (rawLabel === "UNSAFE") return { label: "UNSAFE", confidence, reason };
  // Any other value (including empty) goes to human review queue
  return { label: "REVIEW", confidence, reason: reason ?? `Unexpected label: ${rawLabel}` };
}

async function classifyContent(text: string, ai: Ai): Promise<ModerationResult> {
  try {
    const response = await ai.run("@cf/meta/llama-3-8b-instruct", {
      messages: [
        {
          role: "system",
          content: `Classify the post. Respond with JSON only (no markdown):
{"label":"SAFE","confidence":0.95,"reason":"..."}
label must be exactly SAFE, UNSAFE, or REVIEW.`,
        },
        { role: "user", content: text },
      ],
    });
    return parseModerationResponse(response.response ?? "");
  } catch (err) {
    // AI binding failure: route to human review, never auto-deny
    console.error("Workers AI moderation error", err);
    return { label: "REVIEW", confidence: 0, reason: "AI binding error" };
  }
}
```

## Prevention

1. **Model output contract tests** added to CI using Miniflare mocks that inject known-bad response formats.
2. **Deny-rate alert threshold** tightened from 5% over 5 min to 2% over 2 min.
3. **Shadow mode flag** added: when `MODERATION_SHADOW_MODE=true` the worker logs decisions but never blocks — enables safe comparison when model routing changes.
4. **Tail worker sampling** increased from 1% to 10% for moderation decisions to speed up diagnosis.
5. Added `@cf/meta/llama-3-8b-instruct` to Cloudflare changelog monitoring via RSS.

```typescript
// wrangler.toml — add shadow mode var
[vars]
MODERATION_SHADOW_MODE = false

// Staging override
[env.staging.vars]
MODERATION_SHADOW_MODE = true
```

## Anti-patterns

- Treating AI structured output as guaranteed valid JSON without a parse fallback.
- Using strict string equality on model-generated label values.
- Defaulting to "deny" on any unexpected response rather than routing to human review.
- Assuming Workers AI model behaviour is stable across Cloudflare's internal routing changes.
- Not testing the moderation pipeline against malformed and variant-cased model responses.

## Gotchas

- Workers AI does not expose which internal model variant/quantisation tier is serving a named model alias. The same `@cf/meta/llama-3-8b-instruct` string can produce different output styles silently.
- LLMs are not deterministic — even with identical prompts, casing and whitespace in JSON keys can vary per request.
- Markdown code-fence wrapping in responses is common when the model was fine-tuned for chat, even when the system prompt says "JSON only".
- The AI binding throws on network error but returns a string (not an error) on model-level refusals — always check response content, not just catch blocks.
- A "fail closed" (deny on error) moderation policy feels safe but produces a far worse user experience incident than "fail to review".

## Verification

```typescript
// test/moderation.test.ts
import { describe, it, expect } from "vitest";
import { parseModerationResponse } from "../workers/moderation";

describe("parseModerationResponse", () => {
  it("handles lowercase safe", () => {
    expect(parseModerationResponse('{"label":"safe","confidence":0.9}')).toMatchObject({ label: "SAFE" });
  });
  it("handles markdown fences", () => {
    expect(parseModerationResponse('```json\n{"label":"SAFE","confidence":0.95}\n```')).toMatchObject({ label: "SAFE" });
  });
  it("routes unparseable response to REVIEW", () => {
    expect(parseModerationResponse("I cannot classify this.")).toMatchObject({ label: "REVIEW" });
  });
  it("routes unknown label to REVIEW", () => {
    expect(parseModerationResponse('{"label":"NEUTRAL","confidence":0.5}')).toMatchObject({ label: "REVIEW" });
  });
  it("never returns UNSAFE on empty response", () => {
    expect(parseModerationResponse("")).toMatchObject({ label: "REVIEW" });
  });
});
```

Monitor `moderation_deny_rate` and `moderation_review_rate` in Analytics Engine; a spike in either without a corresponding spam spike is a signal of a parsing or model regression.

## Related

- `workers-ai-rate-limit-exceeded-production-incident.md`
- `workers-ai-model-capability-regression-postmortem.md`
- `workers-ai-cold-start-latency-production-lesson.md`
- `ai-guardrails-2026.md`
- `hallucination-mitigation-2026.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/llama-3-8b-instruct/
- https://developers.cloudflare.com/workers-ai/configuration/bindings/
- https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
