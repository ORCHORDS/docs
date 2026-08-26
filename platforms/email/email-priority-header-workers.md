# Email Priority Header Management — Workers Middleware

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your transactional Workers pipeline sends password-reset emails, weekly newsletters,
and account-suspension alerts through the same code path. Recipients complain that
urgent alerts are buried under newsletters, but you have no consistent way to signal
urgency to mail clients. Alternatively, a marketing team has marked every campaign as
"High Importance", training recipients to ignore the flag entirely, and you want to
normalise or strip priority headers before messages leave the outbound Worker.

---

## Context

Four overlapping header standards control email priority rendering in clients:

| Header | Values | Standard |
|---|---|---|
| `X-Priority` | `1` (Highest) … `5` (Lowest) | De-facto (Outlook, Thunderbird) |
| `Importance` | `high`, `normal`, `low` | RFC 2156 §5.3.6 |
| `Priority` | `urgent`, `normal`, `non-urgent` | RFC 2156 §5.3.5 |
| `X-MSMail-Priority` | `High`, `Normal`, `Low` | Microsoft proprietary |

Mail client behaviour:

- **Outlook desktop** — reads `X-Priority` and `X-MSMail-Priority`; shows a `!` red
  flag for high, `↓` for low.
- **Thunderbird** — reads `X-Priority`; shows a priority column.
- **Gmail** — ignores all priority headers entirely; uses its own ML-based
  "Important" label.
- **Apple Mail** — reads `Importance`; shows a `!` or `↓` in the subject column.
- **Mobile (iOS Mail / Android Gmail)** — generally ignores priority headers.

Because Gmail ignores these headers, priority metadata is useful mainly for B2B
recipients on Exchange/Outlook. Treat it as a secondary signal, never the primary
UX affordance.

---

## Priority Mapping Table

```typescript
// priority.ts

export type EmailPriority = "urgent" | "high" | "normal" | "low" | "bulk";

interface PriorityHeaders {
  "X-Priority": string;
  "Importance": string;
  "Priority": string;
  "X-MSMail-Priority": string;
}

const PRIORITY_MAP: Record<EmailPriority, PriorityHeaders> = {
  urgent: {
    "X-Priority":        "1",
    "Importance":        "high",
    "Priority":          "urgent",
    "X-MSMail-Priority": "High",
  },
  high: {
    "X-Priority":        "2",
    "Importance":        "high",
    "Priority":          "urgent",
    "X-MSMail-Priority": "High",
  },
  normal: {
    "X-Priority":        "3",
    "Importance":        "normal",
    "Priority":          "normal",
    "X-MSMail-Priority": "Normal",
  },
  low: {
    "X-Priority":        "4",
    "Importance":        "low",
    "Priority":          "non-urgent",
    "X-MSMail-Priority": "Low",
  },
  bulk: {
    "X-Priority":        "5",
    "Importance":        "low",
    "Priority":          "non-urgent",
    "X-MSMail-Priority": "Low",
  },
};

export function priorityHeaders(level: EmailPriority): PriorityHeaders {
  return PRIORITY_MAP[level];
}
```

---

## Outbound Priority Middleware

### Applying Priority at Send Time

```typescript
// send-with-priority.ts
import { priorityHeaders, type EmailPriority } from "./priority";

export interface EmailMessage {
  to: string;
  subject: string;
  html: string;
  text?: string;
  priority?: EmailPriority;
  category?: "transactional" | "marketing" | "alert";
}

function resolvePriority(msg: EmailMessage): EmailPriority {
  // Explicit override wins
  if (msg.priority) return msg.priority;

  // Derive from category
  switch (msg.category) {
    case "alert":         return "urgent";
    case "transactional": return "normal";
    case "marketing":     return "low";
    default:              return "normal";
  }
}

export async function sendEmail(msg: EmailMessage, env: Env): Promise<void> {
  const level = resolvePriority(msg);
  const ph = priorityHeaders(level);

  const headers: Record<string, string> = {
    "Content-Type":      "text/html; charset=utf-8",
    "X-Priority":        ph["X-Priority"],
    "Importance":        ph["Importance"],
    "Priority":          ph["Priority"],
    "X-MSMail-Priority": ph["X-MSMail-Priority"],
  };

  // MailChannels TX v1 accepts custom headers
  await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: msg.to }] }],
      from: { email: "noreply@example.com" },
      subject: msg.subject,
      content: [
        { type: "text/html",  value: msg.html },
        { type: "text/plain", value: msg.text ?? stripHtml(msg.html) },
      ],
      headers,
    }),
  });
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
}

interface Env { /* Workers bindings */ }
```

---

