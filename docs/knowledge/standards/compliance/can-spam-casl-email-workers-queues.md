# CAN-SPAM and CASL Email Compliance: Transactional and Commercial Email Pipelines with Cloudflare Workers and Queues

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your Cloudflare Workers application sends email — password resets, order confirmations, newsletters, and promotional campaigns — through an email service provider (ESP: SendGrid, Mailgun, Resend, Postmark). A US/Canada customer complains they cannot unsubscribe. Your legal counsel flags missing physical address disclosures. You need a compliant email dispatch architecture that enforces CAN-SPAM and CASL requirements programmatically before a single message leaves the platform.

---

## Context

Two regimes govern commercial email in the US/Canada:

**CAN-SPAM Act (15 U.S.C. § 7701, FTC regulations 16 CFR § 316):**
- Applies to **commercial** electronic messages (any message whose primary purpose is commercial advertisement or promotion). Transactional messages receive lighter treatment.
- Requirements: no deceptive headers/subject lines; physical postal address in every commercial message; clear opt-out mechanism; honour opt-outs within **10 business days**; no harvested or dictionary-attack addresses.
- Penalties: up to **$53,088 per message** (2024 adjusted).

**Canada's Anti-Spam Legislation (CASL, S.C. 2010, c. 23):**
- Applies to **commercial electronic messages** (CEMs) sent *to* or *from* a Canadian computer.
- Express or **implied consent** must be obtained *before* sending (opt-in, not opt-out).
- Implied consent windows: 2 years from purchase/transaction; 6 months from an inquiry.
- Every CEM must identify the sender, provide a contact mechanism, and include an **unsubscribe mechanism** that is honoured within **10 business days**.
- Penalties: up to **CAD $10 million per violation** for organisations.

The key architectural difference: CAN-SPAM permits sending until a recipient opts *out*; CASL requires consent before sending. Your Workers pipeline must enforce both.

---

## Section 1 — Consent Store Schema in D1

```sql
-- migrations/001_email_consent_schema.sql

CREATE TABLE email_consents (
  id               TEXT PRIMARY KEY,
  email_hash       TEXT NOT NULL UNIQUE,   -- SHA-256 of normalised email
  email_encrypted  TEXT NOT NULL,           -- AES-GCM encrypted email address
  jurisdiction     TEXT NOT NULL CHECK(jurisdiction IN ('US','CA','OTHER')),
  consent_type     TEXT NOT NULL CHECK(consent_type IN ('express','implied_purchase','implied_inquiry','none')),
  consent_source   TEXT NOT NULL,           -- e.g. 'checkout_v2', 'signup_form_2025-09'
  consented_at     TEXT NOT NULL,
  consent_expires_at TEXT,                  -- NULL = indefinite (US); set for CASL implied
  unsubscribed_at  TEXT,
  unsubscribe_token TEXT NOT NULL UNIQUE,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE email_send_log (
  id             TEXT PRIMARY KEY,
  email_hash     TEXT NOT NULL,
  message_type   TEXT NOT NULL CHECK(message_type IN ('transactional','commercial')),
  subject        TEXT NOT NULL,
  esp_message_id TEXT,
  consent_id     TEXT REFERENCES email_consents(id),
  sent_at        TEXT NOT NULL DEFAULT (datetime('now')),
  can_spam_compliant INTEGER NOT NULL DEFAULT 1,
  casl_compliant     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE unsubscribe_events (
  id           TEXT PRIMARY KEY,
  email_hash   TEXT NOT NULL,
  method       TEXT NOT NULL CHECK(method IN ('link','reply','api','admin')),
  unsubscribed_at TEXT NOT NULL DEFAULT (datetime('now')),
  processed_at TEXT    -- must be <= 10 business days
);

CREATE INDEX idx_consent_hash    ON email_consents(email_hash);
CREATE INDEX idx_consent_token   ON email_consents(unsubscribe_token);
CREATE INDEX idx_unsub_hash      ON unsubscribe_events(email_hash);
```

---

## Section 2 — Pre-Send Compliance Gate

Every outgoing email must pass a compliance check before reaching the ESP.

