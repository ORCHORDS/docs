# Email Footer Compliance Auto-Injection via Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your marketing team sends transactional and bulk emails through multiple services (MailChannels, Resend, SendGrid) and compliance footers — physical address, unsubscribe link, CASL consent notice — are sometimes missing, wrong, or vary across templates. Legal requires every outbound email to carry an identical, audited footer regardless of which developer touched the template last.

## Context

CAN-SPAM (US) requires every commercial email to include a valid physical postal address and a functional opt-out mechanism. CASL (Canada) adds an identification block naming the sender and the entity on whose behalf the email is sent. GDPR-adjacent regulations in the EU require similar disclosures for direct marketing. Enforcing this at the template level relies on discipline; enforcing it at the transport layer — a Cloudflare Email Worker that sits in front of every outgoing SMTP call — is deterministic and auditable. The Worker intercepts the outgoing `EmailMessage`, parses the MIME body, and splices a canonical footer into both the `text/plain` and `text/html` MIME parts before forwarding.

## 1. Worker Architecture

The Email Worker receives outbound messages via the `email` handler (Cloudflare Email Routing, send direction). It must:

1. Parse the raw MIME message.
2. Locate `text/plain` and `text/html` parts.
3. Append the compliance footer to each.
4. Re-serialise and forward.

```typescript
// src/index.ts
import { EmailMessage } from "cloudflare:email";
import { createMimeMessage } from "mimetext"; // vendored / inlined

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    const raw = await streamToArrayBuffer(message.raw);
    const patched = await injectFooter(raw, env);
    const forward = new EmailMessage(message.from, message.to, patched);
    await message.forward(env.DESTINATION_ADDRESS, [forward.headers]);
  },
};

async function streamToArrayBuffer(stream: ReadableStream): Promise<ArrayBuffer> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  const total = chunks.reduce((n, c) => n + c.byteLength, 0);
  const buf = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { buf.set(chunk, offset); offset += chunk.byteLength; }
  return buf.buffer;
}
```

## 2. MIME Part Injection

Because Workers run in a V8 isolate without native Node MIME libraries, use a minimal boundary-aware string replacement:

```typescript
async function injectFooter(raw: ArrayBuffer, env: Env): Promise<ArrayBuffer> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let body = decoder.decode(raw);

  const plainFooter = buildPlainFooter(env);
  const htmlFooter  = buildHtmlFooter(env);

  // Append to text/plain part before next boundary
  body = body.replace(
    /(Content-Type: text\/plain[\s\S]*?\r\n\r\n)([\s\S]*?)(\r\n--)/g,
    (_, header, content, boundary) =>
      `${header}${content}\r\n\r\n${plainFooter}${boundary}`
  );

  // Append to text/html part before next boundary
  body = body.replace(
    /(Content-Type: text\/html[\s\S]*?\r\n\r\n)([\s\S]*?)(<\/body>)/gi,
    (_, header, content) =>
      `${header}${content}${htmlFooter}</body>`
  );

  return encoder.encode(body).buffer;
}
```

## 3. Footer Builder — CAN-SPAM + CASL Fields

Store footer variables in Worker secrets / KV so legal can update them without code deploys:

```typescript
interface Env {
  FOOTER_KV: KVNamespace;
  DESTINATION_ADDRESS: string;
}

async function getFooterConfig(env: Env) {
  const [address, orgName, unsubUrl, caslId] = await Promise.all([
    env.FOOTER_KV.get("physical_address"),
    env.FOOTER_KV.get("org_name"),
    env.FOOTER_KV.get("unsub_url"),
    env.FOOTER_KV.get("casl_sender_id"),
  ]);
  return { address, orgName, unsubUrl, caslId };
}

function buildPlainFooter(config: ReturnType<typeof getFooterConfig> extends Promise<infer T> ? T : never): string {
  return [
    "---",
    `Sent by ${config.orgName} | ${config.address}`,
    `Unsubscribe: ${config.unsubUrl}`,
    `CASL sender ID: ${config.caslId}`,
  ].join("\n");
}

function buildHtmlFooter(config: ReturnType<typeof getFooterConfig> extends Promise<infer T> ? T : never): string {
  return `
