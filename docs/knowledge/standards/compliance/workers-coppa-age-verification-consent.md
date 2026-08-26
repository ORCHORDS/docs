# COPPA Compliance: Age-Gate, Parental Consent Flow, and Under-13 Data Blocking in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

COPPA (Children's Online Privacy Protection Act, 15 U.S.C. §§ 6501–6506) prohibits collecting personal information from children under 13 without verifiable parental consent. When your service runs on Cloudflare Workers you can enforce the age gate at the edge, issue a consent token via MailChannels email, store the verified consent record in D1, and block any data collection endpoint for users whose age is unverified or under-13 — all without running a separate origin server.

## Context

- Runtime: Cloudflare Workers (TypeScript)
- Consent records: Cloudflare D1
- Pending consent tokens: Cloudflare KV (TTL-based expiry)
- Email delivery: MailChannels Send API (available free on Workers)
- COPPA rules covered: §312.5 (verifiable parental consent), §312.3 (prohibition on conditioning)

---

## Section 1: D1 Schema

```sql
-- migrations/0005_coppa.sql
CREATE TABLE IF NOT EXISTS coppa_consent (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id        TEXT NOT NULL UNIQUE,
  dob            TEXT NOT NULL,             -- ISO date, not exposed in API responses
  is_minor       INTEGER NOT NULL,          -- 1 = under 13
  parent_email   TEXT,                      -- required if is_minor = 1
  consent_given  INTEGER NOT NULL DEFAULT 0,
  consent_ts     TEXT,
  consent_method TEXT,                      -- 'EMAIL_CONFIRM'
  created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_coppa_user ON coppa_consent(user_id);
```

```bash
npx wrangler d1 migrations apply COPPA_DB --remote
```

---

## Section 2: Age-Gate Endpoint

```typescript
// src/routes/ageGate.ts
import { Env } from '../types';
import { sendParentalConsentEmail } from '../coppa/mailer';
import { storeConsentToken }        from '../coppa/tokenStore';

function calculateAge(dob: string): number {
  const birth = new Date(dob);
  const now   = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  const monthDiff = now.getMonth() - birth.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && now.getDate() < birth.getDate())) {
    age--;
  }
  return age;
}

export async function handleAgeGate(
  req: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  let body: { userId: string; dob: string; parentEmail?: string };
  try {
    body = await req.json();
  } catch {
    return new Response('Bad Request', { status: 400 });
  }

  const { userId, dob, parentEmail } = body;
  if (!userId || !dob) {
    return new Response('userId and dob are required', { status: 400 });
  }

  const age     = calculateAge(dob);
  const isMinor = age < 13 ? 1 : 0;

  if (isMinor && !parentEmail) {
    return Response.json(
      { error: 'COPPA_PARENT_EMAIL_REQUIRED', message: 'Parent email required for users under 13' },
      { status: 422 }
    );
  }

  // Record the registration attempt (no PII collection yet for minors)
  await env.COPPA_DB
    .prepare(
      `INSERT INTO coppa_consent (user_id, dob, is_minor, parent_email)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(user_id) DO UPDATE SET dob=excluded.dob, is_minor=excluded.is_minor, parent_email=excluded.parent_email`
    )
    .bind(userId, dob, isMinor, parentEmail ?? null)
    .run();

  if (isMinor) {
    // Generate and email consent token to parent
    const token = crypto.randomUUID();
    ctx.waitUntil(
      Promise.all([
        storeConsentToken(env, token, userId),
        sendParentalConsentEmail(env, parentEmail!, userId, token),
      ])
    );
    return Response.json({ status: 'PENDING_PARENTAL_CONSENT' }, { status: 202 });
  }

  // Adult — mark consent given immediately
  await env.COPPA_DB
    .prepare(
      `UPDATE coppa_consent
       SET consent_given=1, consent_ts=strftime('%Y-%m-%dT%H:%M:%SZ','now'), consent_method='SELF'
       WHERE user_id=?`
    )
    .bind(userId)
    .run();

  return Response.json({ status: 'CONSENT_GRANTED' });
}
```

---

## Section 3: KV Consent Token Store

```typescript
// src/coppa/tokenStore.ts
import { Env } from '../types';

const TOKEN_PREFIX  = 'coppa:token:';
const TOKEN_TTL_SEC = 72 * 60 * 60;  // 72-hour window for parent to respond

export async function storeConsentToken(
  env: Env,
  token: string,
  userId: string
): Promise<void> {
  await env.COPPA_KV.put(
    `${TOKEN_PREFIX}${token}`,
    userId,
    { expirationTtl: TOKEN_TTL_SEC }
  );
}

export async function consumeConsentToken(
  env: Env,
  token: string
): Promise<string | null> {
  const userId = await env.COPPA_KV.get(`${TOKEN_PREFIX}${token}`);
  if (userId) {
    await env.COPPA_KV.delete(`${TOKEN_PREFIX}${token}`);
  }
  return userId;
}
```

---

## Section 4: MailChannels Parental Consent Email

```typescript
// src/coppa/mailer.ts
import { Env } from '../types';

export async function sendParentalConsentEmail(
  env: Env,
  parentEmail: string,
  userId: string,
  token: string
): Promise<void> {
  const consentUrl = `${env.APP_BASE_URL}/coppa/confirm?token=${token}`;

  const emailBody = `
Dear Parent or Guardian,

Your child (user ID: ${userId}) has attempted to register on ${env.APP_NAME}.

Because they are under 13, we require your consent before collecting any personal
information, as required by the Children's Online Privacy Protection Act (COPPA).

If you approve, please click the link below within 72 hours:
${consentUrl}

If you do not approve, no data will be collected and the registration will be deleted.

This link expires in 72 hours.

-- ${env.APP_NAME} Privacy Team
`;

  const response = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: parentEmail }] }],
      from: { email: env.FROM_EMAIL, name: `${env.APP_NAME} Privacy` },
      subject: `Parental Consent Required — ${env.APP_NAME}`,
      content: [{ type: 'text/plain', value: emailBody }],
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`MailChannels error ${response.status}: ${text}`);
  }
}
```

---

## Section 5: Consent Confirmation Endpoint and Data-Collection Guard

```typescript
// src/routes/coppaConfirm.ts
import { Env }                 from '../types';
import { consumeConsentToken } from '../coppa/tokenStore';

export async function handleCoppaConfirm(
  req: Request,
  env: Env
): Promise<Response> {
  const token = new URL(req.url).searchParams.get('token');
  if (!token) return new Response('Missing token', { status: 400 });

  const userId = await consumeConsentToken(env, token);
  if (!userId) {
    return new Response('Token expired or invalid', { status: 410 });
  }

  await env.COPPA_DB
    .prepare(
      `UPDATE coppa_consent
       SET consent_given=1, consent_ts=strftime('%Y-%m-%dT%H:%M:%SZ','now'), consent_method='EMAIL_CONFIRM'
       WHERE user_id=?`
    )
    .bind(userId)
    .run();

  return new Response('Consent recorded. Thank you.', { status: 200 });
}

// Middleware: block data collection for unconsented minors
export async function requireCoppaConsent(
  env: Env,
  userId: string
): Promise<Response | null> {
  const row = await env.COPPA_DB
    .prepare(
      'SELECT is_minor, consent_given FROM coppa_consent WHERE user_id = ?'
    )
    .bind(userId)
    .first<{ is_minor: number; consent_given: number }>();

  if (!row) {
    // Unknown user — block as a safety default
    return new Response('Age verification required', { status: 451 });
  }

  if (row.is_minor && !row.consent_given) {
    return new Response('Parental consent required', { status: 451 });
  }

  return null;  // proceed
}
```

---

## Anti-patterns

- Accepting the user's self-reported age without server-side calculation — always compute age from DOB on the server.
- Collecting any personal information before parental consent is confirmed for under-13 users — even a username counts under COPPA.
- Storing consent tokens in D1 — KV with a TTL is safer; expired tokens are automatically deleted without a sweep cron.
- Sending the consent URL in the child's email rather than the parent's — COPPA requires the consent mechanism to go to the parent.
- Logging the child's DOB in plaintext in console output — that's PII; omit or hash it.

## Gotchas

- `new Date(dob)` in V8 parses ISO dates as UTC midnight, so a child born on `2013-01-01` might appear one day older in certain timezones. Use explicit year/month/day extraction to avoid off-by-one errors.
- MailChannels requires SPF/DKIM for reliable delivery; configure DNS records and use `X-MC-SpamScore` response headers to debug.
- COPPA also applies to third-party SDKs you embed — audit all analytics and ad pixels if you later add them.
- HTTP 451 (Unavailable For Legal Reasons) is the appropriate status code for COPPA blocks.
- KV `expirationTtl` minimum is 60 seconds; your 72-hour token is well within limits.

---

## Verification

```bash
# Test adult registration (no consent email expected)
curl -X POST https://api.example.com/age-gate \
  -H 'Content-Type: application/json' \
  -d '{"userId":"U001","dob":"1990-05-15"}'
# Expected: {"status":"CONSENT_GRANTED"}

# Test minor registration (consent email should be sent)
curl -X POST https://api.example.com/age-gate \
  -H 'Content-Type: application/json' \
  -d '{"userId":"U002","dob":"2015-03-20","parentEmail":"parent@example.com"}'
# Expected: {"status":"PENDING_PARENTAL_CONSENT"}

# Simulate parent clicking link (replace TOKEN with value from KV)
npx wrangler kv key list --binding=COPPA_KV --prefix='coppa:token:' --remote
curl "https://api.example.com/coppa/confirm?token=<TOKEN>"

# Verify consent record
npx wrangler d1 execute COPPA_DB --remote \
  --command "SELECT user_id, is_minor, consent_given, consent_method FROM coppa_consent;"

# Try accessing a protected endpoint before consent
curl -H 'X-User-Id: U002' https://api.example.com/api/profile
# Expected: 451 Parental consent required
```

---

## Related

- `documentation/docs/policies/compliance/workers-ferpa-student-data-access-d1.md`
- `documentation/docs/policies/compliance/workers-iso-27001-access-log-d1.md`
- `documentation/workers/mailchannels-transactional-email.md`

## Sources

- https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa (FTC COPPA Rule)
- https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-312 (16 CFR Part 312)
- https://blog.cloudflare.com/sending-email-from-workers-with-mailchannels/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