```typescript
// src/email/compliance-gate.ts
import { createHash } from 'crypto';  // available in Workers via Node compat

interface EmailRecipient {
  address: string;
  jurisdiction: 'US' | 'CA' | 'OTHER';
  messageType: 'transactional' | 'commercial';
}

interface ComplianceResult {
  allowed: boolean;
  reason?: string;
  consentId?: string;
}

export async function checkEmailCompliance(
  env: Env,
  recipient: EmailRecipient
): Promise<ComplianceResult> {
  const normalised = recipient.address.toLowerCase().trim();
  const hash = await sha256Hex(normalised);

  const consent = await env.DB.prepare(`
    SELECT id, consent_type, consent_expires_at, unsubscribed_at
    FROM email_consents
    WHERE email_hash = ?
  `).bind(hash).first<{
    id: string;
    consent_type: string;
    consent_expires_at: string | null;
    unsubscribed_at: string | null;
  }>();

  // Hard stop: unsubscribed recipients
  if (consent?.unsubscribed_at) {
    return { allowed: false, reason: 'UNSUBSCRIBED' };
  }

  // Transactional messages: CAN-SPAM and CASL exempt (but best practice: still honour unsubs)
  if (recipient.messageType === 'transactional') {
    return { allowed: true, consentId: consent?.id };
  }

  // Commercial messages: consent required for CA (CASL) or opt-out check for US (CAN-SPAM)
  if (recipient.jurisdiction === 'CA') {
    if (!consent) {
      return { allowed: false, reason: 'CASL_NO_CONSENT' };
    }
    if (consent.consent_type === 'none') {
      return { allowed: false, reason: 'CASL_CONSENT_WITHDRAWN' };
    }
    if (consent.consent_expires_at && new Date(consent.consent_expires_at) < new Date()) {
      return { allowed: false, reason: 'CASL_CONSENT_EXPIRED' };
    }
    return { allowed: true, consentId: consent.id };
  }

  // US (CAN-SPAM): allowed unless opted out
  return { allowed: true, consentId: consent?.id };
}

async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Section 3 — Email Dispatch Worker with Required Disclosures

CAN-SPAM and CASL both require sender identification and unsubscribe mechanisms in every commercial message.

```typescript
// src/email/dispatch-worker.ts
interface EmailPayload {
  to: EmailRecipient[];
  subject: string;
  htmlBody: string;
  textBody: string;
  messageType: 'transactional' | 'commercial';
  senderName: string;
  fromAddress: string;
}

const PHYSICAL_ADDRESS = '123 Main St, Suite 100, San Francisco, CA 94105, USA';

export async function dispatchEmail(env: Env, payload: EmailPayload): Promise<void> {
  for (const recipient of payload.to) {
    const check = await checkEmailCompliance(env, recipient);
    if (!check.allowed) {
      console.warn(`Email to ${sha256Short(recipient.address)} blocked: ${check.reason}`);
      continue;
    }

    const token = await getUnsubscribeToken(env, recipient.address);
    const unsubscribeUrl = `https://your-app.com/unsubscribe?token=${token}`;
    const unsubscribeHeader = `<${unsubscribeUrl}>`;  // RFC 8058 List-Unsubscribe

    // Append required disclosures to commercial messages
    let html = payload.htmlBody;
    let text = payload.textBody;

    if (payload.messageType === 'commercial') {
      html += `
        <hr>
        <p style="font-size:12px;color:#666;">
          You received this email because you have a relationship with ${payload.senderName}.<br>
          Our mailing address: ${PHYSICAL_ADDRESS}<br>
          <a >Unsubscribe</a> at any time.
          Your request will be processed within 10 business days.
        </p>`;
      text += `\n\n---\nYou received this email because you have a relationship with ${payload.senderName}.\nOur mailing address: ${PHYSICAL_ADDRESS}\nTo unsubscribe: ${unsubscribeUrl}\nYour request will be processed within 10 business days.`;
    }

    // Send via ESP (Resend example)
    const response = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: `${payload.senderName} <${payload.fromAddress}>`,
        to: [recipient.address],
        subject: payload.subject,
        html,
        text,
        headers: {
          'List-Unsubscribe': unsubscribeHeader,
          'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',  // RFC 8058
        },
      }),
    });

    if (!response.ok) {
      const err = await response.text();
      throw new Error(`ESP error: ${err}`);
    }

    const { id: espMessageId } = await response.json<{ id: string }>();

    // Audit log
    await env.DB.prepare(`
      INSERT INTO email_send_log (id, email_hash, message_type, subject, esp_message_id, consent_id, sent_at)
      VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    `).bind(
      crypto.randomUUID(),
      await sha256Hex(recipient.address.toLowerCase()),
      payload.messageType,
      payload.subject,
      espMessageId,
      check.consentId ?? null
    ).run();
  }
}

function sha256Short(email: string): string {
  return email.slice(0, 3) + '***';
}

async function getUnsubscribeToken(env: Env, email: string): Promise<string> {
  const hash = await sha256Hex(email.toLowerCase());
  const row = await env.DB.prepare(
    'SELECT unsubscribe_token FROM email_consents WHERE email_hash = ?'
  ).bind(hash).first<{ unsubscribe_token: string }>();
  return row?.unsubscribe_token ?? crypto.randomUUID();
}

async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Section 4 — One-Click Unsubscribe Handler (RFC 8058 + 10-Day Window)

