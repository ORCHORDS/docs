# Email Deliverability with MailChannels + Workers — Lessons Learned

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

After launching a transactional email feature backed by MailChannels via Cloudflare Workers, 18 %
of welcome emails were silently dropped over the first two weeks. Our DMARC aggregate reports later
showed that 31 % of mail from one of our sub-domains was failing DMARC alignment. A bulk
re-engagement campaign we ran in month 3 triggered a Gmail reputation drop that took six weeks to
recover from. None of these failures showed up in our application logs.

---

## Context

Cloudflare Workers can send email via the MailChannels HTTP API without requiring an SMTP server.
The integration is elegant for transactional use cases but the email authentication chain
(SPF → DKIM → DMARC) is easy to misconfigure when the sending domain is not fully under your
control.

### How the auth chain works

```
Sender domain: mail.example.com
│
├─ SPF   — which IPs/services are allowed to send as mail.example.com?
├─ DKIM  — does the email body carry a signature verifiable by the domain's public key?
└─ DMARC — what should receivers do when SPF or DKIM fail? Where do I send reports?
```

MailChannels sends from its own IP ranges. If your SPF record does not include MailChannels, or
your DKIM key is wrong, receivers will see alignment failures.

---

## Solution

### 1. Correct DNS configuration

```dns
; SPF — include MailChannels alongside any other senders
mail.example.com.  TXT  "v=spf1 include:relay.mailchannels.net ~all"

; DKIM — add the MailChannels public key as a CNAME
mailchannels._domainkey.mail.example.com.  CNAME  mailchannels._domainkey.mailchannels.net.

; DMARC — start in monitor mode; tighten after reviewing reports
_dmarc.mail.example.com.  TXT  "v=DMARC1; p=none; rua=mailto:dmarc@example.com; ruf=mailto:dmarc-fail@example.com; adkim=s; aspf=s"
```

Once your DMARC aggregate reports show > 98 % alignment for 30 days, move to `p=quarantine`
then `p=reject`.

### 2. Sending transactional email from Workers

```typescript
import type { Env } from './types';

interface MailChannelsPayload {
  personalizations: Array<{
    to: Array<{ email: string; name?: string }>;
    dkim_domain: string;
    dkim_selector: string;
    dkim_private_key: string;
  }>;
  from: { email: string; name: string };
  subject: string;
  content: Array<{ type: string; value: string }>;
}

export async function sendTransactionalEmail(
  to: { email: string; name: string },
  subject: string,
  html: string,
  env: Env
): Promise<void> {
  const payload: MailChannelsPayload = {
    personalizations: [
      {
        to: [to],
        dkim_domain: 'mail.example.com',
        dkim_selector: 'mailchannels',
        dkim_private_key: env.DKIM_PRIVATE_KEY,  // stored as Workers Secret
      },
    ],
    from: { email: 'no-reply@mail.example.com', name: 'Orchords' },
    subject,
    content: [{ type: 'text/html; charset=utf-8', value: html }],
  };

  const resp = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const body = await resp.text();
    throw new EmailSendError(`MailChannels error ${resp.status}: ${body}`, resp.status);
  }
}

export class EmailSendError extends Error {
  constructor(message: string, public readonly statusCode: number) {
    super(message);
    this.name = 'EmailSendError';
  }
}
```

### 3. Bounce and complaint handling

MailChannels delivers bounce and complaint webhooks. Wire them to a Worker endpoint:

```typescript
interface BounceEvent {
  event: 'bounce' | 'spam_report' | 'unsubscribe';
  email: string;
  reason?: string;
  timestamp: number;
}

export async function handleMailChannelsWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  // Verify the webhook signature
  const sig = request.headers.get('X-MailChannels-Signature');
  if (!sig || !verifyWebhookSignature(sig, await request.clone().text(), env.MC_WEBHOOK_SECRET)) {
    return new Response('Unauthorized', { status: 401 });
  }

  const events = (await request.json()) as BounceEvent[];

  for (const event of events) {
    if (event.event === 'bounce' || event.event === 'spam_report') {
      // Suppress future sends to this address
      await env.DB.prepare(
        'INSERT OR REPLACE INTO email_suppressions (email, reason, suppressed_at) VALUES (?, ?, ?)'
      )
        .bind(event.email, event.event, new Date(event.timestamp * 1000).toISOString())
        .run();
    }
  }

  return new Response('ok');
}

function verifyWebhookSignature(
  signature: string,
  body: string,
  secret: string
): boolean {
  // HMAC-SHA256 verification — implementation depends on your secret format
  // Use crypto.subtle in Workers
  return signature.length > 0 && secret.length > 0; // placeholder
}
```

### 4. Checking the suppression list before every send

```typescript
export async function sendIfNotSuppressed(
  to: { email: string; name: string },
  subject: string,
  html: string,
  env: Env
): Promise<'sent' | 'suppressed'> {
  const suppressed = await env.DB.prepare(
    'SELECT 1 FROM email_suppressions WHERE email = ? LIMIT 1'
  )
    .bind(to.email)
    .first();

  if (suppressed) {
    console.warn(`Skipping suppressed address: ${to.email}`);
    return 'suppressed';
  }

  await sendTransactionalEmail(to, subject, html, env);
  return 'sent';
}
```

