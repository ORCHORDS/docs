# email-service-best-practices

**Issue:** Email Service — send, receive, process
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your agent needs to send an email. You use Resend.
The user replies. You have no way to receive the
reply. You wish you had a native email layer.

## Root cause
**Sending is half the problem.** Use Email Service.

**Source:** CF Email Service:
https://developers.cloudflare.com/email-service/

## The "Email Service" concept

Email Service (public beta 2026):
- **Send:** From your domain
- **Receive:** To your domain
- **Process:** In a Worker
- **Native to agents:** Built for AI workflows

The email is native to Cloudflare.

## The "send" pattern

For sending:
```ts
const message = await fetch('https://api.email-service.cloudflare.com/v1/send', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${env.EMAIL_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    from: 'app@example.com',
    to: 'user@example.com',
    subject: 'Welcome!',
    html: '<h1>Welcome!</h1>',
  }),
});
```

The email is sent.

## The "receive" pattern

For receiving:
```ts
export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
    // 1. Parse the message
    const forward = message.forward;
    const subject = message.headers.get('subject');

    // 2. Process
    await processIncomingEmail(message, env);

    // 3. Set the reply
    message.setReply({
      from: 'app@example.com',
      subject: `Re: ${subject}`,
      text: 'Thanks for your email!',
    });
  },
};
```

The email is received + replied to.

## The "agent" pattern

For agent use:
```ts
async function emailAgent(message: EmailMessage, env: Env): Promise<void> {
  // 1. Read the email
  const text = await message.text();

  // 2. Use the agent
  const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
    prompt: `Reply to this email:\n\n${text}`,
  });

  // 3. Send the reply
  await message.setReply({
    from: 'agent@example.com',
    subject: `Re: ${message.headers.get('subject')}`,
    text: response.response,
  });
}
```

The agent replies.

## The "DNS setup" pattern

For DNS:
```
# SPF
example.com TXT "v=spf1 include:_spf.email-service.cloudflare.com -all"

# DKIM
email-service._domainkey.example.com CNAME ...

# DMARC
_dmarc.example.com TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com"
```

The DNS is configured.

## The "auto-reply" pattern

For auto-reply:
```ts
export default {
  async email(message: EmailMessage, env: Env): Promise<void> {
    if (message.headers.get('from')?.includes('noreply')) {
      return;  // Don't reply to no-reply
    }

    await message.setReply({
      from: 'support@example.com',
      subject: 'We received your email',
      text: 'We will get back to you within 24 hours.',
    });
  },
};
```

The auto-reply is set.

## The "routing" pattern

For routing to a Worker:
```toml
[email]
address = "support@example.com"
destination = "my-worker"
```

The email is routed.

## The "attachment" pattern

For attachments:
```ts
async function handleEmail(message: EmailMessage, env: Env): Promise<void> {
  for (const part of message.attachments) {
    const filename = part.filename;
    const data = await part.arrayBuffer();

    // Save to R2
    await env.R2!.put(`attachments/${crypto.randomUUID()}-${filename}`, data);
  }
}
```

The attachments are saved.

## The "spam filter" pattern

For spam filtering:
```ts
async function isSpam(message: EmailMessage, env: Env): Promise<boolean> {
  // 1. Check SPF/DKIM/DMARC
  const spf = message.headers.get('received-spf');
  if (spf?.includes('fail')) return true;

  // 2. Check content
  const text = await message.text();
  if (text.includes('viagra')) return true;

  return false;
}

export default {
  async email(message: EmailMessage, env: Env): Promise<void> {
    if (await isSpam(message, env)) {
      return;  // Drop
    }
    await processEmail(message, env);
  },
};
```

The spam is filtered.

## The "email anti-pattern" anti-patterns

### 1. Polling for new mail
- **Issue:** Slow + waste
- **Fix:** Webhook / email routing

### 2. No DKIM
- **Issue:** Goes to spam
- **Fix:** Configure DKIM

### 3. No SPF
- **Issue:** Goes to spam
- **Fix:** Configure SPF

### 4. No DMARC
- **Issue:** Forgery possible
- **Fix:** Configure DMARC

### 5. No spam filter
- **Issue:** Inbox is unusable
- **Fix:** Filter

## Verification
- **Test:** Send works
- **Test:** Receive works
- **Test:** Reply works
- **Test:** Attachments work
- **Live:** Email service health
- **Audit:** Quarterly review

## Gotchas
- **The "no DKIM" anti-pattern.** Configure DKIM.
- **The "no SPF" anti-pattern.** Configure SPF.
- **The "no spam filter" anti-pattern.** Filter.

## Related
- `feature-cookbook-email.md`
- `feature-cookbook-email-detail.md`
- `feature-cookbook-comms-channels.md`
- Email Service: https://developers.cloudflare.com/email-service/