```typescript
// src/email/unsubscribe-handler.ts
// GET /unsubscribe?token=<token>  — link click
// POST /unsubscribe               — RFC 8058 one-click (body: List-Unsubscribe=One-Click)

export async function handleUnsubscribe(request: Request, env: Env): Promise<Response> {
  let token: string | null = null;

  if (request.method === 'GET') {
    token = new URL(request.url).searchParams.get('token');
  } else if (request.method === 'POST') {
    const body = await request.text();
    // RFC 8058: body is "List-Unsubscribe=One-Click"
    // Token must come from a signed URL in the List-Unsubscribe header
    token = new URL(request.url).searchParams.get('token');
  }

  if (!token) return new Response('Invalid request', { status: 400 });

  const consent = await env.DB.prepare(
    'SELECT id, email_hash FROM email_consents WHERE unsubscribe_token = ?'
  ).bind(token).first<{ id: string; email_hash: string }>();

  if (!consent) return new Response('Token not found', { status: 404 });

  const now = new Date().toISOString();
  await env.DB.prepare(`
    UPDATE email_consents
    SET unsubscribed_at = ?, updated_at = ?
    WHERE id = ?
  `).bind(now, now, consent.id).run();

  await env.DB.prepare(`
    INSERT INTO unsubscribe_events (id, email_hash, method, unsubscribed_at)
    VALUES (?, ?, ?, ?)
  `).bind(crypto.randomUUID(), consent.email_hash, request.method === 'POST' ? 'link' : 'link', now).run();

  // Queue suppression sync to ESP — must complete within 10 business days
  await env.EMAIL_QUEUE.send({
    type: 'SUPPRESS_IN_ESP',
    emailHash: consent.email_hash,
    unsubscribedAt: now,
  });

  if (request.method === 'POST') {
    return new Response(null, { status: 204 });
  }
  return new Response('<h1>Unsubscribed successfully</h1><p>You will no longer receive commercial emails from us.</p>', {
    headers: { 'Content-Type': 'text/html' },
  });
}
```

---

## Section 5 — CASL Implied Consent Expiry via Cron Trigger

CASL implied consent from a purchase expires after 2 years; from an inquiry, after 6 months.

```typescript
// src/email/casl-expiry.ts
// wrangler.toml cron: "0 4 * * *"

export async function expireCaslConsent(env: Env): Promise<void> {
  // Expire implied purchase consent after 2 years
  const purchaseExpiry = await env.DB.prepare(`
    UPDATE email_consents
    SET consent_type = 'none', consent_expires_at = datetime('now'), updated_at = datetime('now')
    WHERE jurisdiction = 'CA'
      AND consent_type = 'implied_purchase'
      AND consent_expires_at IS NOT NULL
      AND consent_expires_at <= datetime('now')
      AND unsubscribed_at IS NULL
  `).run();

  // Expire implied inquiry consent after 6 months
  const inquiryExpiry = await env.DB.prepare(`
    UPDATE email_consents
    SET consent_type = 'none', consent_expires_at = datetime('now'), updated_at = datetime('now')
    WHERE jurisdiction = 'CA'
      AND consent_type = 'implied_inquiry'
      AND consent_expires_at IS NOT NULL
      AND consent_expires_at <= datetime('now')
      AND unsubscribed_at IS NULL
  `).run();

  console.log(`CASL consent expiry: ${purchaseExpiry.meta.changes} purchase, ${inquiryExpiry.meta.changes} inquiry`);
}

// Helper to record new CASL implied consent
export async function recordCaslImpliedConsent(
  env: Env,
  email: string,
  type: 'implied_purchase' | 'implied_inquiry',
  source: string
): Promise<void> {
  const hash = await sha256Hex(email.toLowerCase());
  const expiresMonths = type === 'implied_purchase' ? 24 : 6;
  const expiresAt = new Date();
  expiresAt.setMonth(expiresAt.getMonth() + expiresMonths);

  await env.DB.prepare(`
    INSERT INTO email_consents
      (id, email_hash, email_encrypted, jurisdiction, consent_type, consent_source,
       consented_at, consent_expires_at, unsubscribe_token)
    VALUES (?, ?, ?, 'CA', ?, ?, datetime('now'), ?, ?)
    ON CONFLICT(email_hash) DO UPDATE SET
      consent_type = excluded.consent_type,
      consent_source = excluded.consent_source,
      consented_at = excluded.consented_at,
      consent_expires_at = excluded.consent_expires_at,
      updated_at = datetime('now')
    WHERE unsubscribed_at IS NULL
  `).bind(
    crypto.randomUUID(),
    hash,
    await encryptEmail(email, env),
    type,
    source,
    expiresAt.toISOString(),
    crypto.randomUUID()
  ).run();
}
```

---

