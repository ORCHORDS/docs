# AI-Powered Content Moderation Gateway with Workers AI + AI Gateway

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

User-generated content (chat messages, reviews, comments) must be screened for harmful material before storage or publication. Manual moderation does not scale. You need an automated gateway that classifies content, blocks violations, logs decisions for audit, and bypasses checks for trusted sources — all with observable metrics.

## Context

The gateway sits between your application and the content store. Every submission passes through:

1. **Allowlist check** — trusted users (internal accounts, verified merchants) skip classification.
2. **AI classification** — Workers AI `@cf/meta/llama-guard-3-8b` evaluates content against harm categories.
3. **Decision enforcement** — safe content is forwarded; harmful content is blocked with a reason.
4. **Audit logging** — AI Gateway records every model call with inputs, outputs, and latency.
5. **Metrics** — Analytics Engine tracks moderation rates by category and user tier.

## Solution

### 1. Harm category enum

```typescript
// src/types/moderation.ts
export const HARM_CATEGORIES = [
  'hate_speech',
  'violence',
  'sexual_content',
  'self_harm',
  'harassment',
  'misinformation',
  'spam',
] as const;

export type HarmCategory = (typeof HARM_CATEGORIES)[number];

export interface ModerationResult {
  safe: boolean;
  category?: HarmCategory;
  confidence: number;
  raw: string; // model's raw output
}
```

### 2. Allowlist check

```typescript
// src/lib/allowlist.ts
import type { KVNamespace } from '@cloudflare/workers-types';

/**
 * Returns true if the user is on the trusted allowlist.
 * KV key: `allowlist:<userId>` => any truthy value.
 */
export async function isTrustedUser(
  kv: KVNamespace,
  userId: string,
): Promise<boolean> {
  const value = await kv.get(`allowlist:${userId}`);
  return value !== null;
}

/** Add a user to the allowlist (admin operation) */
export async function addTrustedUser(
  kv: KVNamespace,
  userId: string,
): Promise<void> {
  await kv.put(`allowlist:${userId}`, '1');
}

/** Remove a user from the allowlist */
export async function removeTrustedUser(
  kv: KVNamespace,
  userId: string,
): Promise<void> {
  await kv.delete(`allowlist:${userId}`);
}
```

### 3. LlamaGuard classification via AI Gateway

```typescript
// src/lib/classifier.ts
import type { Ai } from '@cloudflare/workers-types';
import { HARM_CATEGORIES, type ModerationResult } from '../types/moderation';

/**
 * Llama Guard returns either:
 *   "safe"
 *   "unsafe\n<category>"  (e.g. "unsafe\nS3" for sexual content)
 *
 * S-codes map to our harm categories:
 * S1=hate_speech, S2=violence, S3=sexual_content,
 * S4=self_harm, S5=harassment, S6=misinformation, S7=spam
 */
const S_CODE_MAP: Record<string, string> = {
  S1: 'hate_speech',
  S2: 'violence',
  S3: 'sexual_content',
  S4: 'self_harm',
  S5: 'harassment',
  S6: 'misinformation',
  S7: 'spam',
};

export async function classifyContent(
  ai: Ai,
  content: string,
  // AI Gateway gateway ID is embedded in the binding — no extra config needed
): Promise<ModerationResult> {
  const response = await ai.run('@cf/meta/llama-guard-3-8b', {
    messages: [
      {
        role: 'user',
        content,
      },
    ],
  });

  const raw = (response as { response?: string }).response?.trim() ?? '';
  const lower = raw.toLowerCase();

  if (lower === 'safe' || lower.startsWith('safe')) {
    return { safe: true, confidence: 1, raw };
  }

  // Parse "unsafe\nS3" style response
  const lines = raw.split('\n').map((l) => l.trim());
  const sCode = lines.find((l) => /^S\d+$/i.test(l))?.toUpperCase();
  const category = sCode ? S_CODE_MAP[sCode] : undefined;

  return {
    safe: false,
    category: category as ModerationResult['category'],
    confidence: 0.95, // LlamaGuard is binary; treat positive as high confidence
    raw,
  };
}
```

### 4. Analytics Engine metrics

```typescript
// src/lib/metrics.ts
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';
import type { ModerationResult } from '../types/moderation';

export function recordModerationEvent(
  ae: AnalyticsEngineDataset,
  userId: string,
  userTier: string,
  result: ModerationResult,
  bypassedAllowlist: boolean,
): void {
  ae.writeDataPoint({
    blobs: [
      userId,
      userTier,
      result.category ?? 'none',
      result.safe ? 'safe' : 'blocked',
      bypassedAllowlist ? 'allowlist' : 'classified',
    ],
    doubles: [result.confidence],
    indexes: [userId],
  });
}
```

