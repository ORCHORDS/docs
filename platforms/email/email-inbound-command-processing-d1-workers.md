# Email-Based Command Processing with D1 and Email Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You operate an internal or B2B system where trusted external parties — partner systems, IoT devices, operations staff without VPN access — need to trigger actions or query state by sending a structured email. Use-cases include:

- `CMD: STATUS ORDER: 12345` → reply with current order status from D1
- `CMD: PAUSE CAMPAIGN: newsletter-weekly` → set a D1 flag and reply with confirmation
- `CMD: REPORT RANGE: 2026-08-01 2026-08-24` → aggregate D1 rows and reply with a summary

These systems often already have SMTP access but not HTTP API access. Email Workers allow you to expose a structured command interface over standard email without running an SMTP server.

---

## Context

The Email Worker is bound to a dedicated mailbox — e.g. `commands@yourdomain.com` — via an Email Routing specific address rule. Only emails from pre-authorised sender addresses (stored in a KV allowlist) are processed; all others are silently discarded or rejected.

Command parsing reads the **plain-text body** of the email, extracts lines matching `KEY: VALUE` pairs, and maps the `CMD` key to an action function that runs against D1. Results are sent back via MailChannels with `In-Reply-To` set to the original `Message-ID` so email clients thread the response.

Loop prevention is critical: the auto-reply must carry an `Auto-Submitted: auto-replied` header, and the Worker must check that header before processing.

---

## D1 Schema

```sql
-- wrangler d1 execute command-processor --file=schema.sql
CREATE TABLE IF NOT EXISTS command_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id   TEXT    NOT NULL UNIQUE,
  sender       TEXT    NOT NULL,
  command      TEXT    NOT NULL,
  params       TEXT    NOT NULL,   -- JSON
  outcome      TEXT,               -- 'ok' | 'error' | 'unknown_command'
  result_text  TEXT,               -- human-readable summary
  processed_at TEXT    NOT NULL
);

-- Example application table the commands act on
CREATE TABLE IF NOT EXISTS campaigns (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  slug    TEXT    NOT NULL UNIQUE,
  status  TEXT    NOT NULL DEFAULT 'active'   -- active | paused
);

CREATE INDEX idx_cmd_sender ON command_log(sender);
CREATE INDEX idx_cmd_date   ON command_log(processed_at);
```

---

## Worker Entry Point

```typescript
import PostalMime from "postal-mime";
import type { EmailMessage } from "cloudflare:email";

interface Env {
  SENDER_KV: KVNamespace;    // allowlist: "allowed:<email>" → "1"
  DB: D1Database;
  DKIM_PRIVATE_KEY: string;
  FROM_ADDRESS: string;      // "commands@yourdomain.com"
}

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    // 1. Loop prevention
    const autoSubmitted = message.headers.get("Auto-Submitted") ?? "no";
    if (autoSubmitted !== "no") return;

    // 2. Allowlist check
    const senderKey = `allowed:${message.from.toLowerCase()}`;
    const permitted = await env.SENDER_KV.get(senderKey);
    if (permitted === null) {
      message.setReject("5.7.1 Sender not authorised for command processing");
      return;
    }

    const messageId = message.headers.get("Message-ID") ?? `<${crypto.randomUUID()}@unknown>`;

    // 3. Idempotency: skip already-processed Message-IDs
    const existing = await env.DB.prepare(
      `SELECT id FROM command_log WHERE message_id = ?`
    ).bind(messageId).first();
    if (existing) return;

    // 4. Parse MIME to get plain-text body
    const rawBuffer = await new Response(message.raw).arrayBuffer();
    const parsed = await new PostalMime().parse(rawBuffer);
    const bodyText = parsed.text ?? "";

    // 5. Extract and execute commands
    const params = parseCommandParams(bodyText);
    const cmd = (params["CMD"] ?? params["COMMAND"] ?? "").toUpperCase();

    const { outcome, resultText } = await dispatchCommand(cmd, params, env);

    // 6. Log to D1
    await env.DB.prepare(
      `INSERT OR IGNORE INTO command_log (message_id, sender, command, params, outcome, result_text, processed_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        messageId,
        message.from,
        cmd,
        JSON.stringify(params),
        outcome,
        resultText,
        new Date().toISOString()
      )
      .run();

    // 7. Reply with result (non-blocking)
    ctx.waitUntil(sendReply(message, messageId, resultText, env));
  },
};
```

---

## Command Parameter Parser

```typescript
// Parses a plain-text email body for KEY: VALUE pairs, one per line.
function parseCommandParams(bodyText: string): Record<string, string> {
  const params: Record<string, string> = {};

  for (const rawLine of bodyText.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith(">")) continue;
    if (line === "--") break;

    const colonIdx = line.indexOf(":");
    if (colonIdx < 1) continue;

    const key = line.slice(0, colonIdx).trim().toUpperCase();
    const value = line.slice(colonIdx + 1).trim();

    if (key && value && !(key in params)) {
      params[key] = value;
    }
  }

  return params;
}
```

---

## Command Dispatcher

```typescript
interface CommandResult {
  outcome: "ok" | "error" | "unknown_command";
  resultText: string;
}

