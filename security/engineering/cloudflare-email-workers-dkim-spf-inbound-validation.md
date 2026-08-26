# Cloudflare Email Workers Inbound DKIM/SPF Validation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your application receives inbound email via Cloudflare Email Routing and processes it inside a Worker (e.g. support tickets, webhook-style notifications, automated commands). Without explicit SPF/DKIM/DMARC verification at the Worker boundary, spoofed senders can bypass business logic, trigger privileged actions, or inject malicious content into D1/R2 pipelines.

## Context

Cloudflare Email Workers receive a `ForwardableEmailMessage` on the `email` handler. The runtime exposes SPF and DKIM results on `message.headers` but does NOT enforce DMARC or reject unauthenticated mail on your behalf — that decision belongs to the Worker. An attacker who knows your inbound address can craft a message with a spoofed `From:` header and have it delivered unless you gate on the authentication headers.

RFC 7601 defines the `Authentication-Results` header injected by Cloudflare's mail infrastructure; its values are the authoritative signal you can trust because they are set by the MX hop before your Worker sees the message.

---

## 1. Reading Authentication-Results in Email Workers

```typescript
export default {
  async email(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext) {
    const authResults = message.headers.get("Authentication-Results") ?? "";
    const spfPass  = /spf=pass/i.test(authResults);
    const dkimPass = /dkim=pass/i.test(authResults);
    const dmarcPass = /dmarc=pass/i.test(authResults);

    if (!spfPass || !dkimPass) {
      // Reject: drop the message without forwarding
      message.setReject("Unauthenticated sender — message rejected.");
      return;
    }

    await processInboundEmail(message, env);
  },
};
```

The `setReject()` call generates a permanent 5xx SMTP rejection; the sending MTA receives a non-delivery report and will not retry.

---

## 2. Parsing Multi-Record Authentication-Results Safely

Real `Authentication-Results` headers can contain multiple semicolon-separated results from different verifiers. Parse them structurally rather than with a single regex over the entire header value.

```typescript
function parseAuthResults(header: string): Record<string, string> {
  const results: Record<string, string> = {};
  // Strip the authserv-id (first token before semicolon)
  const body = header.replace(/^[^;]+;/, "");
  for (const segment of body.split(";")) {
    const match = segment.trim().match(/^(\w+)=(\w+)/);
    if (match) results[match[1].toLowerCase()] = match[2].toLowerCase();
  }
  return results;
}

export default {
  async email(message: ForwardableEmailMessage, env: Env, _ctx: ExecutionContext) {
    const ar = parseAuthResults(message.headers.get("Authentication-Results") ?? "");

    if (ar["dkim"] !== "pass" || ar["spf"] !== "pass") {
      message.setReject("Authentication failure.");
      return;
    }

    // Optional: enforce strict DMARC pass for high-privilege inbound addresses
    if (env.REQUIRE_DMARC === "true" && ar["dmarc"] !== "pass") {
      message.setReject("DMARC policy violation.");
      return;
    }

    await processInboundEmail(message, env);
  },
};
```

---

## 3. Allowlisting Verified Sender Domains

Even with DKIM/SPF passing, pin the `From:` domain to an explicit allowlist stored in KV to prevent legitimate-but-unexpected senders from triggering privileged flows.

```typescript
async function isTrustedSender(from: string, env: Env): Promise<boolean> {
  const domain = from.split("@")[1]?.toLowerCase();
  if (!domain) return false;
  const allowed = await env.TRUSTED_DOMAINS_KV.get(domain);
  return allowed !== null;
}

export default {
  async email(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext) {
    const ar = parseAuthResults(message.headers.get("Authentication-Results") ?? "");
    if (ar["dkim"] !== "pass" || ar["spf"] !== "pass") {
      message.setReject("Unauthenticated sender.");
      return;
    }

    const trusted = await isTrustedSender(message.from, env);
    if (!trusted) {
      // Forward to a human review queue rather than silently dropping
      await message.forward(env.REVIEW_MAILBOX);
      return;
    }

    await processInboundEmail(message, env);
  },
};
```

