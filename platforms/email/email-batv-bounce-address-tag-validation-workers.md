# Email BATV (Bounce Address Tag Validation) Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your shared sending infrastructure receives thousands of bounce messages (NDRs) daily,
but a growing fraction are **backscatter**: bounces for mail your system never sent.
SPF and DMARC protect recipients from spoofing but do nothing to stop a third-party
spammer forging `MAIL FROM:<bounces@yourdomain.com>`. Every forged bounce lands in
your bounce-handler queue, pollutes metrics, and inflates suppression lists with
innocent addresses.

BATV (Bounce Address Tag Validation) fixes this by cryptographically tagging the
envelope `MAIL FROM` address at send time. On return, any bounce carrying an
unrecognisable or expired tag is silently discarded.

---

## Context

BATV is documented in the IETF draft `draft-levine-smtp-batv` (never standardised
as an RFC but widely implemented). It differs from SRS (Sender Rewriting Scheme):

| Concern | SRS | BATV |
|---|---|---|
| Problem solved | SPF break on forward | Backscatter from forged MAIL FROM |
| When applied | Forwarder rewrites sender | Originating MTA tags sender |
| Address format | `SRS0=hash=TT=domain=user@relay` | `prvs=YYYYMMDD+hash=user@domain` |
| Who validates | Next-hop receiver | Originating MTA on bounce return |

The BATV-tagged envelope sender looks like:

```
MAIL FROM:<prvs=0823a1b2c3d4/orders@shop.example.com>
```

Components:
- `prvs=` — fixed BATV scheme prefix
- `0823` — 4-digit date tag (`MMDD`)
- `a1b2c3d4` — 8 hex chars of HMAC-SHA1 truncated over `(key, date, localpart@domain)`
- `/orders@shop.example.com` — original address with `/` separator

Bounces are delivered to a wildcard address handler that strips and validates the tag.

---

## Workers Architecture

```
Outbound send path:
  Worker (send)  →  tag MAIL FROM  →  MailChannels / SES / Postmark

Inbound bounce path:
  Cloudflare Email Routing  →  catch-all Worker  →  validate tag  →
    valid   → process bounce (suppress / log)
    invalid → discard silently
```

Store the signing secret in **Workers Secrets** (never in source code or KV plain text).

---

## Implementation

### Signing the Outbound Envelope Sender

```typescript
// batv.ts

const BATV_PREFIX = "prvs";
const TAG_VALID_DAYS = 7; // reject bounces older than 7 days

function mmdd(): string {
  const d = new Date();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${mm}${dd}`;
}

async function hmacHex(
  secret: string,
  message: string
): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-1" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 8); // truncate to 8 hex chars
}

export async function baTVTag(
  localpart: string,
  domain: string,
  secret: string
): Promise<string> {
  const date = mmdd();
  const tag = await hmacHex(secret, `${date}/${localpart}@${domain}`);
  return `${BATV_PREFIX}=${date}${tag}/${localpart}@${domain}`;
}
```

### Validating an Incoming Bounce

```typescript
// batv-validate.ts

export interface BATVResult {
  valid: boolean;
  reason?: string;
  originalAddress?: string;
}

export async function validateBATVAddress(
  envelopeFrom: string,
  secret: string
): Promise<BATVResult> {
  // Strip angle brackets if present
  const addr = envelopeFrom.replace(/^<|>$/g, "");

  if (!addr.startsWith("prvs=")) {
    return { valid: false, reason: "not-batv" };
  }

  // prvs=MMDDhhhhhhhh/localpart@domain
  const rest = addr.slice(5); // strip "prvs="
  const slashIdx = rest.indexOf("/");
  if (slashIdx < 12) {
    return { valid: false, reason: "malformed" };
  }

  const dateTag = rest.slice(0, 4);        // MMDD
  const hashTag = rest.slice(4, 12);       // 8 hex chars
  const original = rest.slice(slashIdx + 1); // localpart@domain

  const atIdx = original.lastIndexOf("@");
  if (atIdx < 1) return { valid: false, reason: "malformed-original" };
  const localpart = original.slice(0, atIdx);
  const domain = original.slice(atIdx + 1);

  // Re-derive expected hash
  const expected = await hmacHex(secret, `${dateTag}/${localpart}@${domain}`);
  if (expected !== hashTag) {
    return { valid: false, reason: "bad-hash" };
  }

  // Check date freshness (MMDD — handle year-boundary wrap)
  const now = new Date();
  const tagMM = parseInt(dateTag.slice(0, 2), 10);
  const tagDD = parseInt(dateTag.slice(2, 4), 10);
  const tagDate = new Date(
    Date.UTC(now.getUTCFullYear(), tagMM - 1, tagDD)
  );
  // If tagDate is in the future (just ticked over year), subtract a year
  if (tagDate > now) tagDate.setUTCFullYear(tagDate.getUTCFullYear() - 1);
  const ageDays = (now.getTime() - tagDate.getTime()) / 86_400_000;

  if (ageDays > TAG_VALID_DAYS) {
    return { valid: false, reason: "expired", originalAddress: original };
  }

  return { valid: true, originalAddress: original };
}