<table role="presentation" width="100%" style="font-size:11px;color:#666;border-top:1px solid #e0e0e0;margin-top:24px;padding-top:12px;">
  <tr><td>
    &copy; ${new Date().getFullYear()} ${config.orgName} &bull; ${config.address}<br>
    <a  style="color:#666;">Unsubscribe</a>
    &bull; CASL sender ID: ${config.caslId}
  </td></tr>
</table>`;
}
```

## 4. Idempotency Guard

Prevent double-injection when the Worker processes a message that already has the footer (e.g., retry paths):

```typescript
const FOOTER_SENTINEL = "<!-- cfooter-injected -->";

function alreadyInjected(body: string): boolean {
  return body.includes(FOOTER_SENTINEL);
}

// Prepend sentinel to htmlFooter
function buildHtmlFooter(...) {
  return `${FOOTER_SENTINEL}\n<table ...>...</table>`;
}
```

## 5. KV Seed Script

Use Wrangler to seed footer values from a JSON file so the compliance team can manage it without touching TypeScript:

```typescript
// scripts/seed-footer.ts
import { execSync } from "node:child_process";
import footer from "../config/footer.json";

for (const [key, value] of Object.entries(footer)) {
  execSync(`npx wrangler kv key put --namespace-id $FOOTER_NS_ID "${key}" "${value}"`);
  console.log(`seeded ${key}`);
}
```

```json
// config/footer.json
{
  "physical_address": "123 Main St, Suite 400, San Francisco CA 94105",
  "org_name": "Acme Corp",
  "unsub_url": "https://app.example.com/unsubscribe?token=<redacted-secret>
  "casl_sender_id": "acme-corp-ca-2024"
}
```

## Anti-patterns

- **Template-level footers only** — developers forget, templates drift, and A/B variants omit the footer entirely.
- **String concatenation without MIME awareness** — appending to the raw body without finding the correct part boundary corrupts the MIME structure and triggers spam filters.
- **Hardcoding the address in source code** — legal address changes require code deploys and create audit gaps.
- **Skipping the plain-text part** — CAN-SPAM applies to the message, not just the HTML part; plain-text-only clients must also see the footer.

## Gotchas

- **Base64-encoded parts** — if the original `text/html` body is `Content-Transfer-Encoding: base64`, you must decode → inject → re-encode; the regex above only handles `7bit`/`quoted-printable`. Check the Content-Transfer-Encoding header before applying.
- **Single-part messages** — messages without a `multipart/alternative` wrapper need a different injection path; check `Content-Type` of the root message first.
- **Token substitution** — `{{unsub_token}}` in the KV value must be replaced per-recipient before injection; pass recipient metadata through a request header or encode it in the `To` address local part.
- **DKIM re-signing** — injecting content after DKIM signing breaks the signature. Inject before the signing step, or use MailChannels' DKIM-at-edge which signs after your Worker runs.

## Verification

```bash
# Send a test message through the Worker pipeline
echo "Subject: Test\r\nFrom: test@example.com\r\nTo: probe@yourtest.com\r\n\r\nHello" | \
  curl -X POST https://api.mailchannels.net/tx/v1/send \
  -H "Content-Type: application/json" \
  -d @test-payload.json

# Inspect the received message for footer sentinel
curl -s https://probe.yourtest.com/latest | grep "cfooter-injected"

# Validate CAN-SPAM fields present
curl -s https://probe.yourtest.com/latest | grep -E "Unsubscribe|physical_address"
```

Run a monthly compliance audit by querying Analytics Engine for messages where the sentinel was absent (injector bypassed):

```typescript
const result = await env.AE.query(
  `SELECT count() FROM email_events WHERE footer_injected = 0 AND date > now() - INTERVAL '30' DAY`
);
```

## Related

- `one-click-unsubscribe-rfc8058-gdpr.md`
- `can-spam-compliance.md`
- `casl-canada-compliance.md`
- `cloudflare-email-routing-workers.md`
- `email-dkim-signing-mailchannels-workers.md`

## Sources

- CAN-SPAM Act: https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- CASL text: https://laws-lois.justice.gc.ca/eng/acts/E-1.6/
- Cloudflare Email Workers docs: https://developers.cloudflare.com/email-routing/email-workers/
- Cloudflare KV: https://developers.cloudflare.com/kv/