### 5. Gateway middleware

```typescript
// src/lib/gateway.ts
import type { Ai, KVNamespace, AnalyticsEngineDataset } from '@cloudflare/workers-types';
import { isTrustedUser } from './allowlist';
import { classifyContent } from './classifier';
import { recordModerationEvent } from './metrics';

export interface GatewayEnv {
  AI: Ai;
  ALLOWLIST: KVNamespace;
  MODERATION_AE: AnalyticsEngineDataset;
}

export interface ContentSubmission {
  userId: string;
  userTier: string;   // 'free' | 'merchant' | 'internal'
  content: string;
}

export interface GatewayDecision {
  allowed: boolean;
  reason?: string;
  category?: string;
}

export async function moderateContent(
  submission: ContentSubmission,
  env: GatewayEnv,
): Promise<GatewayDecision> {
  const { userId, userTier, content } = submission;

  // 1. Allowlist bypass
  const trusted = await isTrustedUser(env.ALLOWLIST, userId);
  if (trusted) {
    recordModerationEvent(
      env.MODERATION_AE,
      userId,
      userTier,
      { safe: true, confidence: 1, raw: 'allowlist_bypass' },
      true,
    );
    return { allowed: true };
  }

  // 2. AI classification
  const result = await classifyContent(env.AI, content);

  // 3. Record metrics
  recordModerationEvent(env.MODERATION_AE, userId, userTier, result, false);

  // 4. Decision
  if (result.safe) {
    return { allowed: true };
  }

  return {
    allowed: false,
    reason: 'Content flagged by automated moderation.',
    category: result.category,
  };
}
```

### 6. Worker entry point

```typescript
// src/index.ts
import { moderateContent } from './lib/gateway';
import { addTrustedUser, removeTrustedUser } from './lib/allowlist';

export interface Env {
  AI: Ai;
  ALLOWLIST: KVNamespace;
  MODERATION_AE: AnalyticsEngineDataset;
  ADMIN_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Content submission
    if (request.method === 'POST' && url.pathname === '/submit') {
      const body = await request.json<{
        userId: string;
        userTier: string;
        content: string;
      }>();

      const decision = await moderateContent(body, env);

      if (!decision.allowed) {
        return Response.json(
          { error: decision.reason, category: decision.category },
          { status: 422 },
        );
      }

      // Forward to downstream content store here...
      return Response.json({ status: 'accepted' });
    }

    // Admin: add to allowlist
    if (request.method === 'POST' && url.pathname === '/admin/allowlist') {
      if (request.headers.get('x-admin-secret') !== env.ADMIN_SECRET) {
        return new Response('Unauthorized', { status: 401 });
      }
      const { userId } = await request.json<{ userId: string }>();
      await addTrustedUser(env.ALLOWLIST, userId);
      return Response.json({ status: 'added' });
    }

    // Admin: remove from allowlist
    if (request.method === 'DELETE' && url.pathname === '/admin/allowlist') {
      if (request.headers.get('x-admin-secret') !== env.ADMIN_SECRET) {
        return new Response('Unauthorized', { status: 401 });
      }
      const { userId } = await request.json<{ userId: string }>();
      await removeTrustedUser(env.ALLOWLIST, userId);
      return Response.json({ status: 'removed' });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

### 7. wrangler.jsonc with AI Gateway

```jsonc
{
  "name": "moderation-gateway",
  "main": "src/index.ts",
  "compatibility_date": "2025-09-01",
  "ai": {
    "binding": "AI"
    // AI Gateway is enabled by routing Workers AI through the gateway URL
    // Configure in Cloudflare dashboard: AI > AI Gateway > Create gateway
    // Then set WORKERS_AI_GATEWAY_URL secret to the gateway endpoint
  },
  "kv_namespaces": [
    { "binding": "ALLOWLIST", "id": "<allowlist-kv-id>" }
  ],
  "analytics_engine_datasets": [
    { "binding": "MODERATION_AE", "dataset": "content_moderation" }
  ],
  "vars": {
    "ADMIN_SECRET": "change-me-use-wrangler-secret-instead"
  }
}
```

### 8. AI Gateway logging configuration

Enable AI Gateway in the Cloudflare dashboard:
1. Navigate to AI > AI Gateway.
2. Create a gateway named `moderation-gateway`.
3. Enable **Log requests** and **Log responses**.
4. Set the gateway URL as the Workers AI endpoint in your binding (or via the `gateway` option on `ai.run`).

Every call to `classifyContent` will appear in the AI Gateway logs with the input, output, latency, and token counts — ready for audit.

## Implementation Details

### LlamaGuard hazard categories (S-codes)

| S-code | Category | Examples |
|---|---|---|
| S1 | hate_speech | Slurs, discrimination based on protected attributes |
| S2 | violence | Threats, graphic violence, weapons instructions |
| S3 | sexual_content | Explicit sexual material |
| S4 | self_harm | Instructions or encouragement for self-harm |
| S5 | harassment | Targeted abuse, doxxing, bullying |
| S6 | misinformation | Demonstrably false health/safety claims |
| S7 | spam | Unsolicited commercial content |

### Analytics Engine query

```sql
-- Query moderation metrics in Cloudflare Analytics Engine SQL API
SELECT
  blob4 AS decision,       -- 'safe' or 'blocked'
  blob3 AS category,
  COUNT() AS count
