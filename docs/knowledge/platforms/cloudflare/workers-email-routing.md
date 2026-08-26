# workers-email-routing

**Issue:** Processing inbound email with Cloudflare Email Routing and Workers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Email Routing lets you attach a Worker to an email address. The Worker receives a `EmailMessage` and can forward, reply, drop, or parse the message.

## Pattern / Solution

```toml
# wrangler.toml
name = "email-handler"

[[send_email]]
name = "SEND_EMAIL"  # binding for outbound send
```

```typescript
import { EmailMessage } from 'cloudflare:email';
import { createMimeMessage } from 'mimetext'; // npm package

export interface Env {
  SEND_EMAIL: SendEmail;
  DB: D1Database;
}

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
    // Read sender / subject
    const from = message.from;
    const subject = message.headers.get('subject') ?? '(no subject)';

    // Read raw body as text
    const reader = message.raw.getReader();
    const chunks: Uint8Array[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    const raw = new TextDecoder().decode(
      chunks.reduce((a, b) => { const c = new Uint8Array(a.length + b.length); c.set(a); c.set(b, a.length); return c; }, new Uint8Array())
    );

    // Store in D1
    await env.DB.prepare(
      `INSERT INTO emails (from_addr, subject, raw) VALUES (?, ?, ?)`
    ).bind(from, subject, raw).run();

    // Forward to a team inbox
    await message.forward('team@example.com');

    // — OR — send a custom reply
    const reply = createMimeMessage();
    reply.setSender({ name: 'Bot', addr: 'bot@example.com' });
    reply.setTo(from);
    reply.setSubject(`Re: ${subject}`);
    reply.addMessage({ contentType: 'text/plain', data: 'Thanks, we got your email!' });

    const replyMsg = new EmailMessage('bot@example.com', from, reply.asRaw());
    await env.SEND_EMAIL.send(replyMsg);
  },
};
```

**Dashboard setup:**
1. Enable Email Routing on your domain.
2. Add a custom address → "Send to a Worker" → select your Worker.
3. Add the `[[send_email]]` binding in `wrangler.toml` for outbound send capability.

## Gotchas
- `message.raw` is a `ReadableStream` — you can only read it once. Clone before reading if you need multiple passes.
- `message.forward()` preserves the original envelope; `SEND_EMAIL.send()` creates a new message from scratch.
- Workers receive emails only for addresses configured in the Email Routing rules; catch-all rules also work.
- Maximum email size is **25 MB** (including attachments).
- The `email` export is a top-level handler, separate from `fetch` and `scheduled`.
- Outbound `SEND_EMAIL` binding requires domain verification; test with Mailtrap or similar first.

## Related
- `email-service-best-practices.md`
- `workers-scheduled-events.md`
- `workers-best-practices.md`
