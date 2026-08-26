# Privacy Email Alias Relay on Workers and Email Routing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Users want to give a unique, disposable email alias to each service they sign up
for — so they can receive mail without exposing their real address, identify which
service leaked their email, and kill an alias the moment spam appears. This is the
pattern used by Apple Hide My Email and SimpleLogin, implemented entirely on
Cloudflare Workers and Email Routing.

## Context

Cloudflare Email Routing lets a Worker receive mail at a catch-all address
(`*@relay.example.com`) and programmatically forward or drop it. A KV namespace
maps `alias → real_email`. Workers also use MailChannels to send outbound mail
with a `Reply-To` that routes replies back through the relay, keeping the real
address hidden end-to-end.

## Architecture

```
Sender → alias+abc123@relay.example.com
         ↓ Email Routing
         Email Worker (lookup alias in KV)
         ↓ alias found
         Forward to real@user.com  (Sender header rewritten)
         ↓
         User replies to "Reply-To: alias+abc123@relay.example.com"
         → routes back through the Worker → delivered to original Sender
```

## KV Schema

Aliases are stored with a structured JSON value:

```typescript
interface AliasRecord {
  realEmail: string;
  label: string;       // human-readable origin (e.g. "Amazon")
  createdAt: number;
  active: boolean;
}
```

Keys: `alias:<localPart>` → `JSON.stringify(AliasRecord)`

Metadata: `{ expiresAt?: number }` — KV TTL handles auto-expiry.

## Alias Creation API

```typescript
// alias-api/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const { realEmail, label } = await request.json<{
      realEmail: string;
      label: string;
    }>();

    // Simple auth — replace with your auth middleware
    const token = request.headers.get('Authorization')?.replace('Bearer ', '');
    if (token !== env.API_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }

    const localPart = generateAliasLocalPart();
    const record: AliasRecord = {
      realEmail,
      label,
      createdAt: Date.now(),
      active: true,
    };

    await env.ALIASES.put(`alias:${localPart}`, JSON.stringify(record));

    const alias = `${localPart}@${env.RELAY_DOMAIN}`;
    return Response.json({ alias }, { status: 201 });
  },
};

function generateAliasLocalPart(): string {
  // 8 random hex chars — 4 billion combinations, short enough to type
  const bytes = new Uint8Array(4);
  crypto.getRandomValues(bytes);
  return [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## Inbound Relay Worker

```typescript
// relay-worker/index.ts
import { EmailMessage } from 'cloudflare:email';

export default {
  async email(message: EmailMessage, env: Env): Promise<void> {
    // Extract the local part before @relay.example.com
    const localPart = message.to.split('@')[0].toLowerCase();
    const raw = await env.ALIASES.get(`alias:${localPart}`);

    if (!raw) {
      // Unknown alias — silently drop (no bounce to avoid backscatter)
      message.setReject('Unknown alias');
      return;
    }

    const record: AliasRecord = JSON.parse(raw);

    if (!record.active) {
      message.setReject('Alias deactivated');
      return;
    }

    // Rewrite the From display name to include the alias label so the user
    // knows which alias received the mail, but keep deliverability intact by
    // preserving the original From domain for SPF/DKIM verification context.
    // The actual envelope-From becomes the relay domain (handled by Email Routing).

    const headers = new Headers({
      'X-Relay-Alias':  `${localPart}@${env.RELAY_DOMAIN}`,
      'X-Relay-Label':  record.label,
      // Tell the user's mail client to reply through the relay, not the real sender
      'Reply-To':       `${localPart}@${env.RELAY_DOMAIN}`,
    });

    await message.forward(record.realEmail, headers);
  },
};
```

## Outbound Reply Routing

When the user replies to a relayed message their client sends to
`alias@relay.example.com`. The Email Worker receives it, looks up the alias, then
re-sends to the *original sender* using MailChannels with the relay address as
`From`:

```typescript
// In the same relay-worker — handle outbound replies
async function handleOutboundReply(
  message: EmailMessage,
  record: AliasRecord,
  localPart: string,
  env: Env,
): Promise<void> {
  // The original sender is in the To header when the user replies
  const originalSender = message.to; // already the relay alias; real dest in headers

  // For full outbound relay you need to extract the real recipient from
  // a stored reply-target KV entry keyed by message-id (see thread-matching article)
  const replyTarget = await env.ALIASES.get(`reply:${localPart}`);
  if (!replyTarget) return;

  const payload = {
    personalizations: [{ to: [{ email: replyTarget }] }],
    from: { email: `${localPart}@${env.RELAY_DOMAIN}`, name: record.label },
    subject: message.headers.get('subject') ?? '',
    content: [{ type: 'text/plain', value: '(see original email client)' }],
    headers: {
      'In-Reply-To': message.headers.get('in-reply-to') ?? '',
      'References':  message.headers.get('references') ?? '',
    },
  };

  await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
```

## Anti-patterns

- **Bouncing unknown aliases** — sends backscatter to the forged sender; always
  call `message.setReject()` to drop silently at the SMTP level.
- **Using predictable alias names** — sequential or timestamp-based aliases can be
  enumerated; use cryptographically random local parts.
- **Storing `realEmail` in the alias local part itself** — that leaks the real
  address in the SMTP envelope; always indirect through KV.
- **Not rate-limiting alias creation** — without limits, the API becomes a spam
  alias generator; apply per-user creation quotas in KV counters.

## Gotchas

- Email Routing catch-all rules must be enabled in the Cloudflare dashboard for
  `*@relay.example.com` — individual address rules take precedence and shadow it.
- `message.forward()` preserves the original DKIM signature; the forwarded message
  may fail DMARC at the destination if the relay domain differs from the `From:`
  domain — an unavoidable limitation of simple forwarding (vs. full re-sending).
- KV `get()` returns `null` for expired keys even if you did not set a TTL; guard
  against `null` before `JSON.parse()`.
- Alias local parts that contain `+` characters are technically valid but many ESPs
  treat them as subaddressing; avoid `+` in generated local parts.

## Verification

```bash
# Create a test alias
curl -X POST https://relay-api.example.com/alias \
  -H "Authorization: Bearer $SECRET" \
  -H "Content-Type: application/json" \
  -d '{"realEmail":"me@personal.com","label":"TestService"}'

# Send a test email to the returned alias via any SMTP client
# Confirm delivery to me@personal.com with X-Relay-Alias header

# Check KV
wrangler kv key get --namespace-id=<id> "alias:<localPart>"
```

## Related

- `email-alias-routing-kv-workers.md`
- `email-forwarding-alias-management-workers-d1.md`
- `email-reply-to-thread-matching-d1.md`
- `cloudflare-email-routing-workers.md`
- `email-forwarding-spf-alignment-srs-workers.md`

## Sources

- Cloudflare Email Routing Workers: https://developers.cloudflare.com/email-routing/email-workers/
- EmailMessage.forward(): https://developers.cloudflare.com/email-routing/email-workers/reply-email-workers/
- Cloudflare KV: https://developers.cloudflare.com/kv/
- RFC 5321 §4.5.5 — Loop detection and bounce handling