// Re-export hmacHex for use in baTVTag
async function hmacHex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret),
    { name: "HMAC", hash: "SHA-1" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("").slice(0, 8);
}
```

### Cloudflare Email Workers Bounce Handler

```typescript
// worker.ts  (email worker on catch-all for bounces+.*)
import { validateBATVAddress } from "./batv-validate";

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const envelopeFrom = message.from; // SMTP MAIL FROM (not header From)

    const result = await validateBATVAddress(envelopeFrom, env.BATV_SECRET);

    if (!result.valid) {
      // Silently drop: backscatter or replay attempt
      console.log(`BATV reject: ${result.reason} for <${envelopeFrom}>`);
      message.setReject(`BATV validation failed: ${result.reason}`);
      return;
    }

    // Legitimate bounce — process against the original address
    const original = result.originalAddress!;
    await env.DB.prepare(
      `INSERT OR IGNORE INTO suppression (email, reason, created_at)
       VALUES (?, 'hard-bounce', unixepoch())`
    ).bind(original).run();

    console.log(`BATV valid bounce for <${original}>, suppressed.`);
  },
};

interface Env {
  BATV_SECRET: string;
  DB: D1Database;
}
```

### Integrating BATV into the Send Path

```typescript
// send.ts
import { baTVTag } from "./batv";

export async function sendTransactional(
  to: string,
  subject: string,
  html: string,
  env: Env
): Promise<void> {
  const from = "orders@shop.example.com";
  const [localpart, domain] = from.split("@");
  const batvFrom = await baTVTag(localpart, domain, env.BATV_SECRET);

  await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: from },           // Header From unchanged
      envelope_from: batvFrom,         // SMTP MAIL FROM tagged
      subject,
      content: [{ type: "text/html", value: html }],
    }),
  });
}
```

---

## Anti-patterns

- **Reusing a single static tag** — the date component and HMAC must be recomputed per
  message. A static tag defeats expiry protection.
- **Using SHA-256 full output** — BATV spec uses 8 hex chars (4 bytes). Longer tags
  break the address format parsers of receiving MTAs.
- **Storing the secret in KV** — KV is readable by anyone with account access. Use
  Workers Secrets (`wrangler secret put BATV_SECRET`).
- **Only tagging transactional, not marketing** — spammers can still forge your marketing
  address. Tag all outbound streams or use a dedicated bounce domain.
- **Forgetting the wildcard MX / Email Routing rule** — the catch-all route
  `prvs=*@shop.example.com` must be configured in Cloudflare Email Routing to reach
  your bounce-handler Worker.

---

## Gotchas

- Some ESPs set the SMTP `MAIL FROM` independently of the `From:` header. Confirm
  your ESP allows overriding the envelope sender (MailChannels: `envelope_from` field;
  SES: `ReturnPath`; SendGrid: `return_path` in personalizations).
- BATV breaks if your ESP changes the local part (e.g., bounce ID prepending). Audit
  what lands in your bounce inbox before enabling silently-drop mode.
- Year-boundary wraps (e.g., tag date `1231` and today is `0101`) require the age
  calculation to subtract a year when the computed tag date is in the future.
- RFC 5321 limits the MAIL FROM path to 256 octets. Tagged addresses for very long
  local parts may exceed this; cap local parts at 64 chars before tagging.

---

## Verification

```bash
# Send a test message and capture the BATV-tagged MAIL FROM in the bounce handler logs
wrangler tail --format pretty

# Force a bounce (send to an RFC 5321 black-hole address) and watch for:
# "BATV valid bounce for <orders@shop.example.com>, suppressed."

# Test an invalid tag directly:
curl -X POST https://bounce.shop.example.com/__test \
  -d '{"from":"prvs=0101deadbeef/orders@shop.example.com"}'
# Expect: { valid: false, reason: "bad-hash" }
```

---

## Related

- `email-bounce-suppression-d1.md` — D1 suppression list schema
- `email-forwarding-spf-alignment-srs-workers.md` — SRS for forwarding chains
- `verp-bounce-addressing.md` — per-recipient envelope addressing
- `email-transactional-dead-letter-queue-workers.md` — dead-letter handling

---

## Sources

- draft-levine-smtp-batv-03 — BATV specification
- RFC 5321 §4.5.5 — bounce address constraints
- Cloudflare Email Routing Workers docs — `message.setReject()`
- MailChannels TX API — `envelope_from` field
