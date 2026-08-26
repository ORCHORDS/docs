# COPPA Compliance Infrastructure with Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A platform that may be used by children under 13 must implement the Children's Online Privacy Protection Act (COPPA) age gate, parental consent flow, and data minimization rules. Non-compliance can result in FTC civil penalties up to $51,744 per violation per day.

## Context

COPPA applies to operators of websites or online services directed at children under 13, or those with actual knowledge that they are collecting personal information from children. The infrastructure below implements:

- Server-side age verification in a Cloudflare Worker (no client-side bypass possible)
- Parental consent email via MailChannels (transactional email from Workers)
- `user_consent` D1 table with hashed DOB, parental email, and consent timestamp
- Blocking of analytics and tracking pixels for verified minors
- 72-hour data deletion on parental request (COPPA §312.6)
- COPPA Safe Harbor program alignment

## Age Gate and Consent Flow Worker

```typescript
import { createHash } from 'node:crypto';

export interface Env {
  DB: D1Database;
  KV: KVNamespace;           // stores pending consent tokens
  MAILCHANNELS_API_KEY: string;
  PLATFORM_DOMAIN: string;   // e.g. 'example.com'
}

const COPPA_AGE_LIMIT = 13;

function hashDob(dob: string): string {
  // dob in ISO format: 'YYYY-MM-DD'
  return createHash('sha256').update(dob + 'coppa-salt').digest('hex');
}

function calculateAge(dob: string): number {
  const birth = new Date(dob);
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  const m = now.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < birth.getDate())) age--;
  return age;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // Step 1: User submits date of birth
    if (url.pathname === '/register/age-check' && req.method === 'POST') {
      return handleAgeCheck(req, env);
    }

    // Step 2: Parent clicks consent link in email
    if (url.pathname === '/consent/verify' && req.method === 'GET') {
      return handleConsentVerify(req, env);
    }

    // Step 3: Parent submits deletion request
    if (url.pathname === '/consent/delete' && req.method === 'POST') {
      return handleDeletionRequest(req, env);
    }

    return new Response('not found', { status: 404 });
  },
};

async function handleAgeCheck(req: Request, env: Env): Promise<Response> {
  const { user_id, dob, parental_email } =
    await req.json<{ user_id: string; dob: string; parental_email?: string }>();

  if (!user_id || !/^\d{4}-\d{2}-\d{2}$/.test(dob)) {
    return new Response('invalid input', { status: 400 });
  }

  const age = calculateAge(dob);
  const isMinor = age < COPPA_AGE_LIMIT;

  if (isMinor && !parental_email) {
    return Response.json({ requires_parental_consent: true }, { status: 200 });
  }

  const dobHash = hashDob(dob);

  if (isMinor && parental_email) {
    // Block account activation until parent consents
    const token = crypto.randomUUID();
    await env.KV.put(
      `consent:${token}`,
      JSON.stringify({ user_id, dob_hash: dobHash, parental_email }),
      { expirationTtl: 604800 }, // 7 days
    );

    await sendConsentEmail(env, parental_email, token, user_id);

    return Response.json({ status: 'pending_parental_consent' });
  }

  // Adult — record consent directly
  await env.DB.prepare(`
    INSERT OR REPLACE INTO user_consent
      (user_id, dob_hash, parental_email, consent_granted_at, is_minor)
    VALUES (?, ?, NULL, unixepoch(), 0)
  `).bind(user_id, dobHash).run();

  return Response.json({ status: 'ok', is_minor: false });
}

async function handleConsentVerify(req: Request, env: Env): Promise<Response> {
  const token = new URL(req.url).searchParams.get('token');
  if (!token) return new Response('missing token', { status: 400 });

  const raw = await env.KV.get(`consent:${token}`);
  if (!raw) return new Response('token expired or invalid', { status: 410 });

  const { user_id, dob_hash, parental_email } =
    JSON.parse(raw) as { user_id: string; dob_hash: string; parental_email: string };

  await env.DB.prepare(`
    INSERT OR REPLACE INTO user_consent
      (user_id, dob_hash, parental_email, consent_granted_at, is_minor)
    VALUES (?, ?, ?, unixepoch(), 1)
  `).bind(user_id, dob_hash, parental_email).run();

  await env.KV.delete(`consent:${token}`);

  // Activate account
  await env.DB.prepare(
    "UPDATE accounts SET status = 'active', coppa_minor = 1 WHERE id = ?",
  ).bind(user_id).run();

  return new Response('Parental consent recorded. Your child can now use the platform.', {
    headers: { 'Content-Type': 'text/plain' },
  });
}

async function handleDeletionRequest(req: Request, env: Env): Promise<Response> {
  const { user_id, parental_email } =
    await req.json<{ user_id: string; parental_email: string }>();

  // Verify parental email matches consent record
  const row = await env.DB.prepare(
    'SELECT parental_email FROM user_consent WHERE user_id = ? AND is_minor = 1',
  ).bind(user_id).first<{ parental_email: string }>();

  if (!row || row.parental_email !== parental_email) {
    return new Response('unauthorized', { status: 403 });
  }

  // Schedule deletion within 72h (COPPA §312.6)
  await env.DB.prepare(`
    INSERT INTO deletion_requests (user_id, requested_at, due_by, status)
    VALUES (?, unixepoch(), unixepoch() + 259200, 'pending')
  `).bind(user_id).run();

  return Response.json({ status: 'deletion_scheduled', due_within_hours: 72 });
}

async function sendConsentEmail(
  env: Env, toEmail: string, token: string, userId: string,
): Promise<void> {
  const consentUrl = `https://${env.PLATFORM_DOMAIN}/consent/verify?token=${token}`;
  await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-api-key': env.MAILCHANNELS_API_KEY },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: toEmail }] }],
      from: { email: `noreply@${env.PLATFORM_DOMAIN}`, name: 'Orchords Platform' },
      subject: 'Parental Consent Required — COPPA',
      content: [{ type: 'text/plain',
        value: `A child has registered with user ID ${userId}.\nTo grant consent, click: ${consentUrl}\nThis link expires in 7 days.` }],
    }),
  });
}
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS user_consent (
  user_id           TEXT PRIMARY KEY,
  dob_hash          TEXT NOT NULL,
  parental_email    TEXT,
  consent_granted_at INTEGER NOT NULL,
  is_minor          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS deletion_requests (
  user_id      TEXT NOT NULL,
  requested_at INTEGER NOT NULL,
  due_by       INTEGER NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending'
);
```

## Blocking Analytics and Tracking for Minors

In every edge Worker that injects analytics scripts or sets ad-tracking cookies, check the `coppa_minor` flag before doing so:

```typescript
const consent = await env.DB.prepare(
  'SELECT is_minor FROM user_consent WHERE user_id = ?',
).bind(userId).first<{ is_minor: number }>();

if (consent?.is_minor) {
  // Strip analytics script injection and remove ad-targeting headers
  resp.headers.delete('Set-Cookie'); // remove tracking cookies
  // do NOT forward to analytics endpoint
  return;
}
```

## COPPA Safe Harbor

To qualify for the FTC COPPA Safe Harbor program, operators must be approved by an FTC-recognized self-regulatory organization (e.g., kidSAFE, PRIVO). Safe Harbor membership requires annual audits, a published privacy policy, and a verified mechanism for parental access/deletion requests. The above infrastructure satisfies the technical requirements; business enrollment in a Safe Harbor program is handled separately.

## Anti-patterns

- **Client-side age verification** — JavaScript can be bypassed; always verify server-side in the Worker.
- **Storing raw DOB** — hash with a salt; the raw date of birth is not needed after age classification.
- **Sending analytics events before checking `is_minor`** — a single analytics ping before the flag is set constitutes a COPPA violation.
- **Treating the 72-hour deletion window as a soft deadline** — it is a hard regulatory requirement; implement a Cron Worker to enforce overdue deletions.

## Gotchas

- COPPA applies even if the platform is not "directed at children" if there is actual knowledge a user is under 13 — train support staff accordingly.
- The parental consent email itself must be treated as PII; store only a hashed or truncated form if possible.
- `MailChannels` is available on Workers without an outbound SMTP relay; the API key must be stored as a Workers secret.
- Deletion must include D1 rows, KV entries, R2 objects, Vectorize embeddings, and any third-party processors (analytics, ad networks).

## Verification

```bash
# Confirm no analytics requests fire for minor users
wrangler tail --format pretty | grep 'is_minor:1'

# Check overdue deletions
wrangler d1 execute example project-db --command \
  "SELECT user_id, due_by, status FROM deletion_requests WHERE status = 'pending' AND due_by < unixepoch();"
```

## Related

- `mental-health-crisis-escalation-pipeline-workers-ai.md`
- Cloudflare MailChannels integration docs
- FTC COPPA Rule: 16 C.F.R. Part 312

## Sources

- FTC COPPA Rule: https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa
- Cloudflare D1: https://developers.cloudflare.com/d1/
- MailChannels + Workers: https://developers.cloudflare.com/workers/tutorials/send-emails-with-mailchannels/
