# Workers AI Output Logprobs Confidence Scoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers AI pipeline produces text outputs but you cannot distinguish high-confidence
answers from hallucinations or hedged guesses. You need a signal beyond the raw text to
decide whether to present the result directly, send it for human review, or route to a
stronger model. Token log-probabilities (logprobs) provide this signal: tokens generated
with high certainty cluster near log(1) = 0, while uncertain or hallucinated tokens carry
strongly negative logprobs.

---

## Context

Log-probabilities are the model's per-token generation confidence expressed as
`log(P(token | context))`. A logprob of `0` means the model was certain (probability ≈ 1);
`-10` means the model considered this token very unlikely (probability ≈ 0.000045).

Common uses:
- **Response confidence** — average logprob across a generated response; low averages
  indicate hedged or uncertain output.
- **Span-level uncertainty** — identify which tokens have low logprobs (likely to be wrong
  named entities, numbers, or rare facts).
- **Selective self-consistency** — run N samples and weight by logprob-derived confidence
  to pick the most reliable answer.
- **Calibrated abstention** — withhold answers when the maximum per-token logprob falls
  below a threshold.

---

## Requesting Logprobs from Workers AI

Not all Workers AI models expose logprobs. At the time of writing, logprob access is
available for OpenAI-compatible endpoints via AI Gateway. For Workers AI directly,
the `logprobs` parameter is experimental and model-dependent.

### Via AI Gateway (OpenAI-compatible path)

```typescript
// logprobs-gateway.ts
interface LogprobToken {
  token: string;
  logprob: number;
  bytes?: number[];
}

interface LogprobContent {
  content: LogprobToken[];
}

interface GatewayChoice {
  message: { content: string };
  logprobs: LogprobContent | null;
}

interface GatewayResponse {
  choices: GatewayChoice[];
}

export async function runWithLogprobs(
  gatewayEndpoint: string,
  apiKey: string,
  model: string,
  messages: Array<{ role: string; content: string }>
): Promise<{ content: string; tokenLogprobs: LogprobToken[] }> {
  const res = await fetch(`${gatewayEndpoint}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      messages,
      logprobs: true,
      top_logprobs: 1,   // 1–5; higher values cost more
      max_tokens: 256,
    }),
  });

  if (!res.ok) throw new Error(`Gateway error ${res.status}: ${await res.text()}`);

  const data = (await res.json()) as GatewayResponse;
  const choice = data.choices[0];

  return {
    content: choice.message.content,
    tokenLogprobs: choice.logprobs?.content ?? [],
  };
}
```

### Via Workers AI Native (where supported)

```typescript
// logprobs-native.ts
export async function runNativeWithLogprobs(
  ai: Ai,
  prompt: string
): Promise<{ response: string; logprobs?: number[] }> {
  // Pass logprobs as an experimental parameter — silently ignored if unsupported
  const result = await (ai as any).run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [{ role: 'user', content: prompt }],
    logprobs: true,
    max_tokens: 128,
  });

  return {
    response: result.response ?? '',
    logprobs: result.logprobs ?? undefined,
  };
}
```

---

## Confidence Metrics from Logprobs

```typescript
// confidence.ts
import { LogprobToken } from './logprobs-gateway';

export interface ConfidenceReport {
  meanLogprob: number;          // average logprob across all tokens
  minLogprob: number;           // worst single token (most uncertain)
  perplexity: number;           // exp(-meanLogprob); lower = more confident
  lowConfidenceTokens: LogprobToken[]; // tokens below a threshold
  score: number;                // 0–1 normalised confidence
}

const LOW_CONFIDENCE_THRESHOLD = -2.0; // roughly P < 0.135

export function computeConfidence(tokens: LogprobToken[]): ConfidenceReport {
  if (tokens.length === 0) {
    return { meanLogprob: 0, minLogprob: 0, perplexity: 1, lowConfidenceTokens: [], score: 1 };
  }

  const logprobs = tokens.map((t) => t.logprob);
  const mean = logprobs.reduce((s, x) => s + x, 0) / logprobs.length;
  const min = Math.min(...logprobs);

  // Normalise to [0, 1]: logprobs in [-10, 0]; clamp and invert
  const normScore = Math.max(0, Math.min(1, (mean + 10) / 10));

  return {
    meanLogprob: mean,
    minLogprob: min,
    perplexity: Math.exp(-mean),
    lowConfidenceTokens: tokens.filter((t) => t.logprob < LOW_CONFIDENCE_THRESHOLD),
    score: normScore,
  };
}
```

---

## Abstention and Routing Based on Confidence

```typescript
// worker.ts
import { runWithLogprobs } from './logprobs-gateway';
import { computeConfidence, ConfidenceReport } from './confidence';