async function dispatchCommand(
  cmd: string,
  params: Record<string, string>,
  env: Env
): Promise<CommandResult> {
  switch (cmd) {
    case "STATUS": {
      const orderId = params["ORDER"];
      if (!orderId) return { outcome: "error", resultText: "Missing ORDER parameter." };

      const row = await env.DB.prepare(
        `SELECT id, status FROM campaigns WHERE id = ?`
      ).bind(orderId).first<{ id: number; status: string }>();

      if (!row) return { outcome: "error", resultText: `No record found for ORDER: ${orderId}` };
      return { outcome: "ok", resultText: `ORDER ${row.id} status: ${row.status}` };
    }

    case "PAUSE": {
      const slug = params["CAMPAIGN"];
      if (!slug) return { outcome: "error", resultText: "Missing CAMPAIGN parameter." };

      const result = await env.DB.prepare(
        `UPDATE campaigns SET status = 'paused' WHERE slug = ?`
      ).bind(slug).run();

      if (result.changes === 0) {
        return { outcome: "error", resultText: `Campaign not found: ${slug}` };
      }
      return { outcome: "ok", resultText: `Campaign "${slug}" has been paused.` };
    }

    case "RESUME": {
      const slug = params["CAMPAIGN"];
      if (!slug) return { outcome: "error", resultText: "Missing CAMPAIGN parameter." };

      const result = await env.DB.prepare(
        `UPDATE campaigns SET status = 'active' WHERE slug = ?`
      ).bind(slug).run();

      if (result.changes === 0) {
        return { outcome: "error", resultText: `Campaign not found: ${slug}` };
      }
      return { outcome: "ok", resultText: `Campaign "${slug}" has been resumed.` };
    }

    case "REPORT": {
      const from = params["FROM"] ?? params["RANGE"]?.split(" ")[0];
      const to   = params["TO"]   ?? params["RANGE"]?.split(" ")[1];

      if (!from || !to) {
        return { outcome: "error", resultText: "Provide FROM and TO dates (YYYY-MM-DD)." };
      }

      const rows = await env.DB.prepare(
        `SELECT command, COUNT(*) AS count FROM command_log
         WHERE processed_at >= ? AND processed_at < ?
         GROUP BY command ORDER BY count DESC`
      ).bind(from, to + "T23:59:59").all<{ command: string; count: number }>();

      const lines = rows.results.map((r) => `  ${r.command}: ${r.count}`).join("\n");
      return { outcome: "ok", resultText: `Command report ${from} → ${to}:\n${lines || "(no data)"}` };
    }

    default:
      return {
        outcome: "unknown_command",
        resultText:
          `Unknown command: "${cmd}". ` +
          `Valid commands: STATUS, PAUSE, RESUME, REPORT.`,
      };
  }
}
```

---

## Reply via MailChannels

```typescript
async function sendReply(
  original: EmailMessage,
  originalMessageId: string,
  resultText: string,
  env: Env
): Promise<void> {
  const subject = `Re: ${original.headers.get("Subject") ?? "Command Result"}`;

  await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      personalizations: [
        {
          to: [{ email: original.from }],
          dkim_domain: "yourdomain.com",
          dkim_selector: "mailchannels",
          dkim_private_key: env.DKIM_PRIVATE_KEY,
        },
      ],
      from: { email: env.FROM_ADDRESS, name: "Command Processor" },
      subject,
      content: [{ type: "text/plain", value: resultText }],
      headers: {
        "In-Reply-To": originalMessageId,
        "References": originalMessageId,
        "Auto-Submitted": "auto-replied",
      },
    }),
  });
}
```

---

## Anti-patterns

- **Accepting commands from any sender** — without an allowlist, anyone who can send email to your domain can trigger D1 writes. Always check a KV allowlist or DKIM-verified sender domain before processing.
- **Executing raw SQL from the email body** — parse a fixed vocabulary of commands and map them to parameterised D1 statements. Never interpolate any email content directly into a SQL string.
- **Sending an auto-reply to every email including bounces and OOO messages** — check `Auto-Submitted` before replying; otherwise a single command email can generate a reply loop with an out-of-office responder.
- **Parsing commands from the HTML body** — HTML email bodies contain markup, forwarded quoted sections, and footer junk. Always use `parsed.text` (the plain-text alternative) for structured command extraction.

---

## Gotchas

- Email clients frequently add quoted history to replies. The parser above breaks on the `--` signature delimiter but does not strip `>` deeply nested quoted blocks — test with Outlook, Gmail, and Apple Mail reply formats.
- The KV allowlist is eventually consistent. A newly added sender address may not be visible on the first message if the KV replication has not propagated. Consider a short warm-up delay or use D1 for the allowlist if strict consistency is required.
- Workers D1 `UNIQUE` on `message_id` prevents processing the same email twice if Email Routing retries delivery. Always treat a `D1_ERROR` on the INSERT as a no-op, not a failure.
- The MailChannels send in `sendReply` happens inside `ctx.waitUntil()`; if it throws, the error is logged but does not roll back the D1 insert. Monitor MailChannels send failures separately.

---

## Verification

```bash
# Apply schema
wrangler d1 execute command-processor --file=schema.sql

