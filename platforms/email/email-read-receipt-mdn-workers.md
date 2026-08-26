# Email Read Receipt (MDN) Handling with Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Transactional and enterprise email systems sometimes include a `Disposition-Notification-To:` header requesting a Message Disposition Notification (MDN) — a structured read receipt — from the recipient's mail client. When the recipient's client honours the request, it generates an MDN message and sends it back. Your inbound email Worker needs to detect these MDNs, parse the structured report part, correlate them with original sent messages via D1, and record the read event.

MDN processing enables CRM-level engagement tracking without open-tracking pixels, which are blocked by Apple Mail Privacy Protection and increasingly by other privacy-oriented clients. MDNs are explicit, user-consented signals that survive image-blocking and proxy-loaded images.

## Context

RFC 3798 defines the MDN format: a `multipart/report; report-type=disposition-notification` MIME message whose second MIME part is `message/disposition-notification` containing key-value fields such as `Original-Message-ID`, `Disposition`, and `Reporting-UA`. Cloudflare Email Routing delivers these inbound MDN messages to a Worker via the `email` export, identical to any other inbound message.

Correlating an MDN to the original message requires storing the `Message-ID` of every sent message in D1 at send time, then looking it up when the MDN arrives. The correlation is reliable because RFC 3798 mandates that MDNs carry the `Original-Message-ID` of the message being acknowledged.

## Sending Messages with Disposition-Notification-To

Add the header at send time and persist the `Message-ID` in D1.

```typescript
// schema:
// CREATE TABLE sent_messages (
//   message_id   TEXT PRIMARY KEY,
//   to_addr      TEXT    NOT NULL,
//   subject      TEXT,
//   sent_at      TEXT    NOT NULL,
//   mdn_requested INTEGER DEFAULT 1
// );

export interface Env {
  DB: D1Database;
}

function generateMessageId(domain: string): string {
  const random = crypto.randomUUID().replace(/-/g, "");
  return `<${random}@${domain}>`;
}

async function sendWithMdnRequest(
  env: Env,
  to: string,
  subject: string,
  htmlBody: string,
  sendingDomain: string
): Promise<string> {
  const messageId = generateMessageId(sendingDomain);

  const response = await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: `noreply@${sendingDomain}`, name: "Your Service" },
      subject,
      content: [{ type: "text/html; charset=utf-8", value: htmlBody }],
      headers: {
        "Message-ID": messageId,
        // MDN replies go to a dedicated inbound address handled by your Worker
        "Disposition-Notification-To": `mdnreply@${sendingDomain}`,
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`ESP error ${response.status}: ${await response.text()}`);
  }

  await env.DB.prepare(
    `INSERT OR IGNORE INTO sent_messages (message_id, to_addr, subject, sent_at)
     VALUES (?, ?, ?, ?)`
  )
    .bind(messageId, to, subject, new Date().toISOString())
    .run();

  return messageId;
}
```

## Parsing Inbound MDN Messages

MDNs arrive as `multipart/report` messages. Use PostalMime (bundled into the Worker) to extract the `message/disposition-notification` part.

```typescript
import { PostalMime } from "postal-mime";

interface MdnFields {
  originalMessageId: string | null;
  disposition: string | null;
  reportingUa: string | null;
  finalRecipient: string | null;
}

async function parseMdn(rawStream: ReadableStream<Uint8Array>): Promise<MdnFields> {
  // Collect stream into a single buffer
  const reader = rawStream.getReader();
  const chunks: Uint8Array[] = [];
  let done = false;
  while (!done) {
    const { value, done: d } = await reader.read();
    if (value) chunks.push(value);
    done = d;
  }
  const totalLength = chunks.reduce((s, c) => s + c.length, 0);
  const buffer = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    buffer.set(chunk, offset);
    offset += chunk.length;
  }

  const parsed = await new PostalMime().parse(buffer.buffer);

  let originalMessageId: string | null = null;
  let disposition: string | null = null;
  let reportingUa: string | null = null;
  let finalRecipient: string | null = null;

  for (const attachment of parsed.attachments ?? []) {
    if (attachment.mimeType === "message/disposition-notification") {
      const text = new TextDecoder().decode(attachment.content);
      for (const line of text.split(/\r?\n/)) {
        const colonIdx = line.indexOf(":");
        if (colonIdx === -1) continue;
        const key = line.slice(0, colonIdx).trim().toLowerCase();
        const value = line.slice(colonIdx + 1).trim();
        switch (key) {
          case "original-message-id":
            originalMessageId = value;
            break;
          case "disposition":
            disposition = value;
            break;
          case "reporting-ua":
            reportingUa = value;
            break;
          case "final-recipient":
            finalRecipient = value.replace(/^rfc822;\s*/i, "");
            break;
        }
      }
    }
  }

  return { originalMessageId, disposition, reportingUa, finalRecipient };
}
```

## Inbound Worker: Detect, Validate, and Record

