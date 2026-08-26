# feature-cookbook-comms-channels

**Issue:** Communication channels — email, push, in-app
**Date:** 2026-08-09
**Status:** documented

## Symptom
You want to notify the user. Email goes to spam. Push
notification is too noisy. The in-app banner is missed.
You wish you had a clear comms strategy.

## Root cause
**Communication is a feature.** Without a strategy,
notifications are missed or annoying.

**Source:** Various product guides.

## Channels

### Email
- **Use:** Async, non-urgent, formal
- **Pros:** Universal, archival
- **Cons:** Spam folder, delay

### Push
- **Use:** Real-time, urgent
- **Pros:** Immediate
- **Cons:** Permission, battery

### In-app
- **Use:** User is active
- **Pros:** Rich
- **Cons:** Only when user is in the app

### SMS
- **Use:** Critical, time-sensitive
- **Pros:** Universal
- **Cons:** Cost, regulation

### Webhook
- **Use:** Programmatic, machine-to-machine
- **Pros:** Reliable
- **Cons:** Developer only

## The "email" pattern

For email, use a transactional email service:
- **Resend:** Modern, simple
- **Postmark:** Reliable
- **SendGrid:** Mature
- **AWS SES:** Cheap

```ts
await resend.emails.send({
  from: 'app@example.com',
  to: user.email,
  subject: 'Welcome!',
  html: '<h1>Welcome to our app</h1>',
});
```

The email is sent.

## The "push" pattern

For push, use Web Push API:
- **Web:** Service worker + push subscription
- **iOS:** APNs
- **Android:** FCM

```ts
// 1. Client subscribes
const subscription = await registration.pushManager.subscribe({
  userVisibleOnly: true,
  applicationServerKey: VAPID_PUBLIC_KEY,
});

// 2. Server sends
await webpush.sendNotification(subscription, JSON.stringify({
  title: 'New message',
  body: 'You have a new message from Alice',
}));
```

The push is sent.

**Source:** Web Push API:
https://developer.mozilla.org/en-US/docs/Web/API/Push_API

## The "in-app" pattern

For in-app, use a banner + real-time channel:
```tsx
function InAppBanner({ notifications }: { notifications: Notification[] }) {
  return (
    <div className="banner">
      {notifications.map(n => (
        <div key={n.id}>
          <strong>{n.title}</strong>
          <p>{n.body}</p>
        </div>
      ))}
    </div>
  );
}
```

The banner is rendered.

## The "SMS" pattern

For SMS, use a service:
- **Twilio:** Mature
- **Vonage:** International
- **AWS SNS:** Cheap

```ts
await twilio.messages.create({
  from: '+1234567890',
  to: user.phone,
  body: 'Your code is 123456',
});
```

The SMS is sent.

## The "webhook" pattern

For webhooks, sign + retry:
```ts
async function sendWebhook(url: string, payload: any, env: Env): Promise<void> {
  const signature = await sign(payload, env.WEBHOOK_SECRET);

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await fetch(url, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-signature': signature,
          'x-attempt': String(attempt + 1),
        },
        body: JSON.stringify(payload),
      });
      return;  // Success
    } catch (err) {
      if (attempt === 2) throw err;
      await sleep(2 ** attempt * 1000);
    }
  }
}
```

The webhook is retried.

## The "channel selection" pattern

For channel selection, the right tool:
- **Critical:** SMS or push
- **Important:** Email
- **Nice-to-know:** In-app
- **Programmatic:** Webhook

## The "frequency capping" pattern

For frequency, cap per user:
- **Max 1 email/day:** No spam
- **Max 5 push/day:** No battery drain
- **No in-app spam:** Aggregate

```ts
async function shouldSend(userId: string, channel: string, env: Env): Promise<boolean> {
  const key = `comms:${userId}:${channel}:${currentDate}`;
  const count = parseInt((await env.KV!.get(key)) ?? '0');
  return count < MAX_PER_DAY;
}

async function recordSend(userId: string, channel: string, env: Env): Promise<void> {
  const key = `comms:${userId}:${channel}:${currentDate}`;
  const count = parseInt((await env.KV!.get(key)) ?? '0');
  await env.KV!.put(key, String(count + 1), { expirationTtl: 86400 });
}
```

The frequency is capped.

## The "user preferences" pattern

For preferences, the user opts in:
```sql
CREATE TABLE notification_preferences (
  user_id TEXT PRIMARY KEY,
  email_enabled BOOLEAN DEFAULT true,
  push_enabled BOOLEAN DEFAULT true,
  in_app_enabled BOOLEAN DEFAULT true,
  sms_enabled BOOLEAN DEFAULT false,
  quiet_hours_start TEXT,  -- '22:00'
  quiet_hours_end TEXT,    -- '08:00'
);
```

The user controls the channels.

## The "template" pattern

For templates, separate content:
```ts
// templates/welcome.ts
export function renderWelcome(user: User): { subject: string; html: string } {
  return {
    subject: `Welcome, ${user.displayName}!`,
    html: `<h1>Welcome, ${user.displayName}!</h1><p>Thanks for signing up.</p>`,
  };
}

// Use
const template = renderWelcome(user);
await sendEmail(user.email, template, env);
```

The content is separate.

## The "i18n" pattern

For i18n, support multiple languages:
```ts
const templates = {
  'en': {
    welcome: { subject: 'Welcome, {{name}}!', html: '<h1>Welcome, {{name}}!</h1>' },
  },
  'es': {
    welcome: { subject: '¡Bienvenido, {{name}}!', html: '<h1>¡Bienvenido, {{name}}!</h1>' },
  },
};

function render(user: User, key: string): Template {
  const locale = user.locale ?? 'en';
  const template = templates[locale]?.[key] ?? templates['en'][key];
  return interpolate(template, { name: user.displayName });
}
```

The content is localized.

## The "deliverability" pattern

For email deliverability:
- **SPF:** Sender policy framework
- **DKIM:** DomainKeys identified mail
- **DMARC:** Reporting + alignment
- **List-unsubscribe:** Standard header
- **Low spam score:** Avoid spam triggers

**Source:** DMARC:
https://dmarc.org/

## The "comms anti-pattern" anti-patterns

### 1. Spam
- **Issue:** User unsubscribes
- **Fix:** Frequency cap + opt-in

### 2. Wrong channel
- **Issue:** Important email goes to spam
- **Fix:** Critical = SMS or push

### 3. No preferences
- **Issue:** User can't opt out
- **Fix:** Preferences

### 4. No templates
- **Issue:** Copy-paste everywhere
- **Fix:** Template per message

### 5. No i18n
- **Issue:** English-only
- **Fix:** Localize

## Verification
- **Test:** Each channel works
- **Test:** Preferences are respected
- **Test:** Frequency is capped
- **Live:** Comms is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "spam" anti-pattern.** Cap + opt-in.
- **The "wrong channel" anti-pattern.** Match urgency.
- **The "no i18n" anti-pattern.** Localize.

## Related
- `feature-cookbook-comms.md`
- `feature-cookbook-email.md`
- `feature-cookbook-onboarding.md`
- `i18n/` (8 entries)
- Resend: https://resend.com/
- Twilio: https://www.twilio.com/
- Web Push: https://developer.mozilla.org/en-US/docs/Web/API/Push_API
- DMARC: https://dmarc.org/
