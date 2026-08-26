# Email Consent Audit Trail with Cloudflare D1

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A regulatory audit or a data subject access request (DSAR) demands proof that a
subscriber actively consented to receive email. The CRM contains only a boolean
`is_subscribed` flag — no timestamp, no IP address, no consent version, no record of
what the subscriber agreed to. Under GDPR Article 7, CASL, and CAN-SPAM, controllers
must demonstrate consent was freely given, specific, informed, and unambiguous. Without
a durable, tamper-evident audit trail, consent cannot be proven and fines follow.

## Context

GDPR requires that the data controller be able to demonstrate consent on demand. The
consent record must capture: who consented, when, to what (the exact wording of the
consent statement), which version of the privacy policy was in effect, and via which
channel (web form, import, API). Consent may also be withdrawn at any time, and the
withdrawal event must be preserved alongside the original grant — not as a deletion.

Cloudflare D1 is well-suited for this: it runs in the same Worker environment that
handles sign-up and unsubscribe flows, writes are transactional, and the data lives in
a region-configurable SQLite database that can be queried directly for DSAR fulfilment.

## Consent Event Schema

```sql
-- Immutable append-only log of consent events
CREATE TABLE consent_events (
  id              TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subscriber_id   TEXT    NOT NULL,
  email           TEXT    NOT NULL,
  event_type      TEXT    NOT NULL,   -- 'granted' | 'withdrawn' | 'updated' | 'imported'
  channel         TEXT    NOT NULL,   -- 'web_form' | 'api' | 'import' | 'double_opt_in'
  consent_text_id TEXT    NOT NULL,   -- FK to consent_texts.id
  ip_address      TEXT,               -- NULL if not available (e.g. server-side import)
  user_agent      TEXT,
  form_url        TEXT,               -- URL of the sign-up form at the time of consent
  source_metadata TEXT,               -- JSON blob for extra context (A/B variant, etc.)
  created_at      INTEGER NOT NULL    -- Unix ms, immutable
);

-- Versioned consent statement library
CREATE TABLE consent_texts (
  id           TEXT    PRIMARY KEY,   -- e.g. 'v3-marketing-en-2026-01-15'
  locale       TEXT    NOT NULL DEFAULT 'en',
  purpose      TEXT    NOT NULL,      -- 'marketing' | 'transactional' | 'both'
  body         TEXT    NOT NULL,      -- Full text shown to subscriber at consent time
  privacy_url  TEXT    NOT NULL,      -- URL of the privacy policy version in effect
  effective_at INTEGER NOT NULL,
  retired_at   INTEGER                -- NULL while active
);

-- Current effective state per subscriber (derived view, but materialised for speed)
CREATE TABLE subscriber_consent_state (
  subscriber_id   TEXT    PRIMARY KEY,
  email           TEXT    NOT NULL UNIQUE,
  current_state   TEXT    NOT NULL,   -- 'active' | 'withdrawn' | 'pending_doi'
  last_event_id   TEXT    NOT NULL,
  updated_at      INTEGER NOT NULL
);

CREATE INDEX idx_ce_subscriber ON consent_events(subscriber_id);
CREATE INDEX idx_ce_email       ON consent_events(email);
CREATE INDEX idx_ce_created_at  ON consent_events(created_at);
```

The `consent_events` table is append-only — no UPDATE or DELETE ever touches it. The
`subscriber_consent_state` table is a materialised view of the latest state for fast
"can I send to this address?" checks. Audit queries always go to `consent_events`.

## Recording Consent in a Worker

```typescript
// src/consent.ts
interface ConsentRecord {
  subscriberId: string;
  email: string;
  eventType: 'granted' | 'withdrawn' | 'updated' | 'imported';
  channel: 'web_form' | 'api' | 'import' | 'double_opt_in';
  consentTextId: string;
  ipAddress?: string;
  userAgent?: string;
  formUrl?: string;
  sourceMetadata?: Record<string, unknown>;
}

export async function recordConsent(db: D1Database, record: ConsentRecord): Promise<void> {
  const now = Date.now();
  const id = crypto.randomUUID();

  await db.batch([
    db.prepare(`
      INSERT INTO consent_events
        (id, subscriber_id, email, event_type, channel, consent_text_id,
         ip_address, user_agent, form_url, source_metadata, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      id,
      record.subscriberId,
      record.email,
      record.eventType,
      record.channel,
      record.consentTextId,
      record.ipAddress ?? null,
      record.userAgent ?? null,
      record.formUrl ?? null,
      record.sourceMetadata ? JSON.stringify(record.sourceMetadata) : null,
      now,
    ),
    db.prepare(`
      INSERT INTO subscriber_consent_state
        (subscriber_id, email, current_state, last_event_id, updated_at)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(subscriber_id) DO UPDATE SET
        current_state = excluded.current_state,
        last_event_id = excluded.last_event_id,
        updated_at    = excluded.updated_at
    `).bind(
      record.subscriberId,
      record.email,
      record.eventType === 'withdrawn' ? 'withdrawn' : 'active',
      id,
      now,
    ),
  ]);
}
```

`db.batch()` wraps both writes in a single D1 transaction so the event log and the state
table are never out of sync.

## Checking Consent Before Sending

```typescript
export async function hasActiveConsent(
  db: D1Database,
  email: string,
  purpose: 'marketing' | 'transactional',
): Promise<boolean> {
  const state = await db.prepare(
    'SELECT current_state, last_event_id FROM subscriber_consent_state WHERE email = ?'
  ).bind(email).first<{ current_state: string; last_event_id: string }>();

  if (!state || state.current_state !== 'active') return false;

  // Verify the consent text covers the requested purpose
  const event = await db.prepare(`
    SELECT ct.purpose FROM consent_events ce
    JOIN consent_texts ct ON ct.id = ce.consent_text_id
    WHERE ce.id = ?
  `).bind(state.last_event_id).first<{ purpose: string }>();

  return event?.purpose === purpose || event?.purpose === 'both';
}
```

## DSAR Fulfilment Query

When a data subject requests all records held about them:

```sql
SELECT
  ce.id               AS event_id,
  ce.event_type,
  ce.channel,
  ce.ip_address,
  ce.user_agent,
  ce.form_url,
  ce.source_metadata,
  ce.created_at,
  ct.purpose,
  ct.body             AS consent_text,
  ct.privacy_url
