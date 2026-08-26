# ai-content-moderation-pipeline

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Users on an anonymous social platform (example project) post hate speech,
NSFW images, and coordinated spam. The moderation queue floods
with 10 k items/hour; human reviewers miss 40 % of violating
content because the pipeline is synchronous and times out before
returning a verdict. Adversarial users encode slurs in leetspeak,
Unicode look-alikes, or base64 to evade classifier models.

## Context

A production pipeline layers fast automated classifiers (< 50 ms),
async escalation to human review, and retraining loops on
confirmed violations. example project users are anonymous — no account
history exists as a prior; every post is judged on content alone.
Synchronous moderation must fit the 200 ms response SLA;
anything slower runs async with the post held pending.

## 1  Classifier tiers and confidence routing

```
                 ┌──────────────────────────────────────┐
POST content ──► │ Tier 1: fast rule-based filter (2 ms)│
                 │  • blocklist, regex, length heuristics│
                 └──────────────┬───────────────────────┘
                                │ pass
                 ┌──────────────▼───────────────────────┐
                 │ Tier 2: ML classifier (30 ms)         │
                 │  • NSFW / hate / spam scores [0,1]    │
                 └──────┬────────────────────┬───────────┘
                        │ conf ≥ 0.9         │ 0.5–0.9
              ┌─────────▼──────┐    ┌────────▼────────┐
              │ Auto-block     │    │ Human queue      │
              └────────────────┘    └─────────────────┘
                                             │ conf < 0.5
                                    ┌────────▼────────┐
                                    │ Allow (monitor) │
                                    └─────────────────┘
```

Thresholds are tunable per content type; NSFW images use a
lower block threshold (0.85) than text spam (0.92) because
false negatives are more costly.

## 2  Classifier invocation in a Worker

```typescript
interface ModerationResult {
  nsfw: number;
  hate: number;
  spam: number;
  verdict: "allow" | "hold" | "block";
}

async function moderateText(
  text: string,
  env: Env,
): Promise<ModerationResult> {
  // Run both classifiers concurrently to fit latency budget
  const [openaiRes, customRes] = await Promise.all([
    fetch("https://api.openai.com/v1/moderations", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.OPENAI_KEY}`,
                 "Content-Type": "application/json" },
      body: JSON.stringify({ input: text }),
    }).then((r) => r.json()),
    env.HATE_CLASSIFIER.fetch(
      new Request("https://internal/score",
        { method: "POST", body: text }),
    ).then((r) => r.json()),
  ]);

  const nsfw  = openaiRes.results[0].category_scores["sexual"];
  const hate  = Math.max(
    openaiRes.results[0].category_scores["hate"],
    customRes.hate_score,
  );
  const spam  = customRes.spam_score;
  const max   = Math.max(nsfw, hate, spam);

  const verdict =
    max >= 0.9  ? "block"
    : max >= 0.5 ? "hold"
    : "allow";

  return { nsfw, hate, spam, verdict };
}
```

## 3  Adversarial evasion mitigations

| Attack vector | Mitigation |
|---------------|------------|
| Leetspeak (h4te) | Normalise to ASCII before classifying |
| Unicode homoglyphs (ɑ for a) | Unicode NFKD + confusable map |
| Base64-encoded slurs | Detect and decode `[A-Za-z0-9+/]{20,}={0,2}` |
| Multilingual evasion | Run `langdetect`; route to lang-specific model |
| Image text embedding | OCR (Tesseract / Workers AI vision) before scoring |

```typescript
function normaliseText(input: string): string {
  // Unicode NFKD decompose + strip diacritics
  let s = input.normalize("NFKD").replace(/[̀-ͯ]/g, "");
  // Detect and decode base64 segments
  s = s.replace(/[A-Za-z0-9+/]{20,}={0,2}/g, (m) => {
    try { return atob(m); } catch { return m; }
  });
  // Map common leetspeak
  return s.replace(/[04@]/g, "o")
          .replace(/[13]/g,  "e")
          .replace(/5/g,     "s");
}
```

## 4  Human review queue (example project architecture)

```typescript
// Producer: send held post to Cloudflare Queue
async function enqueueForReview(
  postId: string,
  scores: ModerationResult,
  env: Env,
): Promise<void> {
  await env.MODERATION_QUEUE.send({
    postId,
    scores,
    queuedAt: Date.now(),
    priority: scores.hate > 0.7 ? "high" : "normal",
  });
}
// Consumer Worker pulls messages and writes to D1 review
// dashboard; each message is acked after DB insert.
```

## 5  Latency budget

| Phase | Target | Notes |
|-------|--------|-------|
| Rule-based filter | < 2 ms | Inline Worker code |
| ML classifier (sync) | < 50 ms | Workers AI |
| Response to user | < 200 ms | Allow/block immediately |
| Human review queue | async | Cloudflare Queue |
| Reviewer SLA | < 4 h | Priority + paging |

Posts in "hold" are stored in R2 and hidden from the feed.

## Anti-patterns

- Running moderation synchronously in series with the LLM
  call — doubles latency when both paths must complete.
- Using a single global threshold for all content types —
  violence in news context differs from violence in UGC.
- Relying solely on the provider moderation API — it misses
  domain-specific slurs and community-specific norms.
- Logging raw violating content to general application logs
  — creates liability and content-at-rest risk.
- Blocking on confidence alone without an appeal path —
  false positives on legitimate posts damage trust.

## Gotchas

- OpenAI Moderation API is rate-limited to 1 000 req/min;
  buffer at high volume with a Cloudflare Queue.
- Classifiers trained on English perform poorly on code-switched
  text; add multilingual models for a global platform.
- example project anonymous posts have no reputation history; weight
  content-only scores higher than on accounts-based platforms.
- Human reviewers experience vicarious trauma; implement
  exposure limits, blur tools, and support resources.

## Verification

- Run 500 human-labelled samples through the pipeline; target
  precision ≥ 0.95, recall ≥ 0.90 on hate class.
- Load-test the sync path at 300 RPS; confirm P99 latency
  < 200 ms with classifier calls concurrent.
- Inject base64-encoded slur; confirm normalisation decodes it
  and classifier scores hate ≥ 0.9.

## Related

- `ai-ml/ai-content-moderation.md`
- `ai-ml/ai-safety-guardrails.md`
- `ai-ml/pii-detection-redaction.md`
- `ai-ml/ai-output-filtering.md`
- `ai-ml/prompt-injection-defense-strategies.md`

## Source URLs (verified 2026-08-17)

- https://platform.openai.com/docs/guides/moderation
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/workers-ai/
- https://perspectiveapi.com/
- https://arxiv.org/abs/2204.05149  (ToxiGen multilingual)
