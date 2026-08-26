# Email Forwarding SPF Alignment and SRS Rewriting on Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

When Cloudflare Email Routing forwards a message to an external mailbox (Gmail, Outlook),
the envelope `MAIL FROM` domain no longer matches the sending IP, causing SPF to fail at
the final destination. Without Sender Rewriting Scheme (SRS) the forwarded message arrives
with a broken SPF result, which — when the original sender has a strict DMARC policy —
leads to the forwarded copy being rejected or quarantined silently.

## Context

SPF authenticates the envelope sender against the IP address that delivered the message.
When Cloudflare's forwarding infrastructure re-injects the message, the envelope
`MAIL FROM` still carries the original sender's domain, but the delivering IP belongs to
Cloudflare. The original sender's SPF record does not list Cloudflare, so SPF fails.
SRS rewrites the `MAIL FROM` to `SRS0=<hash>=<timestamp>=<original-domain>=<local-part>@<forwarding-domain>`,
making SPF pass against the forwarding domain's record. DKIM on the original message is
preserved through the forwarding hop, giving DMARC a passing signal via DKIM alignment
even when SPF alignment fails.

## Implementing SRS Rewriting in a Forwarding Worker

```typescript
import { createHmac } from "node:crypto";

export interface Env {
  SRS_SECRET: string;          // HMAC key stored as a Workers secret
  SRS_DOMAIN: string;          // e.g. "forward.acme.example"
  FORWARD_DESTINATION: string; // e.g. "user@gmail.com"
}

// SRS0 timestamp: days since epoch mod 1024, base32-encoded (simplified).
const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function srsTimestamp(): string {
  const days = Math.floor(Date.now() / 86_400_000) % 1024;
  return BASE32[Math.floor(days / 32)] + BASE32[days % 32];
}

function srsHash(secret: string, timestamp: string, domain: string, local: string): string {
  const hmac = createHmac("sha256", secret);
  hmac.update(`${timestamp}${domain}${local}`);
  // Truncate to first 4 base32 chars (20-bit hash, common SRS implementations).
  const hex = hmac.digest("hex");
  let hash = "";
  for (let i = 0; i < 4; i++) {
    hash += BASE32[parseInt(hex.slice(i * 2, i * 2 + 2), 16) % 32];
  }
  return hash;
}

export function buildSrsAddress(
  originalFrom: string,
  srsDomain: string,
  secret: string
): string {
  const atIdx = originalFrom.lastIndexOf("@");
  const localPart = originalFrom.slice(0, atIdx);
  const fromDomain = originalFrom.slice(atIdx + 1);

  const ts = srsTimestamp();
  const hash = srsHash(secret, ts, fromDomain, localPart);

  // SRS0=HASH=TT=ORIGINAL-DOMAIN=LOCAL-PART@SRS-DOMAIN
  return `SRS0=${hash}=${ts}=${fromDomain}=${localPart}@${srsDomain}`;
}

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const srsFrom = buildSrsAddress(
      message.from,
      env.SRS_DOMAIN,
      env.SRS_SECRET
    );

    // Cloudflare Email Routing's forward() does not currently accept a custom
    // envelope MAIL FROM; use a Resend / MailChannels send call to re-inject
    // with the SRS address as the envelope sender.
    const raw = await new Response(message.raw).text();

    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${(env as any).RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: srsFrom,
        to: [env.FORWARD_DESTINATION],
        // Pass the raw RFC 5322 message as-is to preserve DKIM.
        raw,
      }),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Forward failed (${response.status}): ${body}`);
    }
  },
};
```

## SPF DNS Record for the SRS Domain

The SRS domain needs its own SPF record that authorises the re-injection path (Resend,
MailChannels, or your own IP range).

```typescript
// Verify that forward.acme.example has a valid SPF record.
// Example TXT record (add via Cloudflare DNS API or dashboard):
// forward.acme.example. 300 IN TXT "v=spf1 include:_spf.resend.com ~all"

// Workers: look up the SPF record at startup for sanity-checking.
async function verifySrsDomainSpf(srsDomain: string): Promise<boolean> {
  const resp = await fetch(
    `https://cloudflare-dns.com/dns-query?name=${srsDomain}&type=TXT`,
    { headers: { Accept: "application/dns-json" } }
  );
  const data = (await resp.json()) as { Answer?: { data: string }[] };
  return (data.Answer ?? []).some(
    (r) => r.data.includes("v=spf1") && r.data.includes("include:")
  );
}
```

## Reverse SRS Lookup for Bounces

Bounces from the destination mailbox arrive at the SRS address
(`SRS0=...@forward.acme.example`). A second inbound Worker parses the SRS tag, verifies
the HMAC, and re-delivers the DSN to the original sender.

```typescript
export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const localPart = message.to.split("@")[0]; // e.g. SRS0=ABCD=AB=example.com=alice

    if (!localPart.startsWith("SRS0=")) {
      // Not an SRS bounce; discard or handle normally.
      message.setReject("Not an SRS address");
      return;
    }

    const parts = localPart.split("=");
    // parts: ["SRS0", hash, ts, originalDomain, originalLocal]
    const [, receivedHash, ts, originalDomain, originalLocal] = parts;
    const expectedHash = srsHash(env.SRS_SECRET, ts, originalDomain, originalLocal);

    if (receivedHash !== expectedHash) {
      message.setReject("Invalid SRS signature");
      return;
    }

    const originalAddress = `${originalLocal}@${originalDomain}`;
    await message.forward(originalAddress);
  },
};
```

## Anti-patterns

- Relying solely on DKIM alignment instead of implementing SRS — if the original sender
  re-signs after the DKIM signature window (usually 5 days), DMARC will fail on both axes.
- Using a static hard-coded SRS hash — without a timestamp and HMAC the SRS address is
  trivially forged and will be used to generate bounce spam (backscatter).
- Setting `v=spf1 +all` on the SRS domain as a quick fix — this authorises every IP on
  the internet to send as your forwarding domain.

## Gotchas

- Cloudflare Email Routing's built-in `message.forward()` does not expose envelope MAIL
  FROM rewriting; to implement SRS you must re-inject the message through an ESP that
  accepts a custom `from` envelope address (Resend, MailChannels, or a self-hosted MTA).
- The SRS timestamp uses a modular day counter; SRS bounce addresses are valid for a
  configurable window (typically 21 days). Bounces arriving after expiry must be rejected
  without backscatter.
- Quoted-printable and base64 encoded DKIM bodies must pass through untouched; never
  re-encode the raw RFC 5322 message before re-injection.

## Verification

```bash
# Send a test message from a domain with strict DMARC (p=reject) through your forwarder.
swaks --to forward.acme.example --from test@dmarc-strict.example \
  --server mx1.cloudflare.com

# Check headers in the destination inbox for SPF result on the SRS domain.
# Expected: Received-SPF: pass (forward.acme.example: ...)

# Verify SRS bounce handling by sending a DSN to the SRS address.
echo "" | mail -s "Delivery failure" SRS0=ABCD=AB=dmarc-strict.example=test@forward.acme.example
```

## Related

- `email/email-forwarding-setup.md`
- `email/spf-record-setup.md`
- `email/srs-sender-rewriting-scheme.md`
- `email/arc-authenticated-received-chain.md`

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/
- https://www.ietf.org/rfc/rfc7208.txt
- https://srs.sourceforge.net/srs.pdf
- https://datatracker.ietf.org/doc/html/rfc5321#section-4.1.1.2
