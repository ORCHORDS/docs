# Workers AI Model Capability Regression Postmortem

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Over a 72-hour window in production, the example project (example.com) audio intelligence pipeline
began returning malformed transcription JSON: the `words` array — used for karaoke-style
word-level highlighting — was present in the response schema but consistently empty, despite
the `word_timestamps` parameter being set to `true`. Users reported that the word-sync feature
had "broken", and the product team initially assumed a frontend regression. Root cause was
eventually traced to a silent capability change in the `@cf/openai/whisper-large-v3-turbo` model
served by Workers AI: Cloudflare had updated the model weights behind the same model identifier
without bumping the identifier or publishing a changelog to the developer dashboard.

The incident represents a new category of production risk specific to managed AI inference
platforms: model capability regression under a stable model ID, with no version pin mechanism
available to consumers and no automated regression test in the deploy pipeline.

## Context

Workers AI provides serverless AI inference through the `ai.run()` binding. Models are
referenced by a string identifier such as `@cf/openai/whisper-large-v3-turbo`. Unlike container
images or npm packages, Workers AI model identifiers are mutable references: Cloudflare retains
the right to update model weights, quantization, runtime, or post-processing logic behind an
existing identifier to improve quality, reduce cost, or address safety issues. There is no
`@cf/openai/whisper-large-v3-turbo@sha256:...` pin syntax available to consumers.

example project uses Workers AI for audio transcription at the core of its feature set. The
transcription Worker calls `@cf/openai/whisper-large-v3-turbo` with `word_timestamps: true`
and passes the resulting `words` array to a downstream alignment service that drives
word-level UI highlights. The pipeline had been stable for four months before the incident.

## Timeline

**Day 0, ~14:00 UTC** — Cloudflare updates model weights for `@cf/openai/whisper-large-v3-turbo`
(inferred from behavior; no public changelog). The `words` array is now returned empty for all
inputs.

**Day 0, 16:30 UTC** — First user reports: "Word highlighting stopped working."

**Day 0, 17:00 UTC** — Frontend engineer investigates; assumes a React state bug. Closes without
a fix after 45 minutes.

**Day 1, 09:00 UTC** — Second wave of user reports. A support ticket is escalated to engineering.

**Day 1, 11:30 UTC** — Backend engineer reproduces the issue in staging using the same audio
file that previously returned word timestamps. Confirms `words: []` in the AI response.

**Day 1, 13:00 UTC** — Engineer checks the Workers AI model changelog in the dashboard — no
entry for this model. Opens a Cloudflare support ticket.

**Day 2, 08:00 UTC** — Cloudflare support confirms an "infrastructure update" to the Whisper
model occurred on Day 0 and that word timestamps are temporarily unavailable for the turbo
variant. An ETA is not provided.

**Day 3, 11:00 UTC** — example project engineering deploys a fallback: if `words` is empty, fall
back to `@cf/openai/whisper-large-v3` (non-turbo variant) for the word-timestamp pass.

**Day 3, 11:15 UTC** — Word highlighting restored for all users. Fallback adds ~400 ms latency.

## Root Cause Analysis

The model capability regression was caused by a Cloudflare-side change to model weights or
post-processing logic. From the consumer side, the call code was unchanged:

```typescript
// transcription-worker/src/transcribe.ts
export async function transcribeAudio(
  env: Env,
  audioBuffer: ArrayBuffer
): Promise<WhisperResult> {
  const result = await env.AI.run('@cf/openai/whisper-large-v3-turbo', {
    audio: [...new Uint8Array(audioBuffer)],
    task: 'transcribe',
    language: 'en',
    word_timestamps: true,
  });
  return result as WhisperResult;
}
```

The response shape before the model update:

```json
{
  "text": "Hello world this is a test",
  "words": [
    { "word": "Hello", "start": 0.0, "end": 0.48 },
    { "word": "world", "start": 0.52, "end": 0.94 }
  ]
}
```

The response shape after the model update:

```json
{
  "text": "Hello world this is a test",
  "words": []
}
```

The downstream alignment service received an empty `words` array, treated it as valid input
(no guard against empty arrays), and silently produced no word-sync output. No error was raised
anywhere in the pipeline, so no alert fired. The regression was only detectable through
business-level product monitoring (word-sync activation rate), which was not instrumented.

## Impact Analysis

- 72 hours of degraded word-highlighting feature for 100 % of new transcriptions.
- Estimated 18 000 transcription jobs produced empty word-sync output.
- Word-sync is a key differentiator for example project premium tier; churn analysis showed a 3.2 %
  increase in premium-to-free downgrades during the incident window.
- No data loss; transcribed text (`text` field) was unaffected.
- Two enterprise customers flagged the regression in quarterly business reviews.

## Remediation

### Short-term: capability guard with fallback model

```typescript
// transcription-worker/src/transcribe.ts (post-incident)
const PRIMARY_MODEL   = '@cf/openai/whisper-large-v3-turbo';
const FALLBACK_MODEL  = '@cf/openai/whisper-large-v3';

export async function transcribeAudio(
  env: Env,
  audioBuffer: ArrayBuffer
): Promise<WhisperResult> {
  const primary = await env.AI.run(PRIMARY_MODEL, {
    audio: [...new Uint8Array(audioBuffer)],
    task: 'transcribe',
    language: 'en',
    word_timestamps: true,
  }) as WhisperResult;

  // Capability guard: if word timestamps are missing, fall back to non-turbo model
  if (primary.words && primary.words.length > 0) {
    return primary;
  }

  env.METRICS.writeDataPoint({
    blobs: [PRIMARY_MODEL, 'word_timestamps_missing'],
    doubles: [1],
    indexes: ['workers_ai_capability_guard'],
  });

  const fallback = await env.AI.run(FALLBACK_MODEL, {
    audio: [...new Uint8Array(audioBuffer)],
    task: 'transcribe',
    language: 'en',
    word_timestamps: true,
  }) as WhisperResult;

  return fallback;
}
```

