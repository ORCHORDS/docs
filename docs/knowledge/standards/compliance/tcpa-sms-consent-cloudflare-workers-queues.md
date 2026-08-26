# TCPA SMS Consent — Cloudflare Workers, D1, and Queues

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Managing Express Written Consent Under TCPA at Scale

The Telephone Consumer Protection Act (47 U.S.C. § 227) and its implementing FCC regulations (47 CFR Part 64) impose strict requirements on any autodialer or prerecorded-message SMS sent to consumers without prior express written consent. Statutory damages run from $500 to $1,500 per unlawful message, and class actions are common because each message to each subscriber is a separate violation. The FCC's 2024 one-to-one consent order (effective January 2025) further requires that consent be obtained from a single named sender — aggregated or shared consent across marketing partners is no longer valid.

The compliance architecture must handle four distinct obligations: (1) capturing and storing express written consent records that include the exact disclosure language shown to the user at opt-in; (2) processing opt-out requests within a maximum of 10 business days (FCC standard) — in practice, immediately; (3) screening every outbound message against do-not-call (DNC) registry data before dispatch; (4) preserving consent and opt-out records for a minimum of 4 years as litigation hold evidence. Workers handle the per-message routing decision; D1 is the authoritative consent store; Queues decouple opt-out processing from the inbound webhook path to ensure opt-outs are never lost under load.

Because TCPA litigation is common and discovery requests for consent records arrive years after the originating opt-in, the schema is designed to be append-only: consent records are never deleted in response to a Subject Access Request for deletion (consent evidence is retained for legal defence purposes, separate from the subscriber's marketing profile).

## Context

- Runtime: Cloudflare Workers (ES modules)
- Database: D1 (consent records, DNC screening cache)
- Queue: Cloudflare Queues (opt-out processing, outbound routing)
- Inbound SMS: Twilio / Bandwidth webhook → Worker
- Regulation: TCPA (47 U.S.C. § 227), FCC 47 CFR Part 64, FCC 2024 One-to-One Consent Order

## Express Written Consent Capture

At opt-in, the API records the phone number, the exact disclosure text presented to the user, the IP address, and the page URL as evidence of what the user agreed to. The `consent_text_hash` column stores a SHA-256 of the disclosure so future changes to the copy are detectable.

```ts
// src/handlers/consent-capture.ts
import { Env } from '../types';

interface ConsentPayload {
  phone: string;          // E.164 format
  consentText: string;    // Exact disclosure shown at opt-in
  sourceUrl: string;
  ipAddress: string;
  senderName: string;     // FCC 2024: must identify the specific sender
  signalType: 'web_form' | 'keyword' | 'paper';
}

async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function captureConsent(req: Request, env: Env): Promise<Response> {
  const body = await req.json<ConsentPayload>();
  const phone = body.phone.replace(/\D/g, '');
  if (!/^\+?1?\d{10}$/.test(phone)) {
    return new Response('Invalid phone number', { status: 400 });
  }
  if (!body.consentText || body.consentText.length < 30) {
    return new Response('Consent disclosure text required', { status: 400 });
  }

  const hash = await sha256Hex(body.consentText);
  const now = new Date().toISOString();

  // Check if already on DNC before accepting opt-in
  const onDnc = await env.DB.prepare(
    `SELECT 1 FROM dnc_list WHERE phone = ? AND active = 1`
  ).bind(phone).first();

  if (onDnc) {
    // Still record the attempt for audit; do not activate consent
    await env.DB.prepare(
      `INSERT INTO consent_records (phone, sender_name, consented_at, consent_text_hash,
         source_url, ip_address, signal_type, status)
       VALUES (?, ?, ?, ?, ?, ?, ?, 'blocked_dnc')`
    ).bind(phone, body.senderName, now, hash, body.sourceUrl, body.ipAddress, body.signalType).run();
    return new Response('Phone number on internal DNC list', { status: 422 });
  }

  await env.DB.prepare(
    `INSERT INTO consent_records (phone, sender_name, consented_at, consent_text_hash,
       consent_text, source_url, ip_address, signal_type, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')`
  ).bind(phone, body.senderName, now, hash, body.consentText, body.sourceUrl, body.ipAddress, body.signalType).run();

  return Response.json({ consentRecorded: true, consentedAt: now });
}
```

## Opt-Out Processing via Queues

Inbound STOP/UNSUBSCRIBE keywords arrive via webhook and are immediately enqueued rather than processed synchronously. This ensures that even if the D1 write path is temporarily slow, the opt-out intent is never lost. The Queue consumer updates the DNC list and revokes active consent records.

```ts
// src/handlers/inbound-sms.ts — enqueue opt-out intent
const OPT_OUT_KEYWORDS = new Set(['STOP', 'STOPALL', 'UNSUBSCRIBE', 'CANCEL', 'END', 'QUIT']);

