# Email Deliverability Feedback Loop ISP Integration With Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project (example.com) sends notification emails to users across major ISPs (Gmail, Yahoo, Outlook/Hotmail, AOL). When recipients mark emails as spam, ISPs send Feedback Loop (FBL) complaint notifications back to the sender. Without processing these, the platform continues mailing complainers, driving up the complaint rate, damaging sender reputation, and eventually triggering ISP-side deferrals or blocks.

## Context
ISPs deliver FBL complaint reports as ARF (Abuse Reporting Format) emails to a designated abuse address, or via HTTP POST (Yahoo's CFL uses a webhook). Cloudflare Email Routing receives ARF complaints at `abuse@mail.example.com` and routes them to a Worker. The Worker parses the ARF `X-Feedback-ID` header (or VERP envelope) to identify the original recipient, inserts a suppression record in D1, and posts a metric to Analytics Engine for complaint rate monitoring.

## FBL Registration

Each ISP requires a separate registration. Gmail uses Google Postmaster Tools (no ARF emails — they expose complaint rate in the API). Yahoo, AOL, and Comcast use Feedback Loop registration portals. Microsoft uses JMRP (Junk Mail Reporting Program). For all ARF-based FBLs, register `abuse@mail.example.com` as the complaint address and include the `X-Feedback-ID` header in outgoing emails.

```typescript
// add-feedback-id-header.ts
// Include this header in every outbound notification email
// Format: campaignType:userId:sendingDomain (base64-safe, no colons in values)
export function buildFeedbackIdHeader(
  userId: string,
  campaignType: string
): string {
  // X-Feedback-ID is scanned by Gmail Postmaster Tools and some ISP FBLs
  // Use a structured value: <campaign>:<userId>:<domain>
  const safeUserId = userId.replace(/[^a-z0-9]/gi, "");
  return `${campaignType}:${safeUserId}:example.com`;
}
```

## ARF Complaint Email Worker

The Worker receives ARF complaint emails at `abuse@mail.example.com`. ARF messages are `multipart/report` with `Content-Type: message/feedback-report`. The Worker extracts the original recipient from the `Original-Rcpt-To` or `Original-Mail-From` ARF header, then writes a suppression.

```typescript
// arf-processor.ts
import PostalMime from "postal-mime";

interface ARFReport {
  feedbackType: string;
  originalRcptTo: string | null;
  originalMailFrom: string | null;
  userAgent: string;
  feedbackId: string | null;
}

export async function parseARF(rawBytes: ArrayBuffer): Promise<ARFReport | null> {
  const email = await PostalMime.parse(rawBytes);

  if (!email.contentType?.startsWith("multipart/report")) return null;

  // The second part of a multipart/report is message/feedback-report
  const reportPart = email.attachments.find(
    (a) => a.mimeType === "message/feedback-report"
  );
  if (!reportPart) return null;

  const reportText = new TextDecoder().decode(reportPart.content);
  const lines = reportText.split(/\r?\n/);

  const get = (key: string) => {
    const line = lines.find((l) => l.toLowerCase().startsWith(key.toLowerCase() + ":"));
    return line ? line.slice(key.length + 1).trim() : null;
  };

  return {
    feedbackType:    get("Feedback-Type") ?? "abuse",
    originalRcptTo:  get("Original-Rcpt-To"),
    originalMailFrom: get("Original-Mail-From"),
    userAgent:       get("User-Agent") ?? "",
    feedbackId:      get("X-Feedback-ID"),
  };
}
```

## Suppression Insert and Metric Write

After parsing the ARF report the Worker inserts a suppression record in D1 and writes a complaint event to Analytics Engine. The suppression uses the original recipient email as the key; future sends check this table before delivery.

```typescript
// arf-email-handler.ts — email export
export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    // Only process mail to the abuse address
    if (!message.to.startsWith("abuse@")) {
      await message.forward("postmaster@example.com");
      return;
    }

    const chunks: Uint8Array[] = [];
    const reader = message.raw.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) chunks.push(value);
    }
    const bytes = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0));
    let off = 0; for (const c of chunks) { bytes.set(c, off); off += c.length; }

    const report = await parseARF(bytes.buffer);
    if (!report) return; // Not an ARF message — silently drop

    const complainerEmail = report.originalRcptTo ?? report.originalMailFrom;
    if (!complainerEmail) return;

    // 1. Insert suppression
    await env.DB.prepare(`
      INSERT OR IGNORE INTO suppressions (email, reason, source, created_at)
      VALUES (?1, 'fbl_complaint', ?2, unixepoch())
    `)
      .bind(complainerEmail.toLowerCase(), report.userAgent)
      .run();

    // 2. Update user row if found
    const user = await env.DB
      .prepare("SELECT id FROM users WHERE lower(email) = ?1")
      .bind(complainerEmail.toLowerCase())
      .first<{ id: string }>();

    if (user) {
      await env.DB.prepare(`
        UPDATE users SET complaint_count = complaint_count + 1, last_complaint_at = unixepoch()
        WHERE id = ?1
      `).bind(user.id).run();
    }

    // 3. Metric
    env.EMAIL_AE.writeDataPoint({
      blobs: [report.feedbackType, report.feedbackId ?? "unknown", "complaint"],
      doubles: [1],
      indexes: ["fbl"],
    });
  },
};
```

## Yahoo CFL Webhook Handler

Yahoo's Complaint Feedback Loop (CFL) delivers complaints via HTTP POST (JSON) rather than ARF email. Register a HTTPS endpoint and verify the `Authorization: Bearer <token>` header that Yahoo provides during registration.

```typescript
// yahoo-cfl-webhook.ts
interface YahooCFLPayload {
  complaint_feedback_id: string;
  feedback_date:         string;
  user_agent:            string;
  version:               string;
  recipients:            Array<{ email: string }>;
}

export async function handleYahooCFL(request: Request, env: Env): Promise<Response> {
  const authHeader = request.headers.get("Authorization") ?? "";
  if (authHeader !== `Bearer ${env.YAHOO_CFL_TOKEN}`) {
    return new Response("Unauthorized", { status: 401 });
  }

  const payload = await request.json<YahooCFLPayload>();

  for (const recipient of payload.recipients) {
    const email = recipient.email.toLowerCase();
    await env.DB.prepare(`
      INSERT OR IGNORE INTO suppressions (email, reason, source, created_at)
      VALUES (?1, 'fbl_complaint', 'yahoo-cfl', unixepoch())
    `).bind(email).run();

    env.EMAIL_AE.writeDataPoint({
      blobs: ["abuse", payload.complaint_feedback_id, "complaint"],
      doubles: [1],
      indexes: ["fbl"],
    });
  }

  return new Response("OK");
}
```

## Anti-patterns
- Ignoring FBL complaints and relying solely on bounce handling — complaints are the primary signal ISPs use to classify senders as spammers; high complaint rates persist in ISP reputation models for weeks.
- Processing ARF as plain-text email without parsing the `multipart/report` structure — the machine-readable recipient address is in the second MIME part, not the outer headers.
- Using the same `X-Feedback-ID` for all emails — without per-campaign or per-user segmentation, the ID provides no actionable signal for identifying which campaigns generate complaints.
- Only suppressing at the user level — if a user has multiple email addresses, suppress all known addresses or you will continue mailing them on the next send.

## Gotchas
- Gmail does not send ARF FBL emails; complaint rate is only visible via Google Postmaster Tools API — set up `email-postmaster-api-workers-analytics-engine.md` separately.
- Some ISPs (Comcast, AOL) redact the original recipient email in ARF reports for privacy; use VERP bounce addresses as a fallback identifier when `Original-Rcpt-To` is absent.
- Yahoo CFL webhook payloads arrive with a slight delay (minutes to hours) after the complaint is filed; real-time suppression is not guaranteed.
- The `X-Feedback-ID` header must be added before DKIM signing; modifying it after signing breaks the DKIM `h=` tag coverage.

## Verification
1. Register the abuse address with Yahoo FBL and trigger a test complaint via the Yahoo FBL test tool; confirm a suppression row appears in D1 within 10 minutes.
2. Craft a synthetic ARF email (per RFC 5965) and deliver it to `abuse@mail.example.com`; confirm the `parseARF` function extracts the recipient and writes the suppression.
3. Query Analytics Engine for `fbl` index events and confirm complaint counts increment after test submissions.
4. Attempt to send to a suppressed address and confirm the send is blocked at the guard layer.

## Related
- [email-feedback-loop-setup.md](email-feedback-loop-setup.md)
- [complaint-rate-monitoring.md](complaint-rate-monitoring.md)
- [email-suppression-list-kv-workers.md](email-suppression-list-kv-workers.md)
- [email-open-click-analytics-engine.md](email-open-click-analytics-engine.md)
- [email-postmaster-api-workers-analytics-engine.md](email-postmaster-api-workers-analytics-engine.md)

## Sources
- https://developers.cloudflare.com/email-routing/email-workers/
- https://www.rfc-editor.org/rfc/rfc5965 (ARF format)
- https://senders.yahooinc.com/complaint-feedback-loop/
- https://sendersupport.olc.protection.outlook.com/snds/JMRP.aspx
- https://developers.cloudflare.com/analytics/analytics-engine/