FROM content_moderation
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY decision, category
ORDER BY count DESC
```

### Rate limiting for high-volume traffic

For high-volume deployments, add Cloudflare Rate Limiting rules upstream of the Worker to prevent the moderation gateway from being overwhelmed by flood submissions.

## Anti-patterns

- **Classifying all content including trusted users**: adds latency and cost; allowlist bypass is essential for internal tools.
- **Blocking on low-confidence results**: LlamaGuard is binary (safe/unsafe); don't add arbitrary confidence thresholds that second-guess the model — it was trained to be decisive.
- **Logging PII in AI Gateway**: AI Gateway logs the full prompt; ensure you strip personal data from content before classification if your data residency policy requires it.
- **Skipping the allowlist for admin actions**: admin endpoints that modify content should still be protected by authentication, not just the allowlist.
- **Reacting to `category` alone without context**: some categories have legitimate uses (e.g., medical professionals discussing self-harm); consider user context in your enforcement policy.

## Gotchas

- `@cf/meta/llama-guard-3-8b` is a classification model, not a chat model — do not pass a system prompt; the model expects only a `user` message with the content to classify.
- AI Gateway adds a small amount of latency (~10-50ms); measure and account for this in your SLA.
- Analytics Engine `writeDataPoint` is fire-and-forget and does not throw on failure; wrap in try/catch only if you need to detect failures.
- KV reads add ~1-5ms; for very high throughput consider caching the allowlist in a `Map` populated at Worker startup via a `fetch` trigger.
- LlamaGuard may be updated on the Workers AI platform; re-test your S-code mapping after platform model updates.

## Verification

```bash
# Safe content
curl -X POST https://moderation-gateway.<account>.workers.dev/submit \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u1","userTier":"free","content":"I love this product, great quality!"}'
# => {"status":"accepted"}

# Harmful content (test with clearly flagged string, not real harmful text)
curl -X POST https://moderation-gateway.<account>.workers.dev/submit \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u2","userTier":"free","content":"[TEST] hate speech example"}'
# => {"error":"Content flagged by automated moderation.","category":"hate_speech"} HTTP 422

# Add to allowlist
curl -X POST https://moderation-gateway.<account>.workers.dev/admin/allowlist \
  -H 'Content-Type: application/json' \
  -H 'x-admin-secret: <secret>' \
  -d '{"userId":"internal-bot-1"}'
# => {"status":"added"}

# Confirm bypass — same user, any content now passes
curl -X POST https://moderation-gateway.<account>.workers.dev/submit \
  -H 'Content-Type: application/json' \
  -d '{"userId":"internal-bot-1","userTier":"internal","content":"any content here"}'
# => {"status":"accepted"}
```

## Related

- `workers-ai-function-calling-tools.md` — gating tool calls through safety classification
- `workers-ai-structured-output-json.md` — structured classification results
- AI Gateway docs: https://developers.cloudflare.com/ai-gateway/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/

## Sources

- Cloudflare Workers AI — LlamaGuard: https://developers.cloudflare.com/workers-ai/models/llama-guard/
- Cloudflare AI Gateway documentation: https://developers.cloudflare.com/ai-gateway/
- Meta LlamaGuard 3 model card and hazard taxonomy
- Cloudflare Analytics Engine SQL API reference