## Section 6 — Bounce and Complaint Handling via Queue Consumer

Hard bounces and spam complaints must suppress the recipient immediately to avoid CAN-SPAM/CASL violations.

```typescript
// src/email/esp-webhook-consumer.ts
// Processes events from your ESP forwarded via Cloudflare Queue

interface EspEvent {
  type: 'bounce' | 'complaint' | 'unsubscribe';
  email: string;
  timestamp: string;
  bounceType?: 'hard' | 'soft';
  espMessageId?: string;
}

export async function processEspEvent(env: Env, event: EspEvent): Promise<void> {
  const hash = await sha256Hex(event.email.toLowerCase());

  if (event.type === 'bounce' && event.bounceType === 'hard') {
    // Hard bounce: permanently suppress
    await env.DB.prepare(`
      UPDATE email_consents
      SET unsubscribed_at = ?, updated_at = ?
      WHERE email_hash = ?
    `).bind(event.timestamp, event.timestamp, hash).run();

    await env.DB.prepare(`
      INSERT INTO unsubscribe_events (id, email_hash, method, unsubscribed_at)
      VALUES (?, ?, 'api', ?)
    `).bind(crypto.randomUUID(), hash, event.timestamp).run();
  }

  if (event.type === 'complaint') {
    // ISP spam complaint: suppress immediately (CAN-SPAM requirement)
    await env.DB.prepare(`
      UPDATE email_consents
      SET unsubscribed_at = ?, updated_at = ?
      WHERE email_hash = ?
    `).bind(event.timestamp, event.timestamp, hash).run();

    await env.DB.prepare(`
      INSERT INTO unsubscribe_events (id, email_hash, method, unsubscribed_at)
      VALUES (?, ?, 'api', ?)
    `).bind(crypto.randomUUID(), hash, event.timestamp).run();
  }
}
```

---

## Anti-Patterns

- **Sending commercial email before CASL consent** — CAN-SPAM allows opt-out, but CASL requires opt-in. Determine the recipient's jurisdiction before sending, not after complaints.
- **Subject line mismatch** — CAN-SPAM prohibits deceptive subject lines. Do not use "Re:" prefixes for first-contact emails.
- **Honouring opt-outs after 10 business days** — The 10-day window is a ceiling, not a target. Suppress within hours using queue-based processing.
- **Omitting physical address from batch emails** — Even automated marketing emails must carry a valid physical mailing address. PO boxes and mail-forwarding services satisfy this.
- **Relying on ESP suppression lists as your only store** — ESPs can lose suppression lists during migrations. Maintain your own canonical suppression in D1 and sync to the ESP.

---

## Gotchas

- **CASL applies to messages *received* in Canada, not just sent from Canada** — If your US company sends to a `@gmail.com` address used by someone in Montreal, CASL applies.
- **"Transactional" does not mean spam-exempt** — A receipt email that includes promotional upsells in the primary body becomes a commercial message under both regimes.
- **CASL implied consent documentation is your burden** — You must be able to prove when and how implied consent was established for every Canadian contact. Keep `consent_source` and `consented_at` for at least 3 years.
- **CASL is not enforced by the FTC** — CASL is enforced by the CRTC, Competition Bureau, and OPC. US lawyers are not sufficient for CASL compliance; engage Canadian counsel.

---

## Verification Checklist

- [ ] `compliance-gate.ts` is called before every `dispatchEmail()` invocation.
- [ ] All commercial messages include physical address and unsubscribe link.
- [ ] `List-Unsubscribe` and `List-Unsubscribe-Post` headers are set on all commercial messages.
- [ ] Canadian recipients have documented express or valid implied consent in D1 before first commercial send.
- [ ] CASL implied consent expiry cron runs daily and sets `consent_type = 'none'` on expired records.
- [ ] ESP bounce and complaint webhooks feed into the queue consumer within seconds.
- [ ] `unsubscribe_events.processed_at` is populated within 10 business days; alert fires if not.
- [ ] Suppression list is periodically synced back from D1 to ESP (prevent drift).

---

## Related Articles

- `gdpr-consent-management-cloudflare-workers.md`
- `gdpr-lawful-basis-workers-d1-consent.md`
- `data-retention-automated-deletion-workers.md`
- `audit-log-mandatory.md`
- `dmarc-aggregate-report-compliance-monitoring.md`

---

## Sources

- CAN-SPAM Act of 2003 (15 U.S.C. § 7701 et seq.)
- FTC CAN-SPAM Rule (16 CFR Part 316)
- Canada's Anti-Spam Legislation S.C. 2010, c. 23
- CRTC CASL Compliance and Enforcement Guidelines
- RFC 8058: "One-Click Unsubscribe" (January 2017)
- Google/Yahoo 2024 bulk sender requirements for List-Unsubscribe
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
