# Emergency Contact Escalation Feature in Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Anonymous confession and social platforms surface users in acute crisis — suicidal ideation, imminent self-harm, domestic violence, or medical emergency — with no way for the platform to contact emergency services because the user is anonymous. Without an opt-in emergency contact mechanism, the platform's only options are generic resource links that are rarely acted on by users in acute distress. A voluntary escalation feature lets users pre-register a trusted contact or opt into emergency-services escalation; the platform activates it when a crisis is detected, bridging anonymity with safety.

## Context

The system operates in two modes: voluntary pre-registration (user saves an encrypted emergency contact at account creation) and real-time crisis escalation (platform routes a de-identified crisis alert to a registered contact or national crisis line when the AI crisis-detection Worker fires a high-confidence signal). All personal data in the emergency contact record is encrypted at rest using a user-held key and is inaccessible to platform staff. Escalation is mediated through a third-party crisis API (e.g., Crisis Text Line partner API or equivalent) that accepts anonymised session data without requiring PII.

## Emergency Contact Registration

Users voluntarily register an emergency contact. The contact (email, phone) is encrypted with a key derived from the user's recovery token so the platform stores only ciphertext.

```typescript
// worker: emergency-contact-register.ts
export interface Env {
  DB: D1Database;
}

interface ContactPayload {
  contactType: 'email' | 'sms' | 'crisis_line';
  contactValue: string;   // plaintext email or phone number — encrypted before storage
  encryptionKeyB64: string; // AES-256-GCM key derived client-side from recovery token
}

export async function registerEmergencyContact(
  env: Env,
  accountId: string,
  payload: ContactPayload
): Promise<void> {
  // Import the user-supplied AES-256-GCM key
  const rawKey = Uint8Array.from(atob(payload.encryptionKeyB64), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    'raw', rawKey, { name: 'AES-GCM' }, false, ['encrypt']
  );

  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    cryptoKey,
    new TextEncoder().encode(payload.contactValue)
  );

  const stored = JSON.stringify({
    iv: btoa(String.fromCharCode(...iv)),
    ct: btoa(String.fromCharCode(...new Uint8Array(ciphertext))),
  });

  await env.DB.prepare(
    `INSERT INTO emergency_contacts (account_id, contact_type, encrypted_contact, created_at)
     VALUES (?1, ?2, ?3, unixepoch())
     ON CONFLICT(account_id) DO UPDATE SET
       contact_type      = excluded.contact_type,
       encrypted_contact = excluded.encrypted_contact,
       created_at        = unixepoch()`
  ).bind(accountId, payload.contactType, stored).run();
}
```

## Crisis Detection Integration and Escalation Trigger

When the AI crisis-detection Worker scores a post above a high-confidence threshold it calls the escalation Worker. The escalation Worker retrieves the user's emergency contact record (if any) and dispatches a de-identified alert.

```typescript
// worker: crisis-escalation.ts
export interface Env {
  DB: D1Database;
  CRISIS_API_TOKEN: string;
  CRISIS_API_URL: string;
}

interface CrisisSignal {
  accountId: string;
  sessionId: string;          // opaque per-session token
  crisisType: 'suicide' | 'self_harm' | 'domestic_violence' | 'medical';
  confidenceScore: number;    // 0-1
  contentSnippet: string;     // first 200 chars of triggering content
}

export async function escalateCrisis(
  env: Env,
  signal: CrisisSignal
): Promise<void> {
  if (signal.confidenceScore < 0.85) return; // only escalate high-confidence signals

  // Check for existing escalation within last 4 hours to prevent duplicates
  const recent = await env.DB.prepare(
    `SELECT escalation_id FROM crisis_escalations
     WHERE account_id = ?1 AND escalated_at > unixepoch() - 14400 LIMIT 1`
  ).bind(signal.accountId).first();

  if (recent) return;

  // Retrieve encrypted emergency contact (may be null — user may not have registered one)
  const contact = await env.DB.prepare(
    `SELECT contact_type, encrypted_contact FROM emergency_contacts
     WHERE account_id = ?1 LIMIT 1`
  ).bind(signal.accountId).first<{
    contact_type: string;
    encrypted_contact: string;
  }>();

  const escalationId = crypto.randomUUID();

  // Always route to platform-level crisis API first (de-identified)
  const alertPayload = {
    session_id: signal.sessionId,           // opaque — no PII
    crisis_type: signal.crisisType,
    confidence: signal.confidenceScore,
    has_contact: contact !== null,
    platform_note: signal.contentSnippet,
  };

  await fetch(env.CRISIS_API_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.CRISIS_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(alertPayload),
  });

  // Log escalation (never logs decrypted contact value)
  await env.DB.prepare(
    `INSERT INTO crisis_escalations
       (escalation_id, account_id, crisis_type, confidence, contact_type_used, escalated_at)
     VALUES (?1, ?2, ?3, ?4, ?5, unixepoch())`
  ).bind(
    escalationId,
    signal.accountId,
    signal.crisisType,
    signal.confidenceScore,
    contact?.contact_type ?? 'platform_only'
  ).run();
}
```