export async function handleInboundSms(req: Request, env: Env): Promise<Response> {
  const form = await req.formData();
  const from = (form.get('From') as string ?? '').replace(/\D/g, '');
  const body = (form.get('Body') as string ?? '').trim().toUpperCase();

  if (OPT_OUT_KEYWORDS.has(body)) {
    await env.OPT_OUT_QUEUE.send({ phone: from, keyword: body, receivedAt: new Date().toISOString() });
    // Twilio expects TwiML response; return empty response to stop SMS from being sent
    return new Response('<Response></Response>', { headers: { 'Content-Type': 'text/xml' } });
  }
  // Route to inbound message handler...
  return new Response('<Response></Response>', { headers: { 'Content-Type': 'text/xml' } });
}

// src/consumers/opt-out-consumer.ts — Queue consumer
export async function processOptOut(batch: MessageBatch<{ phone: string; keyword: string; receivedAt: string }>, env: Env): Promise<void> {
  for (const msg of batch.messages) {
    const { phone, keyword, receivedAt } = msg.body;
    try {
      await env.DB.batch([
        env.DB.prepare(
          `INSERT OR REPLACE INTO dnc_list (phone, opted_out_at, keyword, active)
           VALUES (?, ?, ?, 1)`
        ).bind(phone, receivedAt, keyword),
        env.DB.prepare(
          `UPDATE consent_records SET status='revoked', revoked_at=?, revoke_reason=?
           WHERE phone=? AND status='active'`
        ).bind(receivedAt, `Keyword: ${keyword}`, phone),
        env.DB.prepare(
          `INSERT INTO opt_out_log (phone, keyword, processed_at) VALUES (?, ?, ?)`
        ).bind(phone, keyword, new Date().toISOString()),
      ]);
      msg.ack();
    } catch (err) {
      msg.retry(); // Queues will redeliver; opt-outs must not be dropped
    }
  }
}
```

## Pre-Send DNC Screening

Every outbound SMS is gated through a screening function. The Worker checks the internal DNC list in D1 and enforces the 4-year consent recency window. Federal DNC registry data is ingested nightly via a separate batch Worker and cached in D1.

```ts
// src/lib/dnc-screen.ts
export interface ScreeningResult {
  allowed: boolean;
  reason?: string;
  consentId?: number;
}

export async function screenRecipient(phone: string, senderName: string, env: Env): Promise<ScreeningResult> {
  // 1. Internal DNC check
  const onDnc = await env.DB.prepare(
    `SELECT opted_out_at FROM dnc_list WHERE phone = ? AND active = 1`
  ).bind(phone).first<{ opted_out_at: string }>();
  if (onDnc) return { allowed: false, reason: 'internal_dnc' };

  // 2. Federal DNC registry cache check
  const federalDnc = await env.DB.prepare(
    `SELECT 1 FROM federal_dnc_cache WHERE phone = ?`
  ).bind(phone).first();
  if (federalDnc) return { allowed: false, reason: 'federal_dnc' };

  // 3. Valid active consent check — FCC 2024: consent must be to this specific sender
  const consent = await env.DB.prepare(
    `SELECT id, consented_at FROM consent_records
     WHERE phone = ? AND sender_name = ? AND status = 'active'
     AND consented_at >= datetime('now', '-4 years')
     ORDER BY consented_at DESC LIMIT 1`
  ).bind(phone, senderName).first<{ id: number; consented_at: string }>();
  if (!consent) return { allowed: false, reason: 'no_valid_consent' };

  return { allowed: true, consentId: consent.id };
}
```

## D1 Schema and Litigation Hold

```sql
-- D1 schema: tcpa_compliance.sql
CREATE TABLE IF NOT EXISTS consent_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL,
  sender_name TEXT NOT NULL,
  consented_at TEXT NOT NULL,
  consent_text_hash TEXT NOT NULL,
  consent_text TEXT,          -- full disclosure copy for evidence
  source_url TEXT,
  ip_address TEXT,
  signal_type TEXT NOT NULL,  -- web_form | keyword | paper
  status TEXT NOT NULL DEFAULT 'active',  -- active | revoked | blocked_dnc
  revoked_at TEXT,
  revoke_reason TEXT
  -- NO DELETE permitted; records are litigation hold artefacts
);