---

## Implementation Details

### SPF flattening and the 10-lookup limit

SPF evaluation is limited to **10 DNS lookups**. Every `include:` counts as one lookup (and the
included record can itself trigger more). If you add enough includes you silently exceed the limit
and SPF evaluation returns `permerror`, which DMARC treats as a failure.

Audit your SPF record:

```bash
# Count effective SPF lookups
npx spf-check mail.example.com
# or use: https://dmarcian.com/spf-survey/
```

Fix: consolidate IPs into a single CIDR block, remove stale include directives, or use SPF
flattening (some DNS providers offer automatic flattening, but it requires regular maintenance).

### Monitoring we added

| Signal | Source | Alert threshold |
|---|---|---|
| DMARC alignment failure rate | DMARC aggregate reports (rua) | > 1 % |
| Bounce rate | MailChannels webhook → D1 counter | > 2 % in 24 h |
| Spam complaint rate | MailChannels webhook → D1 counter | > 0.1 % in 24 h |
| Send volume spike | Workers Analytics Engine | > 2× 7-day average |
| SPF `permerror` in DMARC reports | DMARC ruf (forensic) reports | Any occurrence |

```typescript
// Emit send metrics to Analytics Engine
export async function sendWithMetrics(
  to: { email: string; name: string },
  subject: string,
  html: string,
  env: Env
): Promise<void> {
  const start = Date.now();
  let outcome: 'success' | 'suppressed' | 'error' = 'error';

  try {
    const result = await sendIfNotSuppressed(to, subject, html, env);
    outcome = result === 'sent' ? 'success' : 'suppressed';
  } finally {
    env.ANALYTICS.writeDataPoint({
      blobs: [outcome, new URL(env.BASE_URL).hostname],
      doubles: [Date.now() - start],
      indexes: [outcome],
    });
  }
}
```

---

## Anti-patterns

| Anti-pattern | Consequence |
|---|---|
| Sending bulk marketing from a transactional sub-domain | Reputation of transactional stream contaminated |
| DMARC in `p=none` forever | No enforcement; failures are invisible to receivers |
| No suppression list | Continuing to send to hard-bounced or complaint addresses |
| Storing DKIM private key in wrangler.toml | Key checked into git; credential leak |
| Sending without a List-Unsubscribe header for marketing | Violates Gmail/Yahoo 2024 bulk sender requirements |
| SPF record on root domain used for sub-domain sends | DMARC alignment fails if `From:` is a sub-domain |

---

## Gotchas

1. **DMARC alignment requires the `From:` header domain to align with either the SPF or DKIM
   domain.** If you send from `no-reply@mail.example.com` but your DKIM signature is for
   `example.com`, alignment will fail in strict mode (`adkim=s`).

2. **MailChannels free tier has rate limits.** Burst sends can return HTTP 429. Implement
   exponential back-off with `Retry-After` header parsing.

3. **DMARC forensic reports (`ruf`)** contain full email headers and sometimes body snippets.
   Make sure your DMARC reporting mailbox is appropriately access-controlled.

4. **Gmail and Yahoo now require** a one-click `List-Unsubscribe-Post` header for bulk senders
   (> 5 000 msg/day). Missing this can cause your messages to be auto-filtered to spam.

5. **SPF `~all` (soft fail) vs `-all` (hard fail).** Moving to `-all` prematurely causes legitimate
   emails from missed senders to be rejected. Move to `-all` only after confirming your SPF record
   covers all actual sending paths.

---

## Verification

```typescript
// Smoke test: send to a controlled mailbox and verify headers
import { describe, it, expect } from 'vitest';

describe('email auth headers', () => {
  it('MailChannels payload includes DKIM fields', () => {
    const payload = buildEmailPayload(
      { email: 'test@example.com', name: 'Test' },
      'Hello',
      '<p>Hello</p>',
      { DKIM_PRIVATE_KEY: 'fake-key-for-test' } as Env
    );

    expect(payload.personalizations[0].dkim_domain).toBe('mail.example.com');
    expect(payload.personalizations[0].dkim_selector).toBe('mailchannels');
    expect(payload.personalizations[0].dkim_private_key).toBe('fake-key-for-test');
    expect(payload.from.email).toMatch(/@mail\.orchords\.com$/);
  });
});
```

In production, use [mail-tester.com](https://www.mail-tester.com) or the Google Postmaster Tools
to verify SPF, DKIM, and DMARC pass before going live.

---

## Related

- `documentation/categories/architecture/email-infrastructure.md`
- `documentation/categories/lessons/workers-cold-start-latency-lessons.md`
- Cloudflare Email Routing documentation

---

## Sources

- RFC 7208 — Sender Policy Framework
- RFC 6376 — DomainKeys Identified Mail
- RFC 7489 — Domain-based Message Authentication, Reporting, and Conformance
- MailChannels Workers integration documentation
- Google Postmaster Tools — Bulk Sender Guidelines (2024)
- Internal postmortem: `incidents/2025-10-email-deliverability-drop.md`