## Delivering the Crisis Alert to the Registered Contact

If a user pre-registered a contact and the platform holds the decryption capability (user provided key in the crisis activation flow), the alert is decrypted and routed. This path is optional and requires the user to have activated it.

```typescript
// worker: contact-notifier.ts  (called only when user has activated in-session key)
export interface Env {
  DB: D1Database;
  EMAIL_SENDER: string;     // from address
  EMAIL_API_URL: string;
  EMAIL_API_TOKEN: string;
}

export async function notifyRegisteredContact(
  env: Env,
  accountId: string,
  decryptionKeyB64: string,  // provided by the in-session user during crisis confirmation
  crisisType: string
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT contact_type, encrypted_contact FROM emergency_contacts
     WHERE account_id = ?1 LIMIT 1`
  ).bind(accountId).first<{ contact_type: string; encrypted_contact: string }>();

  if (!row) return false;

  const { iv: ivB64, ct: ctB64 } = JSON.parse(row.encrypted_contact) as {
    iv: string; ct: string;
  };

  const rawKey = Uint8Array.from(atob(decryptionKeyB64), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    'raw', rawKey, { name: 'AES-GCM' }, false, ['decrypt']
  );

  let contactValue: string;
  try {
    const iv = Uint8Array.from(atob(ivB64), (c) => c.charCodeAt(0));
    const ct = Uint8Array.from(atob(ctB64), (c) => c.charCodeAt(0));
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, cryptoKey, ct);
    contactValue = new TextDecoder().decode(plain);
  } catch {
    // Decryption failure — wrong key or tampered record; do not escalate to wrong contact
    return false;
  }

  if (row.contact_type === 'email') {
    await fetch(env.EMAIL_API_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.EMAIL_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: env.EMAIL_SENDER,
        to: contactValue,
        subject: 'Safety alert from a person who trusts you',
        text: `Someone who listed you as their emergency contact may need help right now. Crisis type: ${crisisType}. Please check in on them or contact emergency services if you believe they are in immediate danger.`,
      }),
    });
  }

  return true;
}
```

## In-App Safe Messaging Response

Independently of escalation, every crisis detection triggers an in-app response with local crisis resources, shown immediately and non-dismissibly for 5 seconds.

```typescript
// worker: safe-messaging-response.ts
export interface Env {
  DB: D1Database;
}

interface SafeMessagingResources {
  crisisLine: string;
  textLine: string;
  chatUrl: string;
  localNumber?: string;
}

const RESOURCES_BY_COUNTRY: Record<string, SafeMessagingResources> = {
  US: { crisisLine: '988', textLine: 'Text HOME to 741741', chatUrl: 'https://988lifeline.org' },
  GB: { crisisLine: '116 123', textLine: 'Text SHOUT to 85258', chatUrl: 'https://www.samaritans.org' },
  AU: { crisisLine: '13 11 14', textLine: 'Text 0477 13 11 14', chatUrl: 'https://www.lifeline.org.au' },
  DEFAULT: { crisisLine: '+1-800-273-8255', textLine: '', chatUrl: 'https://findahelpline.com' },
};

