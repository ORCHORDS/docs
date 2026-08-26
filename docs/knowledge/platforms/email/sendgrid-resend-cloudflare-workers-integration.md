# sendgrid-resend-cloudflare-workers-integration

**Issue:** Integrating SendGrid and Resend with Cloudflare Workers—
           webhook signature verification fails, bounce events are
           missed, and mobile click-tracking strips protocol on iOS
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Workers receiving SendGrid Event Webhooks return 200 but silently
discard events because HMAC signature verification was never wired
up.  Bounce and complaint events accumulate in the ESP dashboard
but are never written to the suppression list, so the platform keeps
sending to hard-bounced addresses.  iOS Mail pre-fetches tracking
links and registers opens/clicks that never happened; mobile click
links sometimes strip the `https://` scheme.

## Context

Both SendGrid and Resend expose an HTTP POST webhook for delivery
events (delivered, bounce, complaint, click, open).  A Cloudflare
Worker is the natural receiver: it sits on the edge, handles burst
traffic without cold starts, and can write directly to KV and D1.
The critical integration points are: (1) API client abstraction to
swap providers, (2) webhook signature verification, (3) event
processing pipeline, and (4) mobile link tracking hygiene.

## Provider comparison

```
┌─────────────────────┬──────────────────┬──────────────────────┐
│ Feature             │ SendGrid         │ Resend               │
├─────────────────────┼──────────────────┼──────────────────────┤
│ API style           │ REST, form body  │ REST, JSON           │
│ Webhook auth        │ ECDSA P-256 sig  │ HMAC-SHA-256 sig     │
│ Bounce webhook      │ Event type field │ email.bounced event  │
│ Complaint webhook   │ spam_report type │ email.complained     │
│ Click tracking      │ Opt-in per send  │ Opt-in per domain    │
│ Unsubscribe groups  │ Built-in         │ Manual suppression   │
│ Batch send API      │ Yes (up to 1000) │ Batch API (v1)       │
│ Workers-compatible  │ Yes (fetch)      │ Yes (resend SDK)     │
└─────────────────────┴──────────────────┴──────────────────────┘
```

## API client abstraction

Wrap both providers behind a common `send({ from, to, subject, html })`
interface.  The factory reads `env.EMAIL_PROVIDER` and returns the
matching implementation:

