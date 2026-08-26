# bulk-email-compliance-can-spam-gdpr

**Issue:** Bulk email compliance gaps on anonymous social platforms—
           missing unsubscribe mechanics, no GDPR consent records,
           and suppression lists that do not propagate reliably
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

ESP accounts receive abuse complaints or are suspended because
marketing emails lack a functioning unsubscribe link, or because
EU regulators flag the absence of a documented consent record.
Anonymous platform users (who signed up without verifying identity)
are receiving emails they do not remember opting into.

## Context

CAN-SPAM (US) and GDPR (EU) impose overlapping but distinct duties.
CAN-SPAM is opt-out: you may send until the user unsubscribes, as
long as you honour the request within 10 business days.  GDPR is
opt-in: you must have documented, freely given, specific, informed,
and unambiguous consent before sending marketing email—and be able
to prove it.  Anonymous platforms complicate both: users may share
a device, use throwaway addresses, or be minors, all of which change
the applicable rule.

## CAN-SPAM unsubscribe mechanics

Every commercial email must include a working unsubscribe link that
processes the opt-out within 10 business days.  For Workers-based
stacks the simplest pattern is a signed token in the link:

```js
// Build unsubscribe URL (sign with HMAC to prevent forgery)
async function buildUnsubLink(userId, emailType, env) {
  const payload = `${userId}:${emailType}:${Date.now()}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(env.UNSUB_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false, ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder()
    .encode(payload));
  const token = btoa(String.fromCharCode(...new Uint8Array(sig)));
  return `https://example.com/unsub?p=${encodeURIComponent(payload)}`
       + `&s=${encodeURIComponent(token)}`;
}
```

Also emit a `List-Unsubscribe` header with a `mailto:` and a
one-click POST URL (RFC 8058) so ESP and inbox providers can surface
the button in their native UI:

```
List-Unsubscribe: <mailto:unsub@example.com?subject=unsub-USER_ID>,
  <https://example.com/unsub/one-click?uid=USER_ID&tok=TOKEN>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

## GDPR consent records in D1

For EU users, record the full consent event—not just a boolean flag.

```sql
-- D1 schema
CREATE TABLE email_consents (
  id           TEXT PRIMARY KEY,          -- UUID
  user_id      TEXT NOT NULL,
  email_type   TEXT NOT NULL,             -- 'marketing', 'digest', …
  consent_text TEXT NOT NULL,             -- exact wording shown
  ip           TEXT,
  user_agent   TEXT,
  consented_at INTEGER NOT NULL,          -- Unix epoch ms
  withdrawn_at INTEGER,                   -- NULL = still active
  source       TEXT NOT NULL             -- 'signup', 'pref-center'
);
CREATE INDEX idx_consents_user ON email_consents (user_id);
```

On consent capture from the Worker:

```js
await env.DB.prepare(`
  INSERT INTO email_consents
    (id, user_id, email_type, consent_text, ip, user_agent,
     consented_at, source)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?)
`).bind(
  crypto.randomUUID(),
  userId, 'marketing',
  'I agree to receive marketing emails from Example (GDPR Art. 6(1)(a))',
  req.headers.get('CF-Connecting-IP'),
  req.headers.get('User-Agent'),
  Date.now(), 'signup',
).run();
```

Never store consent as a simple boolean column—you cannot reconstruct
what the user agreed to, when, or from where without the full record.

## Suppression list management in Workers KV

KV provides a fast globally-distributed suppression check that every
Worker can consult before dispatching a send.

```
┌──────────────────┬──────────────────────────────────────────┐
│ KV key pattern   │ Meaning                                  │
├──────────────────┼──────────────────────────────────────────┤
│ sup:u:<uid>:*    │ User-level suppression (all email types) │
│ sup:u:<uid>:<t>  │ Type-level (e.g. sup:u:123:marketing)   │
│ sup:e:<addr>     │ Email-address-level (e.g. bounced addr)  │
└──────────────────┴──────────────────────────────────────────┘
```

```js
export async function isSuppressed(userId, email, emailType, env) {
  const [global, typed, addr] = await Promise.all([
    env.SUP_KV.get(`sup:u:${userId}:*`),
    env.SUP_KV.get(`sup:u:${userId}:${emailType}`),
    env.SUP_KV.get(`sup:e:${email}`),
  ]);
  return !!(global || typed || addr);
}
```

