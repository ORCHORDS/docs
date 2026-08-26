# Static Site Contact Form Backend with Cloudflare Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You have a static site (served from R2, Workers Assets, or any CDN) with a contact form. You need form submissions to be validated, spam-filtered, rate-limited, stored durably, and optionally to trigger an email — all without running a traditional server, and without a third-party form service that locks you into their data model.

## Context

Cloudflare Workers pairs naturally with:

- **D1** — a serverless SQLite database at the edge for durable form storage.
- **KV** — for per-IP rate-limit counters (ephemeral, TTL-based).
- **MailChannels** — a Cloudflare-partnered transactional email API callable from Workers without an API key (when the Worker is deployed on Cloudflare infrastructure).

The static site's form posts to a Worker route. The Worker is the sole backend.

## Solution

### 1. D1 schema

```sql
-- migrations/0001_create_submissions.sql
CREATE TABLE IF NOT EXISTS submissions (
  id          TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  created_at  INTEGER NOT NULL,   -- Unix epoch seconds
  name        TEXT    NOT NULL,
  email       TEXT    NOT NULL,
  message     TEXT    NOT NULL,
  ip          TEXT    NOT NULL,
  user_agent  TEXT,
  spam_score  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_submissions_email ON submissions(email);
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions(created_at);
```

Apply with: `wrangler d1 migrations apply FORM_DB`

### 2. CORS preflight handler

```typescript
// worker/cors.ts
const ALLOWED_ORIGINS = [
  'https://example.com',
  'https://www.example.com',
];

export function corsHeaders(request: Request): Record<string, string> {
  const origin = request.headers.get('Origin') ?? '';
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin':  allowed,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age':       '86400',
  };
}

export function handlePreflight(request: Request): Response | null {
  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders(request) });
  }
  return null;
}
```

### 3. Form validation

```typescript
// worker/validate.ts
export interface FormData {
  name:     string;
  email:    string;
  message:  string;
  honeypot: string; // must be empty
}

export interface ValidationResult {
  ok:     boolean;
  errors: Record<string, string>;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateForm(data: FormData): ValidationResult {
  const errors: Record<string, string> = {};

  if (!data.name?.trim()) {
    errors['name'] = 'Name is required.';
  } else if (data.name.length > 120) {
    errors['name'] = 'Name must be 120 characters or fewer.';
  }

  if (!data.email?.trim()) {
    errors['email'] = 'Email is required.';
  } else if (!EMAIL_RE.test(data.email)) {
    errors['email'] = 'Please enter a valid email address.';
  }

  if (!data.message?.trim()) {
    errors['message'] = 'Message is required.';
  } else if (data.message.length < 10) {
    errors['message'] = 'Message must be at least 10 characters.';
  } else if (data.message.length > 5000) {
    errors['message'] = 'Message must be 5000 characters or fewer.';
  }

  return { ok: Object.keys(errors).length === 0, errors };
}

/** Returns a spam score 0–100. Submission blocked if >= 50. */
export function spamScore(data: FormData): number {
  let score = 0;

  // Classic honeypot: bot-filled hidden field
  if (data.honeypot) score += 100;

  // Link-heavy message
  const links = (data.message.match(/https?:\/\//g) ?? []).length;
  if (links > 2) score += links * 10;

  // All-caps name
  if (data.name === data.name.toUpperCase() && data.name.length > 3) score += 20;

  return Math.min(score, 100);
}
```

### 4. IP-based rate limiting via KV

