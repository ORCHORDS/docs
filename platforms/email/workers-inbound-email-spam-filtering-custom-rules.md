# Workers Inbound Email Spam Filtering with Custom Rules

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Cloudflare Email Routing forwards all matching inbound email to your destination without content inspection. You need to:

- Reject known spam domains and disposable addresses before they reach your inbox or application
- Apply keyword-based body scoring to catch spam not caught by DMARC/SPF failures
- Rate-limit senders who flood your address
- Log rejected messages to R2 for audit without forwarding them

Cloudflare's built-in Email Routing rules match only on recipient address; custom filtering logic must live in the Email Routing Worker.

---

## Context

An Email Routing Worker sits in the delivery path and receives the `EmailMessage` object before any forwarding occurs. Calling `message.setReject(reason)` drops the message and returns a 550-class SMTP rejection to the sending MTA. The Worker can inspect headers, envelope data, and — after buffering `message.raw` — the full body.

The filtering pipeline evaluated in order:

1. **Envelope checks** — sender domain, SPF/DKIM result headers
2. **Header heuristics** — suspicious `X-Mailer`, missing `Date`, excess `Received` hops
3. **Rate limiting** — sender IP or domain via Workers KV TTL counters
4. **Body keyword scoring** — phrase matching on plain-text body
5. **Allow/block list** — KV-backed overrides that bypass or enforce rejection

---

## Envelope and Authentication Checks

```typescript
import type { EmailMessage } from "cloudflare:email";

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    // 1. Block if DMARC/SPF failed (header set by upstream MTA)
    const authResults = message.headers.get("Authentication-Results") ?? "";
    if (/dmarc=fail/i.test(authResults) && /spf=fail/i.test(authResults)) {
      message.setReject("5.7.1 Authentication failed");
      return;
    }

    // 2. Block explicitly listed sender domains (KV blocklist)
    const senderDomain = message.from.split("@")[1]?.toLowerCase();
    const blocked = await env.SPAM_KV.get(`blocklist:domain:${senderDomain}`);
    if (blocked !== null) {
      message.setReject("5.7.1 Sender domain blocked");
      return;
    }

    // 3. Allowlist always passes
    const allowed = await env.SPAM_KV.get(`allowlist:sender:${message.from}`);
    if (allowed !== null) {
      await message.forward(env.DESTINATION_EMAIL);
      return;
    }

    await applyContentFilters(message, env, ctx);
  },
};
```

---

## Header Heuristic Scoring

```typescript
function scoreHeaders(message: EmailMessage): number {
  let score = 0;

  const subject = message.headers.get("Subject") ?? "";
  const mailer = message.headers.get("X-Mailer") ?? "";
  const date = message.headers.get("Date");

  // Missing Date header
  if (!date) score += 2;

  // Suspicious subject patterns
  if (/\b(free|winner|prize|click here|act now|limited offer)\b/i.test(subject)) {
    score += 3;
  }

  if (/!!+/.test(subject)) score += 2;

  // Excessive capitalisation in subject (>60% uppercase letters)
  const letters = subject.replace(/[^a-z]/gi, "");
  if (letters.length > 5) {
    const upperRatio = (subject.replace(/[^A-Z]/g, "").length) / letters.length;
    if (upperRatio > 0.6) score += 2;
  }

  // Known spam X-Mailer strings
  if (/mass\s*mail|bulk\s*sender|email\s*blaster/i.test(mailer)) score += 4;

  return score;
}
```

---

## Rate Limiting Senders via KV

```typescript
async function isSenderRateLimited(
  senderDomain: string,
  env: Env
): Promise<boolean> {
  const key = `ratelimit:domain:${senderDomain}`;
  const countStr = await env.SPAM_KV.get(key);
  const count = countStr ? parseInt(countStr, 10) : 0;

  const WINDOW_SECONDS = 3600; // 1 hour
  const MAX_MESSAGES = 20;

  if (count >= MAX_MESSAGES) return true;

  // Increment with TTL on first write
  await env.SPAM_KV.put(key, String(count + 1), {
    expirationTtl: WINDOW_SECONDS,
  });

  return false;
}
```

---

## Body Keyword Scoring

```typescript
const SPAM_PHRASES: [pattern: RegExp, weight: number][] = [
  [/\bcasino\b/i, 3],
  [/\bviagra\b/i, 5],
  [/\bpayday loan/i, 4],
  [/\bunsubscribe from this list\b/i, 1],  // low weight — legitimate bulk
  [/\bsocial security number\b/i, 4],
  [/\bverify your account\b/i, 2],
  [/https?:\/\/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/i, 4], // bare-IP links
];

async function scoreBody(message: EmailMessage): Promise<number> {
  let score = 0;

  try {
    // Buffer only the first 50 KB to limit memory usage
    const reader = message.raw.getReader();
    const chunks: Uint8Array[] = [];
    let totalBytes = 0;

    while (totalBytes < 50_000) {
      const { done, value } = await reader.read();
      if (done || !value) break;
      chunks.push(value);
      totalBytes += value.byteLength;
    }

    reader.cancel();

    const text = new TextDecoder().decode(
      chunks.reduce((acc, c) => {
        const merged = new Uint8Array(acc.byteLength + c.byteLength);
        merged.set(acc);
        merged.set(c, acc.byteLength);
        return merged;
      }, new Uint8Array(0))
    );

    for (const [pattern, weight] of SPAM_PHRASES) {
      if (pattern.test(text)) score += weight;
    }
  } catch {
    // Stream already consumed or parse error — skip body scoring
  }

  return score;
}
```