```typescript
// schema:
// CREATE TABLE mdn_events (
//   id                  INTEGER PRIMARY KEY AUTOINCREMENT,
//   original_message_id TEXT    NOT NULL,
//   disposition         TEXT,
//   reporting_ua        TEXT,
//   final_recipient     TEXT,
//   received_at         TEXT    NOT NULL,
//   FOREIGN KEY (original_message_id) REFERENCES sent_messages(message_id)
// );

import { EmailMessage } from "cloudflare:email";

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    const contentType = message.headers.get("content-type") ?? "";

    // Not an MDN — forward to main inbox
    if (!contentType.toLowerCase().includes("multipart/report")) {
      await message.forward("inbox@yourdomain.com");
      return;
    }

    const { originalMessageId, disposition, reportingUa, finalRecipient } =
      await parseMdn(message.raw);

    if (!originalMessageId) {
      // Malformed MDN — accept and discard to avoid bounce loops
      await message.setReject("250 2.0.0 MDN accepted");
      return;
    }

    // Verify we actually sent this message
    const sent = await env.DB.prepare(
      "SELECT message_id FROM sent_messages WHERE message_id = ?"
    )
      .bind(originalMessageId)
      .first<{ message_id: string }>();

    if (!sent) {
      // MDN for an unknown message — reject to prevent probing
      await message.setReject("550 5.1.3 Unknown original message");
      return;
    }

    ctx.waitUntil(
      env.DB.prepare(
        `INSERT INTO mdn_events
           (original_message_id, disposition, reporting_ua, final_recipient, received_at)
         VALUES (?, ?, ?, ?, ?)`
      )
        .bind(
          originalMessageId,
          disposition ?? "",
          reportingUa ?? "",
          finalRecipient ?? "",
          new Date().toISOString()
        )
        .run()
    );

    // MDNs require no reply — accept and discard
    await message.setReject("250 2.0.0 MDN recorded");
  },
};
```

## Querying MDN Engagement

```typescript
async function getMessageEngagement(
  db: D1Database,
  messageId: string
): Promise<{ read: boolean; readAt: string | null; ua: string | null }> {
  // RFC 3798 §3.2.6: "displayed" indicates the recipient read the message
  const event = await db
    .prepare(
      `SELECT disposition, received_at, reporting_ua
       FROM mdn_events
       WHERE original_message_id = ?
         AND disposition LIKE '%displayed%'
       ORDER BY received_at ASC
       LIMIT 1`
    )
    .bind(messageId)
    .first<{
      disposition: string;
      received_at: string;
      reporting_ua: string;
    }>();

  return {
    read: !!event,
    readAt: event?.received_at ?? null,
    ua: event?.reporting_ua ?? null,
  };
}

// Usage:
// const engagement = await getMessageEngagement(env.DB, "<abc123@yourdomain.com>");
// if (engagement.read) console.log(`Read at ${engagement.readAt} by ${engagement.ua}`);
```

## Anti-patterns

- Sending `Disposition-Notification-To` to a no-reply address that cannot receive email — MDNs will bounce and inflate your bounce rate
- Treating MDN absence as "message not read" — most email clients do not send MDNs at all; absence is not a negative signal
- Using the sender's own `From:` address as `Disposition-Notification-To` — generates confusing read-receipt prompts for recipients of transactional email
- Not verifying `Original-Message-ID` against your `sent_messages` table — attackers can forge MDNs for arbitrary message IDs to probe what you have sent
- Requesting MDN for mass-marketing campaigns — RFC 3798 §2.1 explicitly discourages MDN requests on bulk email; limit to transactional and person-to-person messages

## Gotchas

- `message.setReject("250 2.0.0 ...")` with a `250` code accepts the message silently; passing `550` actually rejects it — use `250` to absorb MDNs without forwarding them elsewhere
- Apple Mail sends MDNs only when the user explicitly approves a per-message prompt; Gmail's web client never sends MDNs regardless of the header presence
- The `Disposition` field is a structured string: `automatic-action/MDN-sent-manually; displayed` — parse the human-readable action portion after `;` to confirm `displayed` rather than `deleted` or `processed`
- PostalMime parses MDN report parts as binary `Uint8Array`; always decode with `TextDecoder` before splitting on lines
- Some mail clients send the MDN to `Reply-To` rather than `Disposition-Notification-To` if `Reply-To` is present — set `Reply-To` to a distinct address to prevent MDN/reply routing conflicts

## Verification

1. Send a test message with `Disposition-Notification-To: mdnreply@yourdomain.com` using `swaks --header "Disposition-Notification-To: mdnreply@yourdomain.com"`
2. Open the message in Thunderbird (enable MDN: Preferences → Composition → Send return receipt) and accept the read-receipt prompt
3. Confirm an inbound `multipart/report` email arrives at your Cloudflare Email Routing address for `mdnreply@`
4. Confirm the Worker accepts it with a 250 and does not forward it further
5. Query `SELECT * FROM mdn_events ORDER BY received_at DESC LIMIT 1` and verify `disposition` contains `displayed`
6. Call `getMessageEngagement` with the original message ID and confirm `read: true`

## Related

- email-open-tracking.md
- email-open-click-analytics-engine.md
- apple-mail-privacy-protection-metrics.md
- inbound-email-processing.md

## Sources

- RFC 3798 Message Disposition Notification: https://www.rfc-editor.org/rfc/rfc3798
- Cloudflare Email Workers `email` export: https://developers.cloudflare.com/email-routing/email-workers/
- PostalMime MIME parsing library: https://github.com/postalsys/postal-mime