## Inbound Priority Header Normalisation

Strip abused priority headers on inbound email before forwarding to internal
ticketing or webhook systems:

```typescript
// normalise-inbound.ts
// Used in a Cloudflare Email Workers handler

const PRIORITY_HEADERS_TO_STRIP = [
  "x-priority",
  "importance",
  "priority",
  "x-msmail-priority",
  "x-ms-exchange-organization-scl",
];

export function normalisePriorityHeaders(rawHeaders: Headers): Headers {
  const out = new Headers(rawHeaders);
  for (const h of PRIORITY_HEADERS_TO_STRIP) {
    out.delete(h);
  }
  // Optionally re-set to "normal" to avoid downstream inference
  out.set("Importance", "normal");
  out.set("X-Priority", "3");
  return out;
}
```

---

## Anti-Spam Interaction

Bulk senders setting `X-Priority: 1` on marketing email is a **known spam trigger**
signal for SpamAssassin and similar filters:

```
# SpamAssassin rule: MISSING_MIMEOLE detects Outlook-like headers without Outlook
XPRIORITY_HIGH    X-Priority =~ /\b[12]\b/   # +0.5 to +1.5 score
```

Scores depend on the SpamAssassin version and ruleset. Setting high priority on bulk
mail inflates spam scores. Use `low` or `bulk` for newsletters.

```typescript
// Pre-flight guard
export function validatePriorityForCategory(
  priority: EmailPriority,
  category: "transactional" | "marketing" | "alert"
): void {
  if (category === "marketing" && (priority === "urgent" || priority === "high")) {
    throw new Error(
      `Priority '${priority}' must not be used for marketing category — use 'low' or 'bulk'`
    );
  }
}
```

---

## Gmail Promotions Tab Hint

Gmail ignores priority headers but reads structured data annotations for the
Promotions tab. Do not conflate the two: if you are sending a promotional email,
set `X-Priority: 5` (low) *and* separately add Gmail Promotions annotations.
Priority headers are invisible in Gmail; fighting spam scoring is the only reason
they matter there.

---

## Precedence Header (Different from Priority)

`Precedence: bulk` is a separate, older header that suppresses out-of-office
auto-responders (RFC 2076). It is not the same as email priority:

```
Precedence: bulk   ← suppresses OOO replies; signals mailing-list origin
X-Priority: 5     ← signals low urgency to MUA
```

Set both on newsletter sends:

```typescript
headers["Precedence"] = "bulk";
headers["X-Priority"] = "5";
headers["Importance"] = "low";
```

---

## Anti-patterns

- **Setting `X-Priority: 1` on all transactional email** — reduces the signal value to
  zero; recipients and spam filters treat it as noise.
- **Using priority headers as the primary UX for urgency** — subject line wording and
  send time have far more impact than priority flags, especially for Gmail users.
- **Mixing `Priority: urgent` with `Importance: low`** — inconsistent values confuse
  MUAs. Always set all four headers consistently using the mapping table above.
- **Setting `X-Priority` without `Importance`** — Apple Mail reads `Importance` and
  will show no indicator if it is missing while Outlook shows the flag.

---

## Gotchas

- Some ESPs (SendGrid, Mailgun) strip custom headers unless explicitly enabled.
  Check your ESP's documentation for "custom headers" or "additional headers" support.
- AWS SES strips `X-MSMail-Priority` silently. Verify with an inbound capture
  (Postmark inbound, MailCatcher) that headers survive the ESP pipeline.
- `Priority: urgent` is distinct from `X-Priority: 1`. Both should be set for full
  client coverage but they are parsed by different clients.
- Cloudflare Email Routing's `forward()` preserves existing headers; injecting new
  headers requires building a new MIME message from scratch via the Workers email API.

---

## Verification

```bash
# Send a test email and inspect raw headers in Gmail
# Gmail: three-dot menu → "Show original" → search for X-Priority

# Use mail-tester.com or Mailtrap to inspect the final headers
# after ESP processing
```

---

## Related

- `email-spam-score-preflight-workers.md` — spam score checking before send
- `email-batch-sending.md` — batching considerations for bulk sends
- `email-content-guidelines.md` — content signals affecting deliverability
- `transactional-vs-marketing-email.md` — category distinctions

---

## Sources

- RFC 2156 §5.3.5 and §5.3.6 — `Priority` and `Importance` headers
- RFC 2076 — Common Internet Message Headers (`Precedence`)
- SpamAssassin rules: `XPRIORITY_HIGH`, `MISSING_MIMEOLE`
- Microsoft Outlook developer documentation — `X-Priority`
- Gmail Promotions annotations — schema.org structured data