```typescript
// worker/ratelimit.ts
import { Env } from './types';

const MAX_SUBMISSIONS = 5;
const WINDOW_SECONDS  = 3600; // 1 hour

export interface RateLimitResult {
  allowed:   boolean;
  remaining: number;
  resetAt:   number; // Unix epoch
}

export async function checkRateLimit(
  ip: string,
  env: Env
): Promise<RateLimitResult> {
  const key   = `rl:form:${ip}`;
  const now   = Math.floor(Date.now() / 1000);
  const resetAt = now + WINDOW_SECONDS;

  const raw = await env.KV.get<{ count: number; reset: number }>(key, 'json');

  if (!raw || raw.reset < now) {
    // First submission in the window or window expired
    await env.KV.put(key, JSON.stringify({ count: 1, reset: resetAt }), {
      expirationTtl: WINDOW_SECONDS,
    });
    return { allowed: true, remaining: MAX_SUBMISSIONS - 1, resetAt };
  }

  if (raw.count >= MAX_SUBMISSIONS) {
    return { allowed: false, remaining: 0, resetAt: raw.reset };
  }

  await env.KV.put(key, JSON.stringify({ count: raw.count + 1, reset: raw.reset }), {
    expirationTtl: raw.reset - now,
  });

  return {
    allowed:   true,
    remaining: MAX_SUBMISSIONS - raw.count - 1,
    resetAt:   raw.reset,
  };
}
```

### 5. D1 storage

```typescript
// worker/store.ts
import { Env } from './types';
import { FormData } from './validate';

export async function storeSubmission(
  data: FormData,
  ip: string,
  userAgent: string,
  spamScore: number,
  env: Env
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);

  const result = await env.DB.prepare(
    `INSERT INTO submissions (created_at, name, email, message, ip, user_agent, spam_score)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     RETURNING id`
  )
    .bind(now, data.name.trim(), data.email.trim(), data.message.trim(), ip, userAgent, spamScore)
    .first<{ id: string }>();

  if (!result) throw new Error('D1 insert returned no id');
  return result.id;
}
```

### 6. MailChannels email notification

```typescript
// worker/email.ts
import { Env } from './types';

export async function sendNotification(
  submissionId: string,
  name: string,
  email: string,
  message: string,
  env: Env
): Promise<void> {
  const body = JSON.stringify({
    personalizations: [{
      to: [{ email: env.NOTIFY_EMAIL }],
    }],
    from: { email: env.FROM_EMAIL, name: 'Contact Form' },
    subject: `New contact form submission [${submissionId}]`,
    content: [{
      type: 'text/plain',
      value: `From: ${name} <${email}>\n\n${message}`,
    }],
  });

  const response = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });

  if (!response.ok) {
    // Non-fatal — log but don't fail the user's submission
    console.error(`MailChannels error ${response.status}:`, await response.text());
  }
}
```

### 7. Main Worker entry point

```typescript
// worker/index.ts
import { Env } from './types';
import { corsHeaders, handlePreflight } from './cors';
import { validateForm, spamScore, FormData } from './validate';
import { checkRateLimit } from './ratelimit';
import { storeSubmission } from './store';
import { sendNotification } from './email';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Route: only POST /contact
    const url = new URL(request.url);
    if (url.pathname !== '/contact') {
      return new Response('Not found', { status: 404 });
    }

    // CORS preflight
    const preflight = handlePreflight(request);
    if (preflight) return preflight;

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
    const ua = request.headers.get('User-Agent') ?? '';

    // Rate limiting
    const rl = await checkRateLimit(ip, env);
    if (!rl.allowed) {
      return json({ error: 'Too many submissions. Please try again later.' }, 429,
        { ...corsHeaders(request), 'Retry-After': String(rl.resetAt - Math.floor(Date.now() / 1000)) }
      );
    }

    // Parse body
    let data: FormData;
    try {
      const ct = request.headers.get('Content-Type') ?? '';
      if (ct.includes('application/json')) {
        data = await request.json() as FormData;
      } else {
        const fd = await request.formData();
        data = {
          name:     fd.get('name')     as string ?? '',
          email:    fd.get('email')    as string ?? '',
          message:  fd.get('message') as string ?? '',
          honeypot: fd.get('website') as string ?? '', // hidden field labelled 'website'
        };
      }
    } catch {
      return json({ error: 'Invalid request body.' }, 400, corsHeaders(request));
    }

    // Honeypot / spam check (fast-fail before validation)
    const score = spamScore(data);
    if (score >= 50) {
      // Silently accept to avoid tipping off bots
      return json({ success: true }, 200, corsHeaders(request));
    }

    // Validation
    const validation = validateForm(data);
    if (!validation.ok) {
      return json({ errors: validation.errors }, 422, corsHeaders(request));
    }

    // Store in D1
    const id = await storeSubmission(data, ip, ua, score, env);

    // Email notification (non-blocking)
    void sendNotification(id, data.name, data.email, data.message, env);

    return json({ success: true, id }, 201, corsHeaders(request));
  },
};

function json(
  body: unknown,
  status: number,
  extraHeaders: Record<string, string> = {}
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...extraHeaders },
  });
}
```