export function getSafeMessagingPayload(country: string): SafeMessagingResources {
  return RESOURCES_BY_COUNTRY[country] ?? RESOURCES_BY_COUNTRY['DEFAULT'];
}

export async function logSafeMessagingDisplay(
  env: Env,
  accountId: string,
  country: string
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO safe_messaging_log (account_id, country, displayed_at)
     VALUES (?1, ?2, unixepoch())`
  ).bind(accountId, country).run();
}
```

## Anti-patterns

- Storing plaintext emergency contact values in D1 — a database breach would expose the contact's identity and associate them with a user's crisis history; encrypt at the edge before storage
- Escalating every crisis-detection signal regardless of confidence score — AI classifiers produce false positives; require ≥ 0.85 confidence and consider a human-in-the-loop queue for 0.70–0.84 range
- Using the emergency contact notification path to re-identify the anonymous user — the contact message must not include the user's account ID, username, post content, or any detail that re-identifies them to the contact
- Skipping de-duplication of escalations — a user posting multiple times during a crisis should not generate one outbound notification per post; enforce a cooldown window (4 hours minimum)
- Making the emergency contact feature mandatory — coercion to provide a contact is a dark pattern; keep it strictly opt-in and offer opt-out with no friction

## Gotchas

- `crypto.subtle.importKey` with `extractable: false` prevents key export — pass `false` as the fourth argument; accidentally passing `true` in a Workers environment has no functional difference but is misleading
- AES-GCM decryption throws a `DOMException` (not a plain `Error`) on authentication failure — catch all exceptions, not just `instanceof Error`
- Crisis Text Line and equivalent partner APIs have allowlisted IP ranges; Cloudflare Workers egress IPs rotate — use a fixed egress IP via Cloudflare Aegis or a proxy with a static IP for the outbound crisis API call
- `CF-IPCountry` header returns `XX` for Tor exits and some VPNs; always provide a `DEFAULT` resource bucket for unknown countries
- `crypto.subtle.decrypt` is asynchronous; do not wrap in a non-async function and accidentally return a Promise<ArrayBuffer> unresolved

## Verification

1. Call `registerEmergencyContact` with a test email and a known AES-256-GCM key; confirm `encrypted_contact` in D1 is ciphertext (not plaintext) and decrypts correctly with the same key.
2. Call `escalateCrisis` with `confidenceScore = 0.84`; confirm no escalation row is inserted (below threshold).
3. Call `escalateCrisis` with `confidenceScore = 0.90`; confirm a row in `crisis_escalations` with `contact_type_used` matching the registered contact type, and that the crisis API received the request.
4. Call `escalateCrisis` again within 4 hours for the same `accountId`; confirm no second escalation is created.
5. Call `notifyRegisteredContact` with a wrong decryption key; confirm it returns `false` and no email is dispatched.
6. Call `getSafeMessagingPayload('GB')`; confirm the returned `crisisLine` is `'116 123'`.

## Related

- `crisis-intervention-detection-workers-ai.md`
- `safemessaging-compliance-response-workers.md`
- `self-harm-content-detection-workers-ai.md`
- `anonymous-account-recovery-verification-workers.md`
- `user-privacy-law-enforcement-requests.md`
- `anonymous-whistleblower-protection-tor-pipeline.md`

## Sources

- AFSP Safe Messaging Guidelines for media and platforms: https://afsp.org/safe-messaging-guidelines/
- Crisis Text Line Partner API documentation (private — request via partnership portal)
- Cloudflare Workers Web Crypto API — AES-GCM: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- GDPR Article 9 — special categories of personal data (health/crisis data): https://gdpr-info.eu/art-9-gdpr/
- Cloudflare Aegis — fixed egress IPs for Workers: https://developers.cloudflare.com/aegis/