# Seed test data
wrangler d1 execute command-processor \
  --command "INSERT INTO campaigns (slug, status) VALUES ('newsletter-weekly', 'active')"

# Add your sender to the allowlist
wrangler kv key put --namespace-id <id> "allowed:you@example.com" "1"

# Deploy the Worker
wrangler deploy --name command-processor src/index.ts

# Send a PAUSE command
swaks --from you@example.com --to commands@yourdomain.com \
  --header "Subject: Pause newsletter" \
  --body "$(printf 'CMD: PAUSE\nCAMPAIGN: newsletter-weekly')"

# Verify D1 was updated and the command was logged
wrangler d1 execute command-processor \
  --command "SELECT slug, status FROM campaigns WHERE slug = 'newsletter-weekly'"

wrangler d1 execute command-processor \
  --command "SELECT sender, command, params, outcome, result_text FROM command_log ORDER BY id DESC LIMIT 5"
```

---

## Related

- `inbound-email-processing.md`
- `email-parsing-patterns.md`
- `email-auto-responder-out-of-office-d1-workers.md`
- `email-forwarding-loop-detection-d1-workers.md`
- `email-alias-routing-kv-workers.md`

---

## Sources

- Cloudflare Email Routing Workers — https://developers.cloudflare.com/email-routing/email-workers/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- PostalMime npm — https://www.npmjs.com/package/postal-mime
- MailChannels Transactional API — https://api.mailchannels.net/tx/v1/documentation
- RFC 3834 — Recommendations for Automatic Responses to Electronic Mail — https://datatracker.ietf.org/doc/html/rfc3834