### 8. Types and wrangler.toml

```typescript
// worker/types.ts
export interface Env {
  KV:           KVNamespace;
  DB:           D1Database;
  NOTIFY_EMAIL: string;
  FROM_EMAIL:   string;
}
```

```toml
# wrangler.toml
name = "contact-form-worker"
main = "worker/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding  = "DB"
database_name = "contact-form"
database_id   = "<your-d1-id>"

[[kv_namespaces]]
binding = "KV"
id      = "<your-kv-id>"

[vars]
NOTIFY_EMAIL = "you@example.com"
FROM_EMAIL   = "noreply@example.com"
```

## Implementation Details

- **`waitUntil`** is not used for the email call above; it is fired with `void` which is acceptable inside a Worker fetch handler because the Worker keeps running until the event loop drains. For guaranteed delivery use `ctx.waitUntil(sendNotification(...))` in a handler that receives `ctx: ExecutionContext`.
- **D1 `RETURNING id`** avoids a second `SELECT last_insert_rowid()` round-trip.
- **Rate limit precision**: KV is eventually consistent across regions. A burst of near-simultaneous submissions from the same IP may briefly exceed the limit. For stricter enforcement use Durable Objects.
- **Honeypot field** must have a human-meaningful label (`website`, `company`) so bots autofill it, but be visually hidden via CSS (`position:absolute; left:-9999px`).

## Anti-patterns

- **Validating only on the client** — always re-validate on the Worker; browser validation is bypassed by cURL.
- **Storing the raw IP as a sensitive identifier** — hash it with a daily rotating key if GDPR applies to your deployment.
- **Blocking the response on email delivery** — MailChannels can occasionally be slow; fire-and-forget keeps p99 latency predictable.
- **Allowing wildcard CORS (`*`)** — locks down the origin to your known domains to prevent cross-origin form abuse.

## Gotchas

- `request.formData()` fails if `Content-Type` is not `multipart/form-data` or `application/x-www-form-urlencoded`. Detect and branch.
- MailChannels delivery from Workers requires your sending domain to have an SPF record including `include:relay.mailchannels.net` and optionally a `_mailchannels` TXT record for domain lockdown.
- D1 is in GA but has a 10 MB per-row and 2 GB per-database limit. Log large `message` fields carefully.
- `CF-Connecting-IP` is populated by Cloudflare's proxy; if you run `wrangler dev` locally it will be absent — fall back to `127.0.0.1`.

## Verification

1. `wrangler dev` — post via `curl -X POST http://localhost:8787/contact -H 'Content-Type: application/json' -d '{"name":"Test","email":"t@t.com","message":"hello world","honeypot":""}'` — expect `{"success":true}`.
2. Fill the honeypot — expect `{"success":true}` with no D1 row inserted.
3. Submit 6 times from the same IP — the 6th should return HTTP 429.
4. Query D1 directly: `wrangler d1 execute FORM_DB --command 'SELECT * FROM submissions ORDER BY created_at DESC LIMIT 5;'`.
5. Send a submission with an invalid email — expect HTTP 422 with an `errors` object.

## Related

- `workers-edge-personalisation-htmlrewriter.md` — using KV in Workers
- `workers-dark-mode-cookie-edge.md` — cookie handling in Workers

## Sources

- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- Cloudflare KV API: https://developers.cloudflare.com/kv/api/
- MailChannels Workers integration: https://blog.cloudflare.com/sending-email-from-workers-with-mailchannels/
- OWASP contact form security: https://owasp.org/www-community/attacks/Form_Hijacking