Write to KV from the unsubscribe Worker endpoint, the bounce
webhook handler, and the complaint webhook handler:

```js
// On unsubscribe request
await env.SUP_KV.put(`sup:u:${userId}:${emailType}`, '1');
// Also withdraw the D1 consent record
await env.DB.prepare(
  'UPDATE email_consents SET withdrawn_at = ? '
+ 'WHERE user_id = ? AND email_type = ? AND withdrawn_at IS NULL'
).bind(Date.now(), userId, emailType).run();
```

## Mobile unsubscribe UX patterns

Mobile users are less likely to navigate to a preferences page.
Prioritise native inbox unsubscribe mechanisms:

```
┌──────────────────┬───────────────────────────────────────────┐
│ Mechanism        │ Mobile behaviour                          │
├──────────────────┼───────────────────────────────────────────┤
│ List-Unsubscribe │ Gmail app surfaces "Unsubscribe" button   │
│ (RFC 8058 POST)  │ next to sender name; no redirect needed  │
│ Footer link      │ Must work without JavaScript; many mobile │
│                  │ email clients open links in system browser│
│ Mailto: fallback │ Compose screen opens; user must send—     │
│                  │ completion rate is low, do not rely on it │
│ Reply STOP       │ Not standard for email; do not advertise  │
└──────────────────┴───────────────────────────────────────────┘
```

Landing pages for the footer unsubscribe link must confirm the
action in one tap—no password required, no CAPTCHA.  Pre-populate
all fields from the signed token in the URL.

## Anti-patterns

- Requiring a login to unsubscribe—CAN-SPAM prohibits requiring
  any information beyond the email address to process an opt-out.
- Storing `opted_in BOOLEAN DEFAULT FALSE` and calling it GDPR
  compliance—you need the consent event record, not just the flag.
- Writing suppression only to KV without mirroring to D1—if KV
  is cleared (namespace deletion, migration) suppressions are lost.
- Sending a "you've been unsubscribed" confirmation email to the
  address that just unsubscribed—CAN-SPAM allows it, but it re-
  engages the address and annoys users.
- Setting a 30-day delay before honouring unsubscribes—CAN-SPAM
  requires processing within 10 business days; best practice is
  immediate (synchronous KV write in the unsubscribe endpoint).

## Gotchas

- GDPR `legitimate interest` does not cover marketing email to EU
  users—only `consent` (Art. 6(1)(a)) or a pre-existing contract.
  Anonymous platforms rarely have a contract basis; always use
  explicit consent.
- CAN-SPAM applies to any commercial message with a US recipient,
  regardless of where the sender is based.  An EU company sending
  to US users must still comply.
- RFC 8058 one-click unsubscribe requires the POST to be
  `application/x-www-form-urlencoded` with the body
  `List-Unsubscribe=One-Click`.  A JSON body fails silently.
- KV `get` returns `null` for absent keys; treat null as "not
  suppressed" and never suppress on read errors—fail open to avoid
  blocking legitimate sends during KV outages.

## Verification

```bash
# Verify List-Unsubscribe header is present
curl -s -I https://example.com/email/preview | grep -i unsubscribe

# Test one-click POST (simulates Gmail inbox button)
curl -s -X POST 'https://example.com/unsub/one-click?uid=123&tok=T' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'List-Unsubscribe=One-Click'
# Expected: 200 OK, no redirect

# Confirm suppression was written
wrangler kv:key get --binding SUP_KV "sup:u:123:marketing"
# Expected: "1"

# Confirm D1 consent withdrawal
wrangler d1 execute DB \
  --command "SELECT withdrawn_at FROM email_consents
             WHERE user_id='123' AND email_type='marketing'"
```

## Related

- `documentation/docs/policies/email/can-spam-compliance.md`
- `documentation/docs/policies/email/gdpr-email-consent.md`
- `documentation/docs/policies/email/unsubscribe-handling-rfc.md`
- `documentation/docs/policies/email/suppression-list-management.md`
- `documentation/docs/policies/email/email-preference-center.md`

## Source URLs

- https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- https://gdpr-info.eu/art-6-gdpr/
- https://datatracker.ietf.org/doc/html/rfc8058
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