CREATE TABLE IF NOT EXISTS dnc_list (
  phone TEXT PRIMARY KEY,
  opted_out_at TEXT NOT NULL,
  keyword TEXT,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS federal_dnc_cache (
  phone TEXT PRIMARY KEY,
  last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opt_out_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL,
  keyword TEXT NOT NULL,
  processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message_dispatch_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL,
  sender_name TEXT NOT NULL,
  consent_id INTEGER,
  dispatched_at TEXT NOT NULL,
  screening_result TEXT NOT NULL  -- 'allowed' | denial reason
);
```

## Anti-patterns

- Deleting consent records when a user requests data erasure under CCPA/GDPR — consent records are litigation hold evidence; erasure requests should remove the marketing profile and mark the consent record `revoked` but must not delete the row.
- Processing opt-outs synchronously in the inbound webhook response path — a timeout or downstream error will silently drop the opt-out, resulting in continued messages and statutory violations.
- Treating a single consent record as valid for multiple sender brands — FCC 2024 requires one-to-one consent; each sending entity needs its own consent record.
- Using approximate phone number normalisation — always normalise to E.164 before storage to prevent misses where `+12125551234` and `12125551234` are treated as different numbers.

## Gotchas

- The FCC's 2024 one-to-one consent rule was challenged in court; as of the knowledge cutoff the rule stands, but monitor FCC docket 21-402 for updates.
- STOP handling must work even if the subscriber never explicitly opted in — any STOP from any number must be honoured.
- "Express written consent" under TCPA requires a clear and conspicuous disclosure that the consumer is agreeing to receive autodialer messages; storing only a checkbox value is insufficient — store the full disclosure text.
- State mini-TCPA laws (Florida, Oklahoma, Washington) impose shorter opt-out processing windows and additional damages multipliers; screen for area codes mapped to those states.

## Verification

```ts
// tests/dnc-screen.spec.ts
import { expect, test } from 'vitest';
import { screenRecipient } from '../src/lib/dnc-screen';

test('number on internal DNC is blocked', async () => {
  const env = getMiniflareEnv();
  await env.DB.prepare(`INSERT INTO dnc_list (phone, opted_out_at, active) VALUES ('12125551234', '2025-01-01T00:00:00Z', 1)`).run();
  const result = await screenRecipient('12125551234', 'TestSender', env);
  expect(result.allowed).toBe(false);
  expect(result.reason).toBe('internal_dnc');
});

test('number with active consent is allowed', async () => {
  const env = getMiniflareEnv();
  await env.DB.prepare(
    `INSERT INTO consent_records (phone, sender_name, consented_at, consent_text_hash, signal_type, status)
     VALUES ('12125559999', 'TestSender', datetime('now'), 'abc123', 'web_form', 'active')`
  ).run();
  const result = await screenRecipient('12125559999', 'TestSender', env);
  expect(result.allowed).toBe(true);
});
```

## Related

- [can-spam-casl-email-workers-queues.md](can-spam-casl-email-workers-queues.md)
- [two-party-consent-call-recording.md](two-party-consent-call-recording.md)
- [ccpa-cpra-consumer-rights-operations.md](ccpa-cpra-consumer-rights-operations.md)
- [data-retention-policy-engineering.md](data-retention-policy-engineering.md)
- [gdpr-consent-management-cloudflare-workers.md](gdpr-consent-management-cloudflare-workers.md)

## Sources

- Telephone Consumer Protection Act (47 U.S.C. § 227): https://www.law.cornell.edu/uscode/text/47/227
- FCC 47 CFR Part 64 Subpart L: https://www.ecfr.gov/current/title-47/part-64/subpart-L
- FCC 2024 One-to-One Consent Order (Docket 21-402): https://www.fcc.gov/document/fcc-strengthens-consent-rules-combat-robotexts-and-robocalls
- Cloudflare Queues Documentation: https://developers.cloudflare.com/queues/
- National Do Not Call Registry: https://www.donotcall.gov/
