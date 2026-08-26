# Pre-send Spam Score Preflight Checking with Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Transactional and marketing emails occasionally contain phrases, broken links, or formatting patterns that trigger spam filters, causing deliverability degradation before anyone notices. You want a Cloudflare Worker that acts as a preflight gate: it submits the rendered email HTML and headers to a spam-scoring service, blocks sends whose score exceeds a configurable threshold, and logs every check to D1 for audit and trend analysis.

## Context

SpamAssassin-compatible APIs (e.g., postmark's `/spam-check` endpoint, or a self-hosted SpamAssassin-over-HTTP sidecar) return a numeric score and triggered rules. The preflight Worker sits between your application and the outbound ESP API: your app `POST`s to the Worker, the Worker submits to the scoring service, and — if the score is safe — forwards the send request to the ESP. Scores and triggered rule names are written to D1 for dashboard queries. A KV namespace caches scores for repeated renders of the same content hash to avoid duplicate scoring round-trips.

## Content Hashing and Score Cache

```typescript
// src/hash.ts
export async function contentHash(html: string, subject: string): Promise<string> {
  const input = new TextEncoder().encode(`${subject}::${html}`);
  const digest = await crypto.subtle.digest('SHA-256', input);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// src/cache.ts
export interface Env {
  SPAM_SCORE_CACHE: KVNamespace;
  DB: D1Database;
  SPAM_CHECK_URL: string;        // e.g. https://spamcheck.postmarkapp.com/filter
  ESP_API_KEY: string;
  ESP_SEND_URL: string;
  SPAM_BLOCK_THRESHOLD: string;  // e.g. "5.0"
}

export interface SpamCheckResult {
  score: number;
  rules: string[];
  cached: boolean;
}

export async function getCachedScore(
  env: Env,
  hash: string
): Promise<SpamCheckResult | null> {
  const raw = await env.SPAM_SCORE_CACHE.get(hash);
  if (!raw) return null;
  return { ...JSON.parse(raw), cached: true };
}

export async function cacheScore(
  env: Env,
  hash: string,
  result: Omit<SpamCheckResult, 'cached'>
): Promise<void> {
  await env.SPAM_SCORE_CACHE.put(hash, JSON.stringify(result), {
    expirationTtl: 3_600, // 1 hour; content may change after fixes
  });
}
```

## Spam Score Submission and D1 Logging

```typescript
// src/checker.ts
import { contentHash, getCachedScore, cacheScore, type Env, type SpamCheckResult } from './cache';

interface PostmarkSpamResponse {
  Score: number;
  Report: string; // multiline rule output
}

function parsePostmarkRules(report: string): string[] {
  return report
    .split('\n')
    .filter((line) => /^\s*\d+\.\d+\s+/.test(line))
    .map((line) => line.trim());
}

export async function checkSpamScore(
  env: Env,
  html: string,
  subject: string
): Promise<SpamCheckResult> {
  const hash = await contentHash(html, subject);

  const cached = await getCachedScore(env, hash);
  if (cached) return cached;

  const res = await fetch(env.SPAM_CHECK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ email: `Subject: ${subject}\n\n${html}`, options: 'short' }),
  });

  if (!res.ok) throw new Error(`Spam check API error: ${res.status} ${await res.text()}`);

  const data = await res.json<PostmarkSpamResponse>();
  const result: SpamCheckResult = {
    score: data.Score,
    rules: parsePostmarkRules(data.Report),
    cached: false,
  };

  await cacheScore(env, hash, result);
  return result;
}

export async function logCheckToD1(
  env: Env,
  params: {
    hash: string; subject: string; score: number;
    rules: string[]; blocked: boolean; recipientDomain: string;
  }
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO spam_preflight_log
     (hash, subject, score, rules_json, blocked, recipient_domain, checked_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    params.hash,
    params.subject,
    params.score,
    JSON.stringify(params.rules),
    params.blocked ? 1 : 0,
    params.recipientDomain,
    new Date().toISOString()
  ).run();
}
```

## Preflight Gate Worker Fetch Handler

```typescript
// src/worker.ts
import { checkSpamScore, logCheckToD1 } from './checker';
import { contentHash } from './hash';

interface SendRequest {
  to: string;
  subject: string;
  html: string;
  from?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/send') {
      return new Response('Not found', { status: 404 });
    }

    const body = await request.json<SendRequest>();
    const { to, subject, html } = body;
    const hash = await contentHash(html, subject);
    const recipientDomain = to.split('@')[1] ?? 'unknown';
    const threshold = parseFloat(env.SPAM_BLOCK_THRESHOLD);

    let result;
    try {
      result = await checkSpamScore(env, html, subject);
    } catch (err) {
      // Fail open on scoring service outage — log and pass through
      console.error('Spam check service unavailable:', err);
      return await forwardToEsp(env, body);
    }

    const blocked = result.score >= threshold;
    await logCheckToD1(env, { hash, subject, score: result.score,
      rules: result.rules, blocked, recipientDomain });

    if (blocked) {
      return Response.json({
        ok: false,
        reason: 'spam_score_exceeded',
        score: result.score,
        threshold,
        rules: result.rules.slice(0, 10),
      }, { status: 422 });
    }

    return await forwardToEsp(env, body);
  },
} satisfies ExportedHandler<Env>;

async function forwardToEsp(env: Env, body: SendRequest): Promise<Response> {
  const res = await fetch(env.ESP_SEND_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.ESP_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
```

## Anti-patterns

- Blocking sends on scoring service timeout — fail open (log and forward) to avoid taking down transactional mail when the scoring API is unavailable.
- Using the same threshold for transactional and marketing email — transactional mail should use a looser threshold (e.g., 7.0) than marketing (e.g., 3.5).
- Not caching scores — the same template body is sent to thousands of recipients; re-scoring each send wastes API quota and adds latency.

## Gotchas

- SpamAssassin scores vary by version; a rule set upgrade at the scoring service can cause previously passing content to suddenly exceed the threshold — pin the service version or set threshold headroom of at least 1.0 above your ISP's typical filter level.
- The Postmark `/filter` endpoint scores raw RFC 2822 messages, not just HTML bodies — include `Subject:` and `From:` headers in the submitted text for accurate scoring.

## Verification

```bash
# Check a known-clean message
curl -X POST https://preflight.example.com/send \
  -H 'Content-Type: application/json' \
  -d '{"to":"user@example.com","subject":"Your receipt","html":"<p>Thanks for your order.</p>","from":"noreply@example.com"}'
# Expect: 200 with ESP response

# Check a message designed to score high
curl -X POST https://preflight.example.com/send \
  -H 'Content-Type: application/json' \
  -d '{"to":"user@example.com","subject":"FREE CASH WIN PRIZE NOW!!!","html":"<p>Click here to claim your FREE money</p>"}'
# Expect: 422 spam_score_exceeded

# Query D1 for recent blocked sends
wrangler d1 execute EMAIL_DB \
  --command "SELECT subject, score, rules_json, checked_at FROM spam_preflight_log WHERE blocked=1 ORDER BY checked_at DESC LIMIT 10"
```

## Related

- `email/email-spam-triggers.md`
- `email/spam-assassin-scoring.md`
- `email/email-content-guidelines.md`
- `email/email-deliverability-fundamentals.md`

## Sources

- https://spamcheck.postmarkapp.com/
- https://developers.cloudflare.com/d1/get-started/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://spamassassin.apache.org/doc/Mail_SpamAssassin_Conf.html
