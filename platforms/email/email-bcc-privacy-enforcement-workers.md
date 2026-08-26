# Email BCC Privacy Enforcement in Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

BCC (Blind Carbon Copy) recipients must never appear in the `To:`, `CC:`, or `Bcc:` headers delivered to primary recipients. Some ESPs or in-house SMTP pipelines incorrectly include a `Bcc:` header in the outbound message, leaking recipient identities and violating privacy expectations. This is especially damaging in HR, legal, or compliance contexts where the confidentiality of BCC'd parties is legally required.

A Cloudflare Worker sitting between your application and a transactional ESP (MailChannels, Resend, Postmark) acts as a privacy firewall: it strips forbidden headers from every outbound message and logs violations so engineering can fix the upstream bug at its source.

## Context

RFC 5322 §3.6.3 specifies that a `Bcc:` field, if present in a message delivered to non-BCC recipients, must either be deleted or left with an empty value. RFC 5321 §3.6.3 similarly requires BCC recipients to be removed from the envelope before delivery. Many application developers misread this as "the ESP handles it," without realising that some ESPs re-inject BCC addresses from their API payload's `bcc` field into the outgoing MIME headers.

Cloudflare Workers intercept the HTTPS API call your application makes to the ESP (or act as a proxy endpoint your app posts to), inspect and mutate the payload, and forward a sanitised version. No BCC header reaches the wire. Violations are logged to D1 for audit and alerting.

## Sanitising ESP JSON Payloads

```typescript
export interface Env {
  DB: D1Database;
  ESP_API_URL: string;  // e.g. "https://api.mailchannels.net/tx/v1/send"
  ESP_API_KEY: string;
}

// Header names that must not appear in delivered messages
const FORBIDDEN_HEADERS = ["bcc", "blind-carbon-copy", "x-bcc"];

function sanitiseJsonPayload(payload: Record<string, unknown>): {
  sanitised: Record<string, unknown>;
  hadBcc: boolean;
} {
  let hadBcc = false;
  const sanitised = { ...payload };

  // Remove top-level BCC fields used by ESPs (Postmark, Resend, SendGrid, etc.)
  for (const key of ["bcc", "Bcc", "BCC"]) {
    if (key in sanitised) {
      delete sanitised[key];
      hadBcc = true;
    }
  }

  // Remove BCC from custom headers array (MailChannels, SendGrid v3 style)
  if (Array.isArray(sanitised.headers)) {
    const before = (sanitised.headers as unknown[]).length;
    sanitised.headers = (
      sanitised.headers as Array<{ name: string; value: string }>
    ).filter((h) => !FORBIDDEN_HEADERS.includes(h.name.toLowerCase()));
    if ((sanitised.headers as unknown[]).length < before) hadBcc = true;
  }

  // Remove BCC from MailChannels personalizations[].headers
  if (Array.isArray(sanitised.personalizations)) {
    sanitised.personalizations = (
      sanitised.personalizations as Array<Record<string, unknown>>
    ).map((p) => {
      if (!Array.isArray(p.headers)) return p;
      const before = p.headers.length;
      const cleaned = (p.headers as Array<{ name: string; value: string }>).filter(
        (h) => !FORBIDDEN_HEADERS.includes(h.name.toLowerCase())
      );
      if (cleaned.length < before) hadBcc = true;
      return { ...p, headers: cleaned };
    });
  }

  return { sanitised, hadBcc };
}
```

## Stripping BCC from Raw MIME

When passing raw MIME (e.g., via MailChannels `raw_mime` field), strip at the header level respecting folded header continuation lines:

```typescript
function stripBccFromMimeHeaders(rawMime: string): string {
  const lines = rawMime.split(/\r?\n/);
  const cleaned: string[] = [];
  let skipFolded = false;

  for (const line of lines) {
    const headerName = line.match(/^([A-Za-z0-9-]+)\s*:/)?.[1]?.toLowerCase();

    if (headerName) {
      // Start of a named header
      skipFolded = FORBIDDEN_HEADERS.includes(headerName);
    } else if (skipFolded && /^\s/.test(line)) {
      // Folded continuation of a forbidden header — skip it
      continue;
    } else {
      skipFolded = false;
    }

    if (!skipFolded) cleaned.push(line);
  }

  return cleaned.join("\r\n");
}

async function processMimePayload(
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  if (typeof payload["raw_mime"] === "string") {
    return {
      ...payload,
      raw_mime: stripBccFromMimeHeaders(payload["raw_mime"]),
    };
  }
  return payload;
}
```

## Worker Proxy Handler with Audit Logging

