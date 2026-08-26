# feature-cookbook-email-detail

**Issue:** Email — templates, deliverability, bounce
**Date:** 2026-08-09
**Status:** documented

## Symptom
You send 100k marketing emails. 90% go to spam. Your
domain reputation tanks. Future emails fail.

## Root cause
**Email is hard.** Use a transactional email service
+ good practices.

**Source:** DMARC + SPF + DKIM.

## The "transactional vs marketing" pattern

For transactional email:
- **Use:** Triggered by user action (signup, payment,
  password reset)
- **Pros:** Higher deliverability
- **Service:** Resend, Postmark, SendGrid

For marketing email:
- **Use:** Newsletter, announcements
- **Pros:** Bulk sending, analytics
- **Service:** Mailchimp, ConvertKit, SendGrid

Keep them separate (different IPs).

## The "template" pattern

For templates, separate content:
```ts
// templates/welcome.ts
export function renderWelcome(user: User): { subject: string; html: string; text: string } {
  return {
    subject: `Welcome, ${user.displayName}!`,
    html: `<h1>Welcome, ${user.displayName}!</h1><p>Thanks for signing up.</p>`,
    text: `Welcome, ${user.displayName}! Thanks for signing up.`,
  };
}
```

The template is reusable.

## The "i18n email" pattern

For i18n:
```ts
const templates = {
  'en': {
    welcome: { subject: 'Welcome, {{name}}!', body: '...' },
  },
  'es': {
    welcome: { subject: '¡Bienvenido, {{name}}!', body: '...' },
  },
};

function renderEmail(user: User, key: string): Email {
  const locale = user.locale ?? 'en';
  const template = templates[locale]?.[key] ?? templates['en'][key];
  return interpolate(template, { name: user.displayName });
}
```

The email is localized.

## The "deliverability" pattern

For deliverability:
- **SPF:** Sender policy framework
- **DKIM:** DomainKeys identified mail
- **DMARC:** Reporting + alignment
- **List-unsubscribe:** Standard header
- **Low spam score:** Avoid spam triggers

**Source:** DMARC:
https://dmarc.org/

## The "SPF" pattern

For SPF, the DNS record:
```
v=spf1 include:_spf.resend.com -all
```

The SPF is in DNS.

## The "DKIM" pattern

For DKIM, the DNS record (auto by Resend):
```
resend._domainkey.example.com -> v=DKIM1; k=rsa; p=...
```

DKIM is auto-configured by most services.

## The "DMARC" pattern

For DMARC, the DNS record:
```
_dmarc.example.com -> v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com
```

The DMARC is in DNS.

## The "bounce handling" pattern

For bounces, a webhook:
```ts
app.post('/webhooks/email/bounce', async (req) => {
  const { recipient, bounceType } = req.body;

  if (bounceType === 'permanent') {
    // Hard bounce: mark email as invalid
    await env.DB!.prepare(
      `UPDATE users SET email_valid = 0 WHERE email = ?`
    ).bind(recipient).run();
  }

  return new Response('OK');
});
```

The bounce is handled.

## The "unsubscribe" pattern

For unsubscribe, the link:
```html
<a href="https://example.com/unsubscribe?token=<redacted-secret>
```

```ts
app.get('/unsubscribe', async (req) => {
  const token = new URL(req.url).searchParams.get('token');
  await unsubscribeUser(token, env);
  return new Response('You have been unsubscribed.');
});
```

The unsubscribe works.

## The "list-unsubscribe" pattern

For list-unsubscribe, the header:
```ts
email.headers['List-Unsubscribe'] = '<mailto:unsubscribe@example.com>, <https://example.com/unsubscribe?token=...>';
email.headers['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click';
```

The standard header.

**Source:** RFC 8058 — List-Unsubscribe:
https://datatracker.ietf.org/doc/html/rfc8058

## The "double opt-in" pattern

For double opt-in:
1. **Signup:** User submits email
2. **Confirmation:** Send email with link
3. **Confirm:** User clicks the link
4. **Active:** User is now active

```ts
async function signup(input: SignupInput, env: Env): Promise<void> {
  const token = crypto.randomUUID();
  await env.DB!.prepare(
    `INSERT INTO users (id, email, status, confirmation_token) VALUES (?, ?, 'pending', ?)`
  ).bind(crypto.randomUUID(), input.email, token).run();

  await sendEmail(input.email, {
    subject: 'Confirm your email',
    html: `<a href="https://example.com/confirm?token=<redacted-secret>
  }, env);
}
```

The user is confirmed.

## The "email queue" pattern

For high volume, queue the emails:
```ts
async function sendBulkEmail(users: User[], template: string, env: Env): Promise<void> {
  for (const user of users) {
    await env.QUEUE.send({
      type: 'send_email',
      userId: user.id,
      template,
    });
  }
}
```

The emails are queued.

## The "email rate limit" pattern

For vendor rate limits:
- **Resend:** 100/sec default
- **Postmark:** 50/sec
- **SendGrid:** Varies

```ts
async function sendWithRateLimit(emails: Email[], env: Env): Promise<void> {
  const BATCH_SIZE = 100;
  const DELAY_MS = 1000;  // 1 sec between batches

  for (let i = 0; i < emails.length; i += BATCH_SIZE) {
    const batch = emails.slice(i, i + BATCH_SIZE);
    await Promise.all(batch.map(e => sendEmail(e, env)));
    if (i + BATCH_SIZE < emails.length) {
      await sleep(DELAY_MS);
    }
  }
}
```

The emails are throttled.

## The "email observability" pattern

For observability:
- **Sent:** How many sent?
- **Delivered:** How many delivered?
- **Opened:** How many opened?
- **Clicked:** How many clicked?
- **Bounced:** How many bounced?
- **Spam:** How many marked spam?

```ts
logEvent('email.sent', 'info', { userId, template });
logEvent('email.opened', 'info', { userId, template });
logEvent('email.clicked', 'info', { userId, template, link });
```

The email is tracked.

## The "email anti-pattern" anti-patterns

### 1. No SPF/DKIM/DMARC
- **Issue:** Emails go to spam
- **Fix:** Configure DNS

### 2. No unsubscribe
- **Issue:** Spam complaint
- **Fix:** Add unsubscribe

### 3. HTML only
- **Issue:** Some clients don't support HTML
- **Fix:** Plain text alternative

### 4. No rate limiting
- **Issue:** Vendor throttles
- **Fix:** Throttle

### 5. No bounce handling
- **Issue:** Bad emails are retried
- **Fix:** Handle bounces

## Verification
- **Test:** Email is sent
- **Test:** Email is delivered
- **Test:** Bounce is handled
- **Test:** Unsubscribe works
- **Live:** Deliverability is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no SPF/DKIM" anti-pattern.** Configure DNS.
- **The "no unsubscribe" anti-pattern.** Add link.
- **The "no bounce handling" anti-pattern.** Handle.

## Related
- `feature-cookbook-comms.md`
- `feature-cookbook-comms-channels.md`
- `feature-cookbook-onboarding.md`
- `i18n/` (8 entries)
- Resend: https://resend.com/
- Postmark: https://postmarkapp.com/
- DMARC: https://dmarc.org/
- RFC 8058: https://datatracker.ietf.org/doc/html/rfc8058
