# Forwarding and Transforming Inbound Emails with Workers Email Routing

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to intercept inbound emails delivered to a Cloudflare-managed domain and mutate them before forwarding to an internal address. The raw `EmailMessage` object exposed by the `email` handler lets you read MIME headers, rewrite `To` and `Subject`, reject spam programmatically, and forward to a new destination — all without a third-party relay.

---

## Context

Cloudflare Email Routing can invoke a Worker on every inbound message through the `email` event handler. The `EmailMessage` interface provides read access to `from`, `to`, `headers`, and a `raw` `ReadableStream` of the full RFC-5322 message. To send the (possibly mutated) message onward you call `message.forward(address, headers)` where the second argument is a `Headers` object whose entries override the original MIME headers. Spam or unwanted mail can be dropped by calling `message.setReject(reason)` — the SMTP session is then terminated with a 550. Workers Email Routing is only available on domains that use Cloudflare as their authoritative DNS and have Email Routing enabled in the dashboard.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "email-forward-transform"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
FORWARD_TO = "internal-team@example.com"
SUBJECT_PREFIX = "[INBOUND] "
SPAM_HEADER = "X-Spam-Status"
```

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  FORWARD_TO: string;
  SUBJECT_PREFIX: string;
  SPAM_HEADER: string;
}

interface EmailMessage {
  readonly from: string;
  readonly to: string;
  readonly headers: Headers;
  readonly raw: ReadableStream;
  readonly rawSize: number;
  forward(rcptTo: string, headers?: Headers): Promise<void>;
  setReject(reason: string): void;
}

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
    // --- Spam rejection ---
    const spamStatus = message.headers.get(env.SPAM_HEADER);
    if (spamStatus && spamStatus.toLowerCase().startsWith("yes")) {
      message.setReject("Message identified as spam");
      return;
    }

    // Block no-reply senders
    const lowerFrom = message.from.toLowerCase();
    if (lowerFrom.startsWith("no-reply@") || lowerFrom.startsWith("noreply@")) {
      message.setReject("Automated sender not accepted");
      return;
    }

    // --- Header transformation ---
    const overrideHeaders = new Headers();

    // Rewrite Subject with prefix
    const originalSubject = message.headers.get("Subject") ?? "(no subject)";
    const newSubject = originalSubject.startsWith(env.SUBJECT_PREFIX)
      ? originalSubject
      : `${env.SUBJECT_PREFIX}${originalSubject}`;
    overrideHeaders.set("Subject", newSubject);

    // Stamp a custom header for audit trail
    overrideHeaders.set("X-Orchords-Original-To", message.to);
    overrideHeaders.set("X-Orchords-Original-From", message.from);
    overrideHeaders.set(
      "X-Orchords-Forwarded-At",
      new Date().toUTCString()
    );

    // --- Forward ---
    await message.forward(env.FORWARD_TO, overrideHeaders);
  },
};
```

## Section 3 — Local Testing & Deployment

```bash
# Install deps
npm install

# Type-check
npx tsc --noEmit

# Deploy to Cloudflare
npx wrangler deploy

# Tail live email logs
npx wrangler tail --format=pretty

# Send a test message via swaks (SMTP Swiss Army Knife)
swaks \
  --to catch-all@yourdomain.com \
  --from sender@example.com \
  --server mx1.yourdomain.com \
  --header 'Subject: Hello from swaks' \
  --body 'Test inbound email routing'
```

---

## Anti-patterns

- **Reading `raw` and re-encoding** — The `raw` stream can only be consumed once. If you tee it for logging, the forwarded copy will be empty. Use `message.forward()` directly.
- **Calling `setReject` after `forward`** — Once `forward()` resolves the SMTP transaction is committed; calling `setReject` afterward throws and is a no-op for delivery.
- **Overriding `From` in the forwarding headers** — Email providers perform SPF/DKIM alignment against the envelope `MAIL FROM`, not the RFC-5322 `From` header; rewriting it causes DMARC failures at the destination.

---

## Gotchas

- `message.headers` is read-only; pass mutation through the second argument of `forward()` instead.
- Email Routing Workers are bound to a specific route (address or catch-all) in the dashboard — a Worker not bound to the route never fires regardless of `wrangler.toml`.
- `rawSize` reports the MIME payload size in bytes; messages larger than 25 MB are rejected before the Worker runs.
- `forward()` is a `Promise` — you must `await` it or the runtime will terminate the Worker before delivery completes.

---

## Verification

```bash
# Check worker is deployed and bound
npx wrangler deployments list

# Inspect email event logs (last 100 lines)
npx wrangler tail --format=json | jq 'select(.type=="email")'

# Verify forwarded message arrived with mutated Subject
# (check internal-team@example.com mailbox for "[INBOUND] Hello from swaks")
```

---

## Related

- `workers-inbound-email-spam-filter-d1.md`
- `mailchannels-dkim-workers-email-auth.md`

---

## Sources

- Cloudflare Email Routing — https://developers.cloudflare.com/email-routing/
- EmailMessage API — https://developers.cloudflare.com/email-routing/email-workers/runtime-api/
- RFC 5321 SMTP — https://datatracker.ietf.org/doc/html/rfc5321