```typescript
// schema:
// CREATE TABLE bcc_violations (
//   id           INTEGER PRIMARY KEY AUTOINCREMENT,
//   detected_at  TEXT NOT NULL,
//   to_addr      TEXT,
//   subject      TEXT,
//   source_ip    TEXT,
//   payload_hash TEXT  -- SHA-256 of full payload for forensics
// );

async function recordViolation(
  db: D1Database,
  req: Request,
  payload: Record<string, unknown>
): Promise<void> {
  const toAddr = Array.isArray(payload["to"])
    ? (payload["to"] as Array<{ email: string }>).map((r) => r.email).join(",")
    : String(payload["to"] ?? "");

  const encoder = new TextEncoder();
  const hashBuffer = await crypto.subtle.digest(
    "SHA-256",
    encoder.encode(JSON.stringify(payload))
  );
  const hashHex = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  await db
    .prepare(
      `INSERT INTO bcc_violations (detected_at, to_addr, subject, source_ip, payload_hash)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(
      new Date().toISOString(),
      toAddr,
      String(payload["subject"] ?? ""),
      req.headers.get("CF-Connecting-IP") ?? "",
      hashHex
    )
    .run();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    let body: Record<string, unknown>;
    try {
      body = await request.json();
    } catch {
      return new Response("Bad Request: invalid JSON", { status: 400 });
    }

    // Handle raw MIME and JSON API paths
    let sanitisedBody = await processMimePayload(body);
    const { sanitised, hadBcc } = sanitiseJsonPayload(sanitisedBody);

    if (hadBcc) {
      console.warn(
        JSON.stringify({
          event: "bcc_header_stripped",
          to: body["to"],
          subject: body["subject"],
          ts: new Date().toISOString(),
        })
      );
      // Fire-and-forget audit log — do not delay the send
      const ctx = (request as Request & { ctx?: ExecutionContext }).ctx;
      if (ctx) {
        ctx.waitUntil(recordViolation(env.DB, request, body));
      }
    }

    const espResponse = await fetch(env.ESP_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${env.ESP_API_KEY}`,
      },
      body: JSON.stringify(sanitised),
    });

    return new Response(await espResponse.text(), {
      status: espResponse.status,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Alerting on Recurring Violations

A daily cron summarises violation counts per source IP so the originating application code can be found and fixed:

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const summary = await env.DB.prepare(
      `SELECT source_ip, COUNT(*) AS cnt
       FROM bcc_violations
       WHERE detected_at > datetime('now', '-24 hours')
       GROUP BY source_ip
       ORDER BY cnt DESC
       LIMIT 10`
    ).all<{ source_ip: string; cnt: number }>();

    if (summary.results.length > 0) {
      const lines = summary.results.map(
        (r) => `  ${r.source_ip}: ${r.cnt} violation(s)`
      );
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `BCC violations in the last 24 h:\n${lines.join("\n")}`,
        }),
      });
    }
  },
};
```

## Anti-patterns

- Relying on the ESP to strip BCC — behaviour varies; Postmark strips it on delivery, but others pass it through verbatim
- Only checking the top-level `bcc` JSON field and missing BCC injected through the custom `headers` array or `personalizations` sub-array
- Logging full BCC email addresses in plaintext in Workers logs — BCC contents are PII; hash or omit them
- Rejecting requests that contain BCC instead of stripping — this breaks legitimate use cases where the app intended BCC addresses to receive a separate copy; strip silently, then fix upstream code
- Treating BCC stripping as optional for transactional email — legal exposure in HIPAA, GDPR, and attorney-client privilege contexts is real and documented

## Gotchas

- MailChannels v2 API uses `personalizations[].to` and does not have an explicit `bcc` field in its schema, but some SDK wrappers inject it via `personalizations[].headers` — always inspect that nested array
- RFC 5322 §3.6.3 allows a `Bcc:` header with an empty value to indicate BCC was used without revealing addresses; stripping entirely is the safer choice for maximum privacy
- Cloudflare Workers cannot inspect outbound SMTP connections at the TCP level; this approach works only when your app uses an HTTP API to send email, not direct SMTP (which Workers do not support anyway)
- If your ESP SDK is called inside the Worker itself rather than proxied, apply `sanitiseJsonPayload` to the SDK options object before calling `send()`
- Folded MIME headers (lines beginning with whitespace that continue a previous header) must be handled as a unit; naive line-by-line stripping that only checks the first line will miss folded BCC continuations

## Verification

1. POST a JSON payload containing `"bcc": "secret@example.com"` to the Worker endpoint
2. Confirm the Worker responds with the ESP's 2xx success
3. Inspect the delivered message headers at the `to` recipient using a raw-header tool (Mailpit, Mailtrap, `swaks --dump`) — no `Bcc:` field should appear
4. Query `SELECT * FROM bcc_violations ORDER BY detected_at DESC LIMIT 5` and confirm a violation row was recorded
5. Test the MIME path: include `Bcc: hidden@example.com\r\n` in `raw_mime` and confirm it is absent in the delivered message
6. POST a payload with no BCC fields and confirm no violation row is inserted

## Related

- email-cc-bcc-transactional.md
- email-header-injection-security.md
- email-security-audit-trail-d1-immutable-log.md
- email-content-html-sanitization-workers.md

## Sources

- RFC 5322 §3.6.3 Blind Copies: https://www.rfc-editor.org/rfc/rfc5322#section-3.6.3
- RFC 5321 §3.6.3 Blind Carbon Copies: https://www.rfc-editor.org/rfc/rfc5321#section-3.6.3
- Cloudflare Workers Fetch Handler: https://developers.cloudflare.com/workers/runtime-apis/handlers/fetch/