---

## Assembling the Filter Pipeline

```typescript
const REJECT_THRESHOLD = 8;

async function applyContentFilters(
  message: EmailMessage,
  env: Env,
  ctx: ExecutionContext
) {
  const senderDomain = message.from.split("@")[1]?.toLowerCase() ?? "";

  if (await isSenderRateLimited(senderDomain, env)) {
    message.setReject("4.7.1 Too many messages from sender");
    return;
  }

  let totalScore = scoreHeaders(message);

  // Note: scoreBody consumes message.raw — call only if not forwarding
  // For simplicity here we score body before deciding; in production,
  // tee the stream if you need both scoring and forwarding of borderline messages.
  totalScore += await scoreBody(message);

  if (totalScore >= REJECT_THRESHOLD) {
    ctx.waitUntil(logRejection(message, totalScore, env));
    message.setReject(`5.7.1 Message rejected (score ${totalScore})`);
    return;
  }

  await message.forward(env.DESTINATION_EMAIL);
}

async function logRejection(
  message: EmailMessage,
  score: number,
  env: Env
): Promise<void> {
  const key = `spam-rejections/${new Date().toISOString().slice(0, 10)}/${crypto.randomUUID()}.json`;
  await env.AUDIT_BUCKET.put(
    key,
    JSON.stringify({
      from: message.from,
      to: message.to,
      subject: message.headers.get("Subject"),
      score,
      rejectedAt: new Date().toISOString(),
    }),
    { httpMetadata: { contentType: "application/json" } }
  );
}
```

---

## KV Blocklist / Allowlist Management API

```typescript
// Admin Worker endpoint to manage blocklists
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { action, type, value } = await request.json<{
      action: "block" | "allow" | "remove";
      type: "domain" | "sender";
      value: string;
    }>();

    const key =
      action === "allow"
        ? `allowlist:${type}:${value}`
        : `blocklist:${type}:${value}`;

    if (action === "remove") {
      await env.SPAM_KV.delete(key);
    } else {
      await env.SPAM_KV.put(key, "1");
    }

    return Response.json({ ok: true, key });
  },
};
```

---

## Anti-patterns

- **Using `message.setReject()` on all unrecognised senders** — you will block legitimate cold email; only reject when the score is unambiguous or the domain is explicitly listed.
- **Scoring the full body synchronously before deciding to forward** — reading `message.raw` is destructive; once consumed the stream cannot be passed to `message.forward()`. If you need to both score and forward borderline messages, tee the stream first or only score the headers.
- **Storing blocklists in D1** — KV reads from the filter hot path are O(1); D1 queries add 5–15 ms of unnecessary latency.
- **Hard-coding spam phrases in the Worker** — maintain the phrase list in a KV key (JSON array) and refresh it via a Cron Worker so spam rules can be updated without a deployment.

---

## Gotchas

- `message.setReject(reason)` must be called before any `await` that resolves after the Worker's synchronous execution path completes — in practice, call it before any async chain that might not resolve.
- Calling `message.forward()` after `message.setReject()` (or vice versa) throws; the two are mutually exclusive.
- The SMTP rejection reason string is returned to the sending MTA; keep it generic to avoid disclosing filtering logic to spammers.
- KV consistency is eventual; a blocklist entry written and immediately checked in the same request may not reflect the new value.
- `message.raw` is a `ReadableStream`; once read (even partially), it cannot be forwarded. If you want to forward the message after body scoring, buffer the full body, check the score, and forward using the `EmailMessage` API (which does not require re-streaming).

---

## Verification

```bash
# Add a blocked domain
curl -X POST https://spam-admin.example.com/ \
  -H "Content-Type: application/json" \
  -d '{"action":"block","type":"domain","value":"spammer.xyz"}'

# Send a test from the blocked domain (expect 550 rejection)
swaks --from test@spammer.xyz --to you@routing-domain.com \
  --body "Click here to claim your prize!!!"

# Review R2 rejection log
wrangler r2 object list AUDIT_BUCKET --prefix "spam-rejections/"
```

---

## Related

- `email-spam-score-preflight-workers.md`
- `inbound-email-processing.md`
- `cloudflare-email-routing-workers.md`
- `disposable-email-domain-detection-workers.md`
- `email-suppression-list-kv-workers.md`

---

## Sources

- Cloudflare Email Routing Workers — https://developers.cloudflare.com/email-routing/email-workers/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- RFC 5321 §4.2 SMTP Reply Codes — https://datatracker.ietf.org/doc/html/rfc5321#section-4.2