FROM consent_events ce
JOIN consent_texts ct ON ct.id = ce.consent_text_id
WHERE ce.email = ?
ORDER BY ce.created_at ASC;
```

This returns the full consent history including all grants and withdrawals in
chronological order — exactly what a regulator or data subject request requires.

## Consent Text Versioning

Whenever the marketing copy, privacy policy, or consent language changes, insert a new
row in `consent_texts` and retire the previous one:

```typescript
async function activateConsentText(db: D1Database, text: {
  id: string; locale: string; purpose: string;
  body: string; privacyUrl: string; effectiveAt: number;
}): Promise<void> {
  const now = Date.now();
  await db.batch([
    // Retire all active texts for this locale/purpose
    db.prepare(`
      UPDATE consent_texts SET retired_at = ?
      WHERE locale = ? AND purpose = ? AND retired_at IS NULL
    `).bind(now, text.locale, text.purpose),
    // Insert new active version
    db.prepare(`
      INSERT INTO consent_texts (id, locale, purpose, body, privacy_url, effective_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `).bind(text.id, text.locale, text.purpose, text.body, text.privacyUrl, text.effectiveAt),
  ]);
}
```

Always serve the active consent text from the database at form-render time — never
hardcode it in HTML — so the `consent_text_id` recorded at sign-up always matches the
exact text the subscriber read.

## Anti-patterns

- **Overwriting consent records**: updating a subscriber's consent row instead of
  inserting a new event destroys the audit trail. The events table must be insert-only.
- **Storing consent as a boolean flag in the subscribers table**: a flag carries no
  timestamp, no consent version, and no withdrawal history. Regulators treat this as
  insufficient proof.
- **Accepting bulk imports without explicit consent mapping**: importing a purchased or
  partner list without recording the original consent source, date, and text on a
  per-email basis violates GDPR and CAN-SPAM. Each imported address must have a
  verifiable consent origin.
- **Deleting consent records on unsubscribe**: GDPR requires the withdrawal event to
  be preserved, not that all records be erased. Proof of withdrawal is needed to defend
  against future re-subscribe complaints.

## Gotchas

- **IP address lawfulness**: storing IP addresses is itself personal data under GDPR.
  Document the legitimate interest (fraud prevention, consent proof) in your ROPA and
  set a retention period (e.g. 36 months) after which IPs are nulled, while the consent
  event record itself is retained.
- **Double opt-in flow**: the `pending_doi` state should be set at initial sign-up. Only
  the confirmed click event (via a tokenised link) flips `current_state` to `active` and
  records a `double_opt_in` channel event. Do not treat the initial sign-up as a grant.
- **D1 cross-region latency**: D1's primary is in a single region. For global sign-up
  forms, set `Location` to the subscriber's primary service region and accept the slight
  write latency rather than distributing consent data across multiple databases.
- **D1 row limits**: D1 databases are capped at 10 GB. A table with one row per consent
  event per subscriber is unlikely to approach this, but factor in a list of millions.

## Verification

1. Submit a sign-up form; query `consent_events` and confirm a `granted` row with the
   correct `consent_text_id`, IP, and timestamp within 1 s.
2. Click the unsubscribe link; confirm a `withdrawn` event appended and `subscriber_consent_state.current_state` = `'withdrawn'`.
3. Re-run the DSAR query for the test email and confirm the full event history is
   returned in chronological order.
4. Attempt to send a marketing email to a withdrawn subscriber via `hasActiveConsent()`;
   confirm it returns `false`.

## Related

- `gdpr-email-consent.md`
- `double-opt-in-flow.md`
- `one-click-unsubscribe-rfc8058-gdpr.md`
- `email-list-hygiene.md`
- `casl-canada-compliance.md`

## Sources

- GDPR Article 7 — conditions for consent: https://gdpr-info.eu/art-7-gdpr/
- ICO guidance on consent: https://ico.org.uk/for-organisations/guide-to-data-protection/guide-to-the-general-data-protection-regulation-gdpr/consent/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- CASL official guidance: https://crtc.gc.ca/eng/internet/anti.htm