### Long-term: AI capability regression test in CI

Add a synthetic golden-sample test that runs on every deployment and after every scheduled
model health check:

```typescript
// tests/ai-capability-regression.test.ts
import { describe, it, expect } from 'vitest';
import { SELF } from 'cloudflare:test';

// A 3-second reference audio clip with known word boundaries
const REFERENCE_AUDIO_URL = 'https://assets.internal/test-clips/hello-world-3s.wav';
const EXPECTED_WORD_COUNT_MIN = 4;

describe('Workers AI capability regression suite', () => {
  it('returns non-empty word_timestamps for reference clip', async () => {
    const res = await SELF.fetch('/internal/transcribe-test', {
      method: 'POST',
      body: JSON.stringify({ audio_url: REFERENCE_AUDIO_URL }),
      headers: { 'X-Internal-Test': '1' },
    });
    expect(res.status).toBe(200);
    const { words } = await res.json<{ words: unknown[] }>();
    expect(Array.isArray(words)).toBe(true);
    expect(words.length).toBeGreaterThanOrEqual(EXPECTED_WORD_COUNT_MIN);
  });
});
```

**Scheduled capability probe** (runs every 6 hours via Cron Trigger):

```typescript
// capability-probe-worker/src/index.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const result = await env.AI.run('@cf/openai/whisper-large-v3-turbo', {
      audio: env.REFERENCE_AUDIO_BYTES,
      task: 'transcribe',
      language: 'en',
      word_timestamps: true,
    }) as { words?: unknown[] };

    const ok = Array.isArray(result.words) && result.words.length > 0;

    await env.DB.prepare(
      'INSERT INTO ai_capability_checks (model, capability, ok, checked_at) VALUES (?, ?, ?, ?)'
    ).bind('@cf/openai/whisper-large-v3-turbo', 'word_timestamps', ok ? 1 : 0, Date.now()).run();

    if (!ok) {
      await fetch(env.PAGERDUTY_WEBHOOK, {
        method: 'POST',
        body: JSON.stringify({
          event_action: 'trigger',
          payload: {
            summary: 'Workers AI word_timestamps capability missing on whisper-large-v3-turbo',
            severity: 'warning',
            source: 'capability-probe-worker',
          },
        }),
        headers: { 'Content-Type': 'application/json' },
      });
    }
  }
};
```

## Prevention

- **Instrument capability-level metrics**, not just error rates. A silent degradation (empty
  array vs. error) is invisible to standard error-rate SLOs.
- **Abstract model identifiers** behind feature flags so they can be swapped without a code
  deploy when Cloudflare makes a regression change.
- **Run golden-sample regression tests** against live Workers AI endpoints in a staging Worker
  after every Cloudflare maintenance window.
- **Subscribe to Cloudflare status and changelog feeds** via RSS/webhook and route Workers AI
  model update notices to the on-call channel.

## Anti-patterns

- Assuming a stable model identifier means stable model behaviour indefinitely.
- Treating an empty response field as valid input to downstream services without a guard.
- Relying solely on HTTP error codes to detect AI inference regressions — capability
  regressions typically return HTTP 200 with degraded payload.
- Coupling product-critical features to a single model with no fallback path.
- Skipping AI-specific integration tests in CI because "it's an external service."

## Gotchas

- Workers AI model identifiers are mutable — `@cf/openai/whisper-large-v3-turbo` today may
  not behave identically to `@cf/openai/whisper-large-v3-turbo` in six months.
- There is no `cf-model-version` header or fingerprint in Workers AI responses to detect when
  the underlying model has changed.
- Cloudflare does not currently provide a model pinning mechanism (hash or version suffix) for
  production use cases.
- The `word_timestamps` parameter for Whisper models on Workers AI is a best-effort feature;
  it may not be available across all runtime configurations or quantizations.
- Workers AI free tier requests and paid requests may be routed to different GPU pools with
  potentially different model configurations.

## Verification

```bash
# 1. Test the capability probe Worker directly
curl -X POST https://capability-probe.internal.workers.dev/ \
  -H "X-Cron-Test: 1"

# 2. Check the capability check history in D1
wrangler d1 execute DB --command \
  "SELECT model, capability, ok, datetime(checked_at/1000, 'unixepoch') as ts
   FROM ai_capability_checks ORDER BY checked_at DESC LIMIT 20;"

# 3. Verify fallback fires correctly by mocking an empty words response in Miniflare
npx vitest run tests/ai-capability-regression.test.ts

# 4. Confirm Analytics Engine emits the capability_guard metric
wrangler tail transcription-worker --format=json \
  | jq 'select(.logs[].message | contains("workers_ai_capability_guard"))'
```

## Related

- `workers-ai-cold-start-latency-production-lesson.md`
- `workers-ai-model-deprecation-migration-adr.md`
- `workers-ai-rate-limit-exceeded-production-incident.md`
- `third-party-api-changes-break-silent-integrations.md`

## Sources

- Cloudflare Workers AI model documentation: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare system status page: https://www.cloudflarestatus.com/
- Cloudflare Workers AI Whisper model reference: https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/
