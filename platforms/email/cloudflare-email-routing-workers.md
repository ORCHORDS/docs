# cloudflare-email-routing-workers

**Issue:** Custom email processing via Cloudflare Email Routing + Workers
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Teams need to receive email at a custom domain, route messages by
address pattern, sanitize anonymous platform addresses, and handle
edge cases in mobile email clients — all without running a mail
server.

## Context

Cloudflare Email Routing lets a zone receive SMTP mail and hand each
message to a Workers handler before forwarding or dropping it.  The
handler runs on the same V8 isolate runtime as other Workers and
receives a `ForwardableEmailMessage` object.  Unlike a full MTA the
Worker cannot originate new SMTP connections; it can only forward,
reject, or silently drop the message.

## Architecture overview

```
Inbound SMTP
    │
    ▼
Cloudflare MX  (route1/2/3.mx.cloudflare.net)
    │
    ▼
Email Routing rule  ──►  Email Worker (custom handler)
                              │
                    ┌─────────┼──────────┐
                    ▼         ▼          ▼
               forward    reject      drop
```

Workers handler skeleton:

```js
export default {
  async email(message, env, ctx) {
    const to = message.to.toLowerCase();

    // Reject obvious abuse before processing
    if (to.startsWith('noreply+')) {
      message.setReject('Address not monitored');
      return;
    }

    // Route by prefix
    if (to.startsWith('support+')) {
      await message.forward('help@internal.example.com');
      return;
    }

    // Default catch-all forward
    await message.forward(env.DEFAULT_DESTINATION);
  }
};
```

## Address sanitization for anonymous platforms

Anonymous platforms generate per-user relay addresses such as
`user_<uuid>@mail.example.com`.  The Worker resolves the UUID to an
internal user and forwards, or rejects if the user has opted out or
the address has expired.

```js
async function resolveAnonymousAddress(to, env) {
  const m = to.match(/^user_([0-9a-f-]{36})@/);
  if (!m) return null;

  const record = await env.RELAY_KV.get(m[1], { type: 'json' });
  if (!record || record.expiresAt < Date.now()) return null;
  if (record.optedOut) return null;
  return record.destination;
}
```

KV schema for relay records:

```
key   : user_<uuid>
value : {
  "destination": "alice@gmail.com",
  "expiresAt" : 1790000000000,   // epoch ms
  "optedOut"  : false,
  "ownerId"   : "u_12345"
}
```

## Forwarding rules and priority

Rules evaluate top-to-bottom; first match wins.  Mixing dashboard
rules with the Worker handler: if a Worker is bound, the Worker runs
*instead of* dashboard rules for addresses the Worker handles.  Use
the Worker for programmatic routing; use dashboard rules only as a
fallback or for static destinations.

```
┌──────────────────────────┬──────────────────────────┐
│ Rule type                │ Evaluated by             │
├──────────────────────────┼──────────────────────────┤
│ Specific address match   │ Dashboard (fast path)    │
│ Wildcard / catch-all     │ Dashboard (fast path)    │
│ Worker binding           │ Worker script            │
│ No rule, no worker       │ Bounce (550)             │
└──────────────────────────┴──────────────────────────┘
```

When both a Worker and a dashboard catch-all exist, the Worker takes
precedence; the catch-all never fires unless the Worker calls
`message.forward()` or re-invokes it explicitly.

## Mobile email client compatibility quirks

Mobile clients (Gmail app, Apple Mail on iOS, Samsung Mail) expose
several edge cases that affect routing logic:

- **Reply-to threading**: Some clients send `In-Reply-To` with
  the original `Message-ID`.  If the Worker rewrites `To:` on
  forward, the replied-to thread header still carries the relay
  address, so the thread correctly re-enters the Worker on reply.

- **Large attachment sizing**: iOS Mail sends MIME messages that
  inline-attach up to 5 MB photos before Cloudflare's 25 MB cap;
  Workers see the full MIME body.  Reject oversized messages early
  with a descriptive 550 to avoid silent truncation.

- **HTML-only bodies from mobile**: Samsung Mail and older Android
  clients omit `text/plain` parts.  If your Worker inspects the body
  (e.g. for content filtering) use a MIME parser that falls back to
  stripping HTML rather than erroring on missing plain-text.

- **Auto-replies from mobile OOO**: Mobile OOO senders set
  `Auto-Submitted: auto-replied`.  Check for this header before
  forwarding to avoid loop amplification through relay addresses.

```js
// Guard against auto-reply loops
if (message.headers.get('auto-submitted') === 'auto-replied') {
  message.setReject('Auto-replies not accepted');
  return;
}
```

## Anti-patterns

- Forwarding every message without inspecting `To:` first — allows
  enumeration of all relay addresses by brute-force.
- Storing relay destination in the local part of the address itself
  (e.g. `base64(dest)@example.com`) — trivially reversible.
- Using `drop` for unresolved UUIDs without logging — makes bounce
  investigation impossible; prefer explicit 550 with a trace ID.
- Calling `message.forward()` inside a try/catch that silently
  swallows errors — a failed forward becomes an invisible drop.

## Gotchas

- The Worker **cannot send new SMTP**; it can only forward the
  original message or call `setReject()`.
- `message.headers` is read-only; you cannot mutate headers before
  forwarding.  If you need header rewriting, route through a second
  service that accepts the forwarded mail and re-sends it.
- Workers have a 10 ms CPU-time budget per activation (50 ms on paid
  plans).  KV lookups are fast but counted; avoid N+1 patterns for
  bulk relay resolution.
- Email Routing requires the zone to have Cloudflare-managed MX.
  Zones with existing custom MX records must migrate or zone-split
  before enabling routing.
- Destination addresses must be individually verified in the
  dashboard; unverified destinations cause silent drops.

## Verification

```bash
# Send a test message to a relay address
echo "Test" | mail -s "relay test" user_<uuid>@mail.example.com

# Confirm delivery in destination inbox and check Worker logs
wrangler tail --format pretty

# Confirm KV record resolves correctly
wrangler kv:key get --binding RELAY_KV "user_<uuid>"

# Test rejection path
swaks --to noreply+test@mail.example.com \
      --server localhost --port 25
# Expect 550 in SMTP response
```

## Related

- `documentation/categories/email/cloudflare-email-routing.md`
- `documentation/categories/email/inbound-email-processing.md`
- `documentation/categories/email/email-catch-all-patterns.md`
- `documentation/categories/email/email-reply-to-patterns.md`
- `documentation/categories/email/multipart-mime-structure.md`

## Source URLs

- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/email-routing/setup/
- https://developers.cloudflare.com/email-routing/reference/limits/
- https://datatracker.ietf.org/doc/html/rfc3834  (auto-replies)