```js
export function createEmailClient(env) {
  if (env.EMAIL_PROVIDER === 'resend') {
    return {
      async send({ from, to, subject, html }) {
        const r = await fetch('https://api.resend.com/emails', {
          method: 'POST',
          headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`,
                     'Content-Type': 'application/json' },
          body: JSON.stringify({ from, to, subject, html }),
        });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      },
    };
  }
  // SendGrid
  return {
    async send({ from, to, subject, html }) {
      const r = await fetch('https://api.sendgrid.com/v3/mail/send', {
        method: 'POST',
        headers: { Authorization: `Bearer ${env.SENDGRID_API_KEY}`,
                   'Content-Type': 'application/json' },
        body: JSON.stringify({
          personalizations: [{ to: [{ email: to }] }],
          from: { email: from }, subject,
          content: [{ type: 'text/html', value: html }],
        }),
      });
      if (!r.ok) throw new Error(await r.text());
    },
  };
}
```

## Webhook signature verification

### Resend (HMAC-SHA-256, Svix)

Svix sends a `svix-signature` header containing one or more
`v1,<base64>` entries.  Verify the payload `${ts}.${body}`:

```js
async function verifyResendWebhook(req, env) {
  const ts   = req.headers.get('svix-timestamp') ?? '';
  const body = await req.text();
  const key  = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(env.RESEND_WEBHOOK_SECRET),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']);
  const rawSig = (req.headers.get('svix-signature') ?? '')
    .split(' ').find(s => s.startsWith('v1,'))?.slice(3) ?? '';
  const ok = await crypto.subtle.verify('HMAC', key,
    Uint8Array.from(atob(rawSig), c => c.charCodeAt(0)),
    new TextEncoder().encode(`${ts}.${body}`));
  if (!ok) throw new Response('Forbidden', { status: 403 });
  return JSON.parse(body);
}
```

### SendGrid (ECDSA P-256)

SendGrid signs with a P-256 key.  Concatenate the timestamp header
with the raw body, then verify the ECDSA signature using the public
key from the dashboard (Base64-encoded DER, not PEM):

```js
async function verifySendGridWebhook(req, env) {
  const sig  = req.headers.get('X-Twilio-Email-Event-Webhook-Signature');
  const ts   = req.headers.get('X-Twilio-Email-Event-Webhook-Timestamp');
  const body = await req.text();
  const der  = Uint8Array.from(atob(env.SENDGRID_WEBHOOK_PUBKEY),
                               c => c.charCodeAt(0));
  const key  = await crypto.subtle.importKey(
    'spki', der, { name: 'ECDSA', namedCurve: 'P-256' },
    false, ['verify']);
  const ok = await crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' }, key,
    Uint8Array.from(atob(sig), c => c.charCodeAt(0)),
    new TextEncoder().encode(ts + body));
  if (!ok) throw new Response('Forbidden', { status: 403 });
  return JSON.parse(body);
}
```

## Bounce and complaint event processing

Map provider-specific event type strings to a common handler.  Write
hard bounces and complaints to KV suppression and log to D1:

```js
export async function processEvents(events, env) {
  for (const evt of events) {
    const email = evt.email;
    const type  = evt.type ?? evt.event; // resend vs sendgrid
    if (type === 'email.bounced' &&
        (evt.bounce_type === 'hard' || evt.data?.type === 'hard')) {
      await env.SUP_KV.put(`sup:e:${email}`, '1');
      await env.DB.prepare(
        'INSERT INTO bounce_log (email, reason, ts) VALUES (?, ?, ?)',
      ).bind(email, evt.reason ?? '', Date.now()).run();
    }
    if (type === 'email.complained' || type === 'spamreport') {
      await env.SUP_KV.put(`sup:e:${email}`, '1');
      await env.DB.prepare(
        'INSERT INTO complaint_log (email, ts) VALUES (?, ?)',
      ).bind(email, Date.now()).run();
    }
  }
}
```

## Mobile link tracking considerations

ESP click-tracking proxies rewrite links through a redirect domain.
Three mobile issues follow: (1) iOS Mail Privacy Protection pre-fetches
all links on open, inflating click counts; (2) Android email parsers
occasionally drop the scheme from double-encoded redirect URLs;
(3) redirect proxies cannot forward to custom-scheme deep links.

Disable open tracking (unreliable post-MPP).  Skip ESP click-tracking
and instead append UTM parameters directly to destination URLs:

```js
function addUtm(url, campaign) {
  const u = new URL(url);
  u.searchParams.set('utm_source', 'email');
  u.searchParams.set('utm_medium', 'transactional');
  u.searchParams.set('utm_campaign', campaign);
  return u.toString();
}
```

Analytics platforms record clicks from UTM data without a redirect
proxy, and deep links remain intact.

## Anti-patterns

- Responding to webhooks with a redirect (301/302)—ESP dispatchers
  do not follow redirects and will eventually disable the endpoint.
- Verifying the signature after JSON.parse—the signature covers raw
  body bytes; always read the text first, verify, then parse.
- Acknowledging the webhook before both KV and D1 writes succeed—
  if the Worker crashes mid-write, the bounce is silently dropped.
- Hardcoding API keys in Worker source—use `wrangler secret put`.
- Treating ESP open-rate metrics as reliable post-Apple MPP.

## Gotchas

- The `svix-signature` header holds space-separated `v1,<base64>`
  values (key rotation).  Verify any one that passes; the code above
  picks the first `v1,` entry.
- SendGrid's ECDSA public key from the dashboard is Base64 DER, not
  PEM.  Do not add `-----BEGIN PUBLIC KEY-----` header lines.
- The Resend npm SDK uses Node.js `https` internally; it throws in
  Workers.  Always use the `fetch`-based client shown above.
- `wrangler secret put` values are available as `env.*` at runtime
  but not visible in `wrangler.toml`—document them in a `.env.example`
  for new contributors.

## Verification

```bash
# Send test email
curl -X POST https://api.example.com/email/send \
  -d '{"to":"test@example.com","subject":"T","html":"<p>Hi</p>"}'

# Replay bounce webhook (use real HMAC sig in production)
curl -X POST https://api.example.com/webhooks/email \
  -H 'svix-signature: v1,<SIG>' -H 'svix-timestamp: <TS>' \
  -d '[{"type":"email.bounced","email":"bad@example.com",
       "bounce_type":"hard"}]'  # Expected: 200 OK

# Confirm KV suppression and D1 bounce log
wrangler kv:key get --binding SUP_KV "sup:e:bad@example.com"
wrangler d1 execute DB \
  --command "SELECT * FROM bounce_log WHERE email='bad@example.com'"
```

## Related

- `documentation/docs/policies/email/sendgrid-setup.md`
- `documentation/docs/policies/email/resend-setup.md`
- `documentation/docs/policies/email/sendgrid-event-webhook.md`
- `documentation/docs/policies/email/bounce-handling-hard-soft.md`
- `documentation/docs/policies/email/suppression-list-management.md`

## Source URLs

- https://resend.com/docs/dashboard/webhooks/introduction
- https://docs.sendgrid.com/for-developers/tracking-events/getting-started-event-webhook-security-features
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://support.apple.com/en-us/HT212019  (Mail Privacy Protection)
- https://docs.sendgrid.com/api-reference/mail-send/mail-send
