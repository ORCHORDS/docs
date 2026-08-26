# feature-cookbook-email

**Issue:** Email patterns — transactional, marketing, deliverability
**Date:** 2026-08-09
**Status:** documented

## Symptom
You send a transactional email. The user doesn't receive
it. It goes to spam. You don't know why. You check the
DNS. No SPF, no DKIM, no DMARC. Your domain is blacklisted.

## Root cause
**Email deliverability is hard.** Without proper DNS
records, authentication, and content, your emails go to
spam.

**Source:** Various email guides.

## The "DNS records" pattern

For email authentication:
```dns
; SPF
@ IN TXT "v=spf1 include:_spf.google.com ~all"

; DKIM
selector._domainkey IN TXT "v=DKIM1; k=rsa; p=..."

; DMARC
_dmarc IN TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com"
```

The records verify the email is from your domain.

## The "transactional email" pattern

For one-off emails (signup confirmation, password reset):
```ts
async function sendTransactionalEmail(input: EmailInput, env: Env): Promise<void> {
  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: 'MyApp <noreply@example.com>',
      to: input.to,
      subject: input.subject,
      html: input.html,
      text: input.text,  // Plain text fallback
    }),
  });

  if (!response.ok) {
    throw new Error(`Email send failed: ${response.status}`);
  }
}
```

The email is sent via a vendor (Resend, Postmark, SendGrid).

## The "email template" pattern

For templating, use a template engine:
```ts
import Handlebars from 'handlebars';

const template = Handlebars.compile(`
<!DOCTYPE html>
<html>
<body>
<h1>Welcome, {{name}}!</h1>
<p>Click <a >here</a> to activate your account.</p>
</body>
</html>
`);

const html = template({ name: 'Alice', activationUrl: 'https://example.com/activate?token=...' });
```

Templates are reusable; the data is variable.

## The "i18n email" pattern

For 20 locales, use i18next:
```ts
import i18next from 'i18next';

await i18next.init({ resources: { en: { translation: enMessages }, /* ... */ } });

const subject = i18next.t('welcome.subject', { lng: user.locale });
const body = i18next.t('welcome.body', { lng: user.locale, name: user.name });
```

The email is in the user's language.

## The "queue" pattern for email

For async sending, use a queue:
```ts
async function sendEmail(input: EmailInput, env: Env): Promise<void> {
  await env.EMAIL_QUEUE.send(input);
}

// Queue handler
export default {
  async queue(batch: MessageBatch<EmailInput>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await sendViaResend(message.body, env);
        message.ack();
      } catch (err) {
        // Retry with backoff
        message.retry({ delaySeconds: 60 });
      }
    }
  },
};
```

The email is sent async; the user request is not blocked.

## The "bounce handling" pattern

For bounces, use a webhook from the vendor:
```ts
async function handleEmailBounce(event: BounceEvent, env: Env): Promise<void> {
  await env.DB!.prepare(
    `UPDATE users SET email_status = 'bounced', email_bounced_at = ? WHERE email = ?`
  ).bind(new Date().toISOString(), event.email).run();
}
```

The bounce is recorded; the user is marked.

## The "unsubscribe" pattern

For marketing email, the CAN-SPAM + GDPR requirement:
```html
<a href="https://example.com/unsubscribe?token=<redacted-secret>
```

The user can unsubscribe in 1 click.

## The "double opt-in" pattern

For GDPR compliance:
1. User signs up
2. Email is sent with a confirmation link
3. User clicks the link
4. The user is confirmed

```ts
async function signup(input: SignupInput, env: Env): Promise<void> {
  const confirmationToken = crypto.randomUUID();

  await env.DB!.prepare(
    `INSERT INTO users (id, email, status, confirmation_token) VALUES (?, ?, 'pending', ?)`
  ).bind(crypto.randomUUID(), input.email, confirmationToken).run();

  await sendEmail({
    to: input.email,
    subject: 'Confirm your email',
    html: `<a href="https://example.com/confirm?token=<redacted-secret>
  }, env);
}

