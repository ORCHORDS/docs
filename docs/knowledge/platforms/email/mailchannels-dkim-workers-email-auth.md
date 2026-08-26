# DKIM Authentication for MailChannels Emails Sent via Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Transactional emails sent from a Worker via MailChannels arrive in recipients' spam folders or show "via mailchannels.net" in Gmail because the sending domain is not DKIM-signed. Adding a `mailchannels._domainkey` TXT record and the appropriate request headers enables DKIM signing, aligns SPF, and causes email clients to show your domain as the verified sender.

---

## Context

MailChannels provides a free email sending API accessible from Cloudflare Workers at `https://api.mailchannels.net/tx/v1/send`. Without DKIM the sending IP is authenticated by SPF only through MailChannels' shared IP pool, which yields mediocre deliverability. Adding your domain's DKIM public key as a DNS TXT record at `mailchannels._domainkey.<yourdomain>` and passing `X-MailChannels-Signing-Domain` plus `X-MailChannels-Track-Opens` in the JSON payload body tells MailChannels to sign outgoing messages with your private key. The private key is stored as a Cloudflare Worker Secret (base64-encoded PKCS#8). SPF alignment is achieved by setting `sender.address` to an address on your domain so the RFC-5321 `MAIL FROM` and the RFC-5322 `From` share the same organizational domain.

---

## Section 1 — DNS & Key Generation

```bash
# Generate a 2048-bit RSA key pair (PKCS#8 PEM)
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out dkim_private.pem

openssl pkey -in dkim_private.pem -pubout -out dkim_public.pem

# Extract the raw base64 public key (strip PEM headers, collapse newlines)
PUB_KEY=$(openssl pkey -in dkim_private.pem -pubout -outform DER \
  | base64 | tr -d '\n')

echo "DNS TXT record value:"
echo "v=DKIM1; p=${PUB_KEY}"

# Add the following DNS TXT record in Cloudflare Dashboard or via API:
# Name:  mailchannels._domainkey.yourdomain.com
# Type:  TXT
# Value: v=DKIM1; p=<base64-public-key>

# Store private key as a Worker Secret (base64-encoded)
PRIV_B64=$(base64 -w 0 dkim_private.pem)
npx wrangler secret put DKIM_PRIVATE_KEY <<< "$PRIV_B64"
```

```toml
# wrangler.toml
name = "email-sender-dkim"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
SENDING_DOMAIN = "example.com"
DKIM_SELECTOR  = "mailchannels"
```

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  SENDING_DOMAIN: string;
  DKIM_SELECTOR: string;
  DKIM_PRIVATE_KEY: string; // base64-encoded PKCS#8 PEM, stored as secret
}

interface MailChannelsPayload {
  personalizations: Array<{
    to: Array<{ email: string; name?: string }>;
    dkim_domain?: string;
    dkim_selector?: string;
    dkim_private_key?: string;
  }>;
  from: { email: string; name?: string };
  subject: string;
  content: Array<{ type: string; value: string }>;
}

async function sendEmail(
  env: Env,
  to: string,
  subject: string,
  html: string
): Promise<Response> {
  const payload: MailChannelsPayload = {
    personalizations: [
      {
        to: [{ email: to }],
        // DKIM signing parameters per recipient group
        dkim_domain: env.SENDING_DOMAIN,
        dkim_selector: env.DKIM_SELECTOR,
        dkim_private_key: env.DKIM_PRIVATE_KEY, // base64 PEM
      },
    ],
    from: {
      email: `noreply@${env.SENDING_DOMAIN}`,
      name: "Orchords",
    },
    subject,
    content: [{ type: "text/html", value: html }],
  };

  return fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // Optional: enable open tracking pixel injection
      "X-MailChannels-Track-Opens": "true",
    },
    body: JSON.stringify(payload),
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { to, subject, html } = await request.json<{
      to: string;
      subject: string;
      html: string;
    }>();

    const res = await sendEmail(env, to, subject, html);

    if (!res.ok) {
      const body = await res.text();
      return new Response(`MailChannels error: ${body}`, { status: 502 });
    }

    return new Response(JSON.stringify({ status: "sent" }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Section 3 — DKIM & SPF Verification

```bash
# Verify DNS TXT record is live
dig TXT mailchannels._domainkey.example.com +short
# Should return: "v=DKIM1; p=<your-public-key>"

# Send a test email via the deployed Worker
curl -X POST https://email-sender-dkim.<account>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"to":"test@mail-tester.com","subject":"DKIM test","html":"<p>Hello</p>"}'

# Check mail-tester.com score — should show:
# DKIM: pass (mailchannels selector)
# SPF:  pass (aligned to example.com)
# DMARC: pass

# Inspect raw email headers in Gmail:
# Authentication-Results: mx.google.com;
#   dkim=pass header.i=@example.com header.s=mailchannels
#   spf=pass smtp.mailfrom=noreply@example.com
```

---

## Anti-patterns

- **Putting the private key in `[vars]`** — `[vars]` values are visible in plain text in `wrangler.toml` and the Cloudflare dashboard; always use `wrangler secret put` for cryptographic material.
- **Using a 1024-bit key** — Major providers (Gmail, Yahoo) now reject or downgrade DKIM signatures using RSA-1024; use 2048-bit minimum.
- **Mismatched `dkim_domain` and `From` domain** — DMARC alignment requires the `dkim_domain` in the payload to match the organizational domain of the `From` header; a mismatch causes a DMARC policy failure.

---

## Gotchas

- MailChannels requires the private key in the `personalizations` array, not as a top-level field — placing it at the root silently sends unsigned mail.
- DNS propagation of the TXT record can take up to 48 hours; verify with `dig` before testing deliverability scores.
- `X-MailChannels-Track-Opens` injects a 1x1 pixel which some privacy-focused clients (Apple Mail Privacy Protection) will pre-fetch, inflating open rates — disable if open metrics are not needed.
- MailChannels rate-limits free-tier usage to 100 emails per day per Cloudflare account; plan accordingly for production volumes.

---

## Verification

```bash
# Check DKIM record propagation
nslookup -type=TXT mailchannels._domainkey.example.com 1.1.1.1

# Use mail-tester.com for a comprehensive score
curl -X POST https://email-sender-dkim.<account>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"to":"your-unique-id@srv1.mail-tester.com","subject":"DKIM check","html":"<p>test</p>"}'

# Verify DKIM pass in Gmail raw headers
# Open email → "Show original" → look for dkim=pass
```

---

## Related

- `workers-email-routing-forward-transform.md`
- `workers-email-template-r2-handlebars.md`

---

## Sources

- MailChannels DKIM guide — https://support.mailchannels.com/hc/en-us/articles/7122849237389-Adding-a-DKIM-Signature
- Cloudflare Workers Secrets — https://developers.cloudflare.com/workers/configuration/secrets/
- RFC 6376 DKIM — https://datatracker.ietf.org/doc/html/rfc6376
