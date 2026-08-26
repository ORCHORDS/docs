# DKIM-Signed Transactional Email via MailChannels in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Applications hosted on Cloudflare need to send transactional emails (receipts, magic links, notifications) without operating an SMTP server. MailChannels provides a native Workers integration that sends DKIM-signed mail over a simple HTTP API.

## Context
Cloudflare Workers can call the MailChannels `/tx/v1/send` endpoint using a standard `fetch()` call. MailChannels validates the sending domain via a DNS TXT record (`_mailchannels.yourdomain.com`) and applies DKIM signing using keys you publish. This eliminates the need for an SMTP library and provides SPF alignment because MailChannels IPs are covered by Cloudflare's SPF range when the TXT record is present.

## DNS Prerequisites

Before any code runs, publish two DNS records on the sending domain.

```
; Lock MailChannels to your zone so no other Worker can send as you
_mailchannels.yourdomain.com  TXT  "v=mc1 cfid=your-zone-subdomain.workers.dev"

; DKIM public key (2048-bit RSA, selector "mc1")
mc1._domainkey.yourdomain.com TXT  "v=DKIM1; k=rsa; p=MIIBIjANBg..."
```

The DKIM private key is stored as a Workers Secret (`DKIM_PRIVATE_KEY`) — never in source code.

## Building the MailChannels Payload

The `/tx/v1/send` endpoint accepts a JSON body. DKIM signing is requested by including the `dkim_*` fields.

```typescript
export interface Env {
  DKIM_PRIVATE_KEY: string;   // Base64-encoded PKCS#8 DER private key
  DKIM_SELECTOR: string;      // e.g. "mc1"
  SENDING_DOMAIN: string;     // e.g. "yourdomain.com"
}

interface MailChannelsPersonalization {
  to: { email: string; name?: string }[];
  dynamic_template_data?: Record<string, string>;
  subject?: string;
}

interface MailChannelsPayload {
  personalizations: MailChannelsPersonalization[];
  from: { email: string; name?: string };
  subject: string;
  content: { type: "text/plain" | "text/html"; value: string }[];
  dkim_domain: string;
  dkim_selector: string;
  dkim_private_key: string;
}

function buildPayload(
  to: string,
  toName: string,
  subject: string,
  html: string,
  text: string,
  env: Env
): MailChannelsPayload {
  return {
    personalizations: [{ to: [{ email: to, name: toName }] }],
    from: { email: `noreply@${env.SENDING_DOMAIN}`, name: "Orchords" },
    subject,
    content: [
      { type: "text/plain", value: text },
      { type: "text/html", value: html },
    ],
    dkim_domain: env.SENDING_DOMAIN,
    dkim_selector: env.DKIM_SELECTOR,
    dkim_private_key: env.DKIM_PRIVATE_KEY,
  };
}
```

## Sending the Email

Wrap the MailChannels `fetch` call with retry logic and structured error logging.

```typescript
const MAILCHANNELS_URL = "https://api.mailchannels.net/tx/v1/send";

async function sendEmail(
  payload: MailChannelsPayload
): Promise<{ success: boolean; error?: string }> {
  const response = await fetch(MAILCHANNELS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.status === 202) {
    return { success: true };
  }

  const errorBody = await response.text();
  console.error(JSON.stringify({
    event: "mailchannels_send_error",
    status: response.status,
    body: errorBody,
  }));
  return { success: false, error: errorBody };
}
```

## Worker Fetch Handler

Expose a POST endpoint that accepts a send request, validates the caller, and dispatches to MailChannels.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/send") {
      return new Response("Not Found", { status: 404 });
    }

    // Validate internal shared secret
    const authHeader = request.headers.get("Authorization") ?? "";
    if (authHeader !== `Bearer ${env.INTERNAL_API_KEY}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    const body = await request.json<{
      to: string;
      toName?: string;
      subject: string;
      html: string;
      text: string;
    }>();

    const payload = buildPayload(
      body.to,
      body.toName ?? "",
      body.subject,
      body.html,
      body.text,
      env
    );

    const result = await sendEmail(payload);
    if (!result.success) {
      return Response.json({ error: result.error }, { status: 502 });
    }
    return Response.json({ sent: true }, { status: 202 });
  },
};
```

## Dry-Run Mode for Testing

MailChannels supports a `dry_run` query parameter that validates the payload and checks DKIM without actually delivering the message.

```typescript
async function sendEmailDryRun(payload: MailChannelsPayload): Promise<Response> {
  return fetch(`${MAILCHANNELS_URL}?dry_run=true`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
```

## Anti-patterns
- Embedding the DKIM private key as a string literal in Worker source — use Workers Secrets
- Omitting `text/plain` content — spam filters penalise HTML-only messages with no plain-text alternative
- Setting `from.email` to a domain that does not have the `_mailchannels` TXT record — MailChannels will reject the send
- Reusing the same DKIM key across environments (staging/production) — rotate separately and use different selectors

## Gotchas
- MailChannels returns HTTP 202 for accepted sends, not 200; treat anything else as a failure
- The `dkim_private_key` field expects the key as a Base64-encoded string (the raw PEM body without headers, no newlines)
- Workers Secrets are available only in deployed Workers, not in `wrangler dev` without `--env` bindings; use a `.dev.vars` file locally
- The `_mailchannels` TXT record must match the subdomain of the Worker's `workers.dev` URL (or your custom domain's zone)

## Verification
1. Call the `/send` endpoint with `dry_run=true` — expect HTTP 200 with no delivery
2. Send a real message to a mailtest inbox (e.g., mail-tester.com) and verify DKIM `pass` in headers
3. Check DMARC alignment: `dkim_domain` must match the `From` header domain
4. Inspect MX Tool (mxtoolbox.com) → Email Header Analyzer on the delivered message

## Related
- `/documentation/docs/policies/email/cloudflare-email-routing.md`
- `/documentation/docs/policies/email/dkim-record-setup.md`
- `/documentation/docs/policies/email/dkim-selector-rollover-and-key-strength.md`
- `/documentation/docs/policies/email/spf-dkim-dmarc-alignment-debugging-workers.md`

## Sources
- MailChannels Send API: https://api.mailchannels.net/tx/v1/documentation
- Cloudflare Blog — Send Email from Workers: https://blog.cloudflare.com/sending-email-from-workers-with-mailchannels/
- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- RFC 6376 — DKIM Signatures