async function confirmEmail(token: string, env: Env): Promise<void> {
  await env.DB!.prepare(
    `UPDATE users SET status = 'active', confirmation_token = NULL WHERE confirmation_token = ?`
  ).bind(token).run();
}
```

The user is active only after confirmation.

## The "rate limit" pattern for email

For per-user rate limit:
```ts
async function canSendEmail(userId: string, env: Env): Promise<boolean> {
  const id = env.RATE_LIMIT.idFromName(`email:${userId}`);
  const stub = env.RATE_LIMIT.get(id);
  const response = await stub.fetch('https://rate-limit/check', {
    method: 'POST',
    body: JSON.stringify({ limit: 10, windowMs: 60_000 }),
  });
  return response.ok;
}
```

The user can send max 10 emails per minute.

## The "deliverability" pattern

For high deliverability:
1. **Authenticate:** SPF, DKIM, DMARC
2. **Warm up:** Start with low volume; ramp up
3. **Clean list:** Remove bounces, unsubscribes
4. **Avoid spam words:** "Free!", "Buy now!"
5. **HTML ratio:** Don't be all images
6. **Plain text version:** Always include

## The "email testing" pattern

For testing, use:
- **Mailtrap:** Sandbox inbox
- **Mailosaur:** Test email service
- **Resend test mode:** Send to a test address

```ts
const response = await fetch('https://api.resend.com/emails', {
  // ...
  headers: {
    'X-Resend-Test': 'true',  // Test mode
  },
});
```

The test mode captures the email without sending.

## The "email analytics" pattern

For tracking:
- **Open rate:** Pixel tracking (controversial)
- **Click rate:** Link tracking
- **Bounce rate:** Bounce webhooks

```html
<a href="https://example.com/track?url={{encodedUrl}}&emailId={{emailId}}">Click</a>
```

The link is tracked; the click is recorded.

## The "email list" pattern

For marketing, manage the list:
```sql
CREATE TABLE email_list (
  email TEXT PRIMARY KEY,
  status TEXT NOT NULL,  -- 'subscribed', 'unsubscribed', 'bounced'
  subscribed_at TEXT,
  unsubscribed_at TEXT
);
```

The list is the source of truth for who to email.

## The "campaign" pattern

For marketing campaigns:
```ts
async function sendCampaign(campaignId: string, env: Env): Promise<void> {
  const campaign = await env.DB!.prepare(`SELECT * FROM campaigns WHERE id = ?`).bind(campaignId).first();
  const recipients = await env.DB!.prepare(`SELECT email FROM email_list WHERE status = 'subscribed'`).all();

  for (const recipient of recipients.results) {
    await env.EMAIL_QUEUE.send({
      to: recipient.email,
      subject: campaign.subject,
      html: renderTemplate(campaign.template, { email: recipient.email }),
    });
  }
}
```

The campaign is sent in batch (to avoid rate limits).

## Verification
- **Test:** Email is sent
- **Test:** Email is received (Mailtrap)
- **Live:** Deliverability is monitored
- **Audit:** Annual deliverability review

## Gotchas
- **The "no SPF/DKIM/DMARC" anti-pattern.** Without
  authentication, the email goes to spam.
- **The "all-HTML email" anti-pattern.** Include a plain
  text version.
- **The "no unsubscribe" anti-pattern.** Marketing email
  without unsubscribe is illegal (CAN-SPAM, GDPR).
- **The "sending too fast" anti-pattern.** Vendors rate
  limit; warm up the sender.
- **The "PII in the email body" anti-pattern.** Encrypt
  sensitive data; use a magic link instead.

## Related
- `feature-cookbook.md`
- `i18n/icu-messageformat-advanced.md`
- `webhook-implementation.md`
- `audit-log-as-product.md`
- Resend: https://resend.com/docs
- Postmark: https://postmarkapp.com/developer
- SendGrid: https://docs.sendgrid.com/