KV key: `allowed-domains/<domain>`, value: JSON metadata (`{"added":"2026-08-23","by":"ops"}`).

---

## 4. Logging Rejected Email to D1 for Audit

```typescript
async function logRejection(
  message: ForwardableEmailMessage,
  reason: string,
  env: Env,
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO email_rejections (from_addr, subject, reason, ts)
     VALUES (?, ?, ?, ?)`,
  ).bind(
    message.from,
    message.headers.get("Subject") ?? "(none)",
    reason,
    new Date().toISOString(),
  ).run();
}
```

Never log full email body to D1 — store only headers and rejection metadata to avoid PII accumulation.

---

## 5. Rate-Limiting Inbound Email by Sender IP via D1

Cloudflare's Email Routing does not expose the originating IP in `message` today, but the `Received:` chain is available in raw headers. Extract the last external IP for abuse counting.

```typescript
function extractOriginatingIP(receivedHeaders: string[]): string | null {
  // The last Received: header is closest to the originating MTA
  const last = receivedHeaders[receivedHeaders.length - 1] ?? "";
  const match = last.match(/from\s+\S+\s+\((\d{1,3}(?:\.\d{1,3}){3})\)/);
  return match ? match[1] : null;
}

async function isRateLimited(ip: string, env: Env): Promise<boolean> {
  const key = `email_rate:${ip}`;
  const count = parseInt((await env.RATE_KV.get(key)) ?? "0", 10);
  if (count >= 20) return true;
  await env.RATE_KV.put(key, String(count + 1), { expirationTtl: 3600 });
  return false;
}
```

---

## Anti-patterns

- **Trusting `From:` header alone** — trivially spoofed; always verify `Authentication-Results`.
- **Accepting `dkim=pass` with `spf=fail`** — partial pass enables domain spoofing via third-party relay abuse; require both.
- **Forwarding all mail to another address** — every forwarded message incurs delivery cost and can leak PII if the destination is uncontrolled.
- **Parsing `Authentication-Results` with a single greedy regex** — multiple verifier records cause false matches across method names.
- **Storing full email bodies in D1** — GDPR/CCPA exposure; store only metadata and a reference to R2 if body archival is needed.

## Gotchas

- `message.setReject()` must be called synchronously before any `await` that touches the message object; once the Workers runtime's email event resolves the accept/forward/reject decision is locked.
- Cloudflare adds its own `Authentication-Results` header after the external `Received:` chain — there may be multiple `Authentication-Results` headers; `message.headers.get()` returns only the first. Use `message.headers.getAll("Authentication-Results")` and validate each.
- DKIM alignment (strict vs relaxed) is not exposed separately; `dkim=pass` means the signature validated, not that the `d=` tag aligns with the `From:` domain — implement your own alignment check if strict DMARC alignment is a compliance requirement.
- Email Workers have a 10 MB message size limit; reject oversized messages before parsing headers.

## Verification

```bash
# Send a test message from a spoofed domain (requires local MTA)
swaks --to inbound@yourdomain.com --from spoof@evil.com --server mx.yourdomain.com

# Check D1 rejection log
wrangler d1 execute DB --command \
  "SELECT from_addr, reason, ts FROM email_rejections ORDER BY ts DESC LIMIT 10"

# Confirm SPF record covers Cloudflare Email Routing MX pool
dig TXT yourdomain.com | grep "v=spf1"
```

## Related

- `workers-tail-workers-security-event-streaming.md`
- `log-injection-prevention.md`
- `r2-bucket-public-exposure-audit.md`
- `rate-limiting-per-user-d1-durable-objects.md`

## Sources

- Cloudflare Email Workers docs — https://developers.cloudflare.com/email-routing/email-workers/
- RFC 7601 — Message Header Field for Indicating Message Authentication Status
- RFC 7489 — Domain-based Message Authentication, Reporting, and Conformance (DMARC)
- RFC 6376 — DomainKeys Identified Mail (DKIM) Signatures