const ACCEPT_THRESHOLD = 0.70;   // score >= this: return directly
const CASCADE_THRESHOLD = 0.45;  // score in [this, ACCEPT): cascade to larger model
                                  // score < CASCADE_THRESHOLD: route to human review

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { question } = await req.json<{ question: string }>();

    const { content, tokenLogprobs } = await runWithLogprobs(
      env.AI_GATEWAY_ENDPOINT,
      env.AI_API_KEY,
      'llama-3.1-8b-instruct',
      [
        { role: 'system', content: 'Answer factual questions concisely. If unsure, say "I don\'t know".' },
        { role: 'user', content: question },
      ]
    );

    const confidence = computeConfidence(tokenLogprobs);

    if (confidence.score >= ACCEPT_THRESHOLD) {
      return Response.json({ answer: content, confidence: confidence.score, source: 'fast' });
    }

    if (confidence.score >= CASCADE_THRESHOLD) {
      // Cascade to a larger model
      const { content: strongAnswer, tokenLogprobs: strongLogprobs } = await runWithLogprobs(
        env.AI_GATEWAY_ENDPOINT,
        env.AI_API_KEY,
        'llama-3.3-70b-instruct',
        [
          { role: 'system', content: 'Answer factual questions concisely. If unsure, say "I don\'t know".' },
          { role: 'user', content: question },
        ]
      );

      const strongConfidence = computeConfidence(strongLogprobs);
      return Response.json({
        answer: strongAnswer,
        confidence: strongConfidence.score,
        source: 'cascade',
      });
    }

    // Low confidence: queue for human review
    await env.REVIEW_QUEUE.send({ question, draftAnswer: content, confidence });
    return Response.json({ status: 'queued', confidence: confidence.score });
  },
};
```

---

## Span-Level Uncertainty Highlighting

Return which parts of the answer are uncertain so the UI can highlight them.

```typescript
// highlight.ts
import { LogprobToken } from './logprobs-gateway';

export interface HighlightedSpan {
  text: string;
  isUncertain: boolean;
  logprob: number;
}

export function highlightUncertainTokens(
  tokens: LogprobToken[],
  threshold = -2.0
): HighlightedSpan[] {
  // Merge consecutive tokens of the same certainty class
  const spans: HighlightedSpan[] = [];
  let current: HighlightedSpan | null = null;

  for (const token of tokens) {
    const uncertain = token.logprob < threshold;

    if (current && current.isUncertain === uncertain) {
      current.text += token.token;
      current.logprob = Math.min(current.logprob, token.logprob);
    } else {
      if (current) spans.push(current);
      current = { text: token.token, isUncertain: uncertain, logprob: token.logprob };
    }
  }

  if (current) spans.push(current);
  return spans;
}
```

---

## Storing Confidence Metrics in D1 for Calibration

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS response_confidence (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
  model          TEXT    NOT NULL,
  question_hash  TEXT    NOT NULL,
  mean_logprob   REAL    NOT NULL,
  min_logprob    REAL    NOT NULL,
  perplexity     REAL    NOT NULL,
  score          REAL    NOT NULL,
  routed_to      TEXT    NOT NULL,  -- 'fast' | 'cascade' | 'human'
  ground_truth   TEXT                -- populated by human reviewers
);
```

Use ground truth labels to compute calibration error (ECE) and adjust the `ACCEPT_THRESHOLD`
and `CASCADE_THRESHOLD` constants over time.

---

## Anti-patterns

- **Treating mean logprob as a probability** — exponentiate to get probability (perplexity
  is the inverse), and then only after normalising for response length.
- **Relying on `top_logprobs: 1` for all decisions** — requesting `top_logprobs: 5` lets
  you inspect the runner-up tokens, which reveals whether uncertainty is between two close
  options or diffuse across many.
- **Ignoring token count** — a 200-token answer with mean logprob `-1.5` is less reliable
  than a 10-token answer with the same mean; longer responses accumulate more uncertainty.
- **Using logprobs from one model to gate another** — logprob scales differ between models;
  threshold calibration must be done per model.

---

## Gotchas

- Logprob support in Workers AI native mode is experimental and may not appear in model
  responses if the backend does not expose it — always check for the field's presence
  before computing metrics.
- Whitespace and punctuation tokens often have very high logprobs (near 0) and inflate
  the mean; filter them out before computing span-level uncertainty.
- `top_logprobs` increases response payload size; for high-throughput paths, request
  logprobs only for a sampled fraction of traffic and use the distribution to tune
  thresholds offline.
- AI Gateway may strip or transform the `logprobs` field in caching responses; ensure
  caching is disabled (`cf-skip-cache: true`) for logprob-dependent paths.

---

## Verification

1. Send a factual question with a known correct answer; inspect `tokenLogprobs` and confirm
   that correctly generated proper nouns have logprobs closer to 0 than filler words.
2. Send an unanswerable question (e.g. "What is my cat's name?"); confirm the model's
   uncertainty tokens ("I don't know") carry higher logprobs (less negative) than
   hallucinated specifics would.
3. Set `ACCEPT_THRESHOLD = 0.99`; confirm all requests route to the cascade or review queue.
4. Set `ACCEPT_THRESHOLD = 0.0`; confirm all requests return directly without cascading.
5. After 100 logged requests, query D1 to check that `routed_to` distribution matches
   the expected cascade rate for the chosen thresholds.

---

## Related

- `workers-ai-text-classification-confidence-thresholding.md`
- `llm-temperature-sampling-decoding.md`
- `ai-gateway-conditional-model-routing.md`
- `model-cascade-cheap-first-routing.md`
- `llm-output-validation.md`
- `llm-ab-testing.md`

---

## Sources

- OpenAI logprobs documentation (compatible API): https://platform.openai.com/docs/api-reference/chat/object
- Cloudflare AI Gateway: https://developers.cloudflare.com/ai-gateway/
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- Guo et al., "On Calibration of Modern Neural Networks", ICML 2017
