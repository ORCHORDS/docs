# Data Minimisation — PII Detection in Workers, D1 Redaction on Write, Tail Worker Log Scrubbing

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project users sometimes embed real names, emails, phone numbers, and national ID numbers in
posts, bios, or DMs. GDPR Art. 5(1)(c) requires that personal data be "adequate, relevant
and limited to what is necessary" (data minimisation). If example project stores raw PII in D1 rows
and Cloudflare Tail Worker logs, the platform carries unnecessary liability for data that
was inadvertently collected. Engineers need PII detection patterns in Workers, redaction
on write to D1, log scrubbing in Tail Workers, and mobile identifier pseudonymisation.

## Context

Data minimisation has three operational layers:

1. **Collection layer** — intercept PII in incoming payloads before it reaches D1.
2. **Storage layer** — redact or pseudonymise identifiers that must be kept for operational
   reasons (e.g. device IDs for fraud signals).
3. **Log layer** — scrub PII from structured logs before they leave the Cloudflare
   Tail Worker pipeline to downstream sinks (R2, external SIEM).

example project is anonymous-first; any real PII appearing in user-generated content is incidental
and should be detected and either blocked (for structured fields) or automatically
redacted (for free-text fields) before persistence.

## PII Pattern Reference Table

```
+------------------+------------------------------------------+--------------------+
| PII Type         | Detection Regex (simplified)             | Action             |
+------------------+------------------------------------------+--------------------+
| Email address    | /[\w.+-]+@[\w-]+\.[a-z]{2,}/gi           | Redact             |
| E.164 phone      | /\+?\d[\d\s\-().]{7,14}\d/g              | Redact             |
| EU IBAN          | /[A-Z]{2}\d{2}[\dA-Z]{11,30}/g           | Block post         |
| UK NI number     | /[A-Z]{2}\d{6}[ABCD]/gi                  | Block post         |
| US SSN           | /\b\d{3}-\d{2}-\d{4}\b/g                 | Block post         |
| IPv4 address     | /\b(?:\d{1,3}\.){3}\d{1,3}\b/g           | Truncate to /24    |
| IPv6 address     | /\b[0-9a-f:]{20,}\b/gi                   | Truncate to /48    |
| Credit card (PAN)| /\b(?:\d[ -]?){13,16}\d\b/g              | Block post / log   |
+------------------+------------------------------------------+--------------------+
```

## Workers PII Detection & Redaction Module

```typescript
// workers/src/lib/pii-redactor.ts

interface RedactionResult {
  redacted: string;
  detections: string[];   // list of detected types (no raw values)
  blocked: boolean;
}

const PATTERNS: Array<{ name: string; re: RegExp; action: 'redact' | 'block' }> = [
  { name: 'email',   re: /[\w.+\-]+@[\w\-]+\.[a-z]{2,}/gi,       action: 'redact' },
  { name: 'phone',   re: /\+?\d[\d\s\-().]{7,14}\d/g,             action: 'redact' },
  { name: 'iban',    re: /[A-Z]{2}\d{2}[\dA-Z]{11,30}/g,          action: 'block'  },
  { name: 'us_ssn',  re: /\b\d{3}-\d{2}-\d{4}\b/g,               action: 'block'  },
  { name: 'pan',     re: /\b(?:\d[\s-]?){13,16}\d\b/g,            action: 'block'  },
  { name: 'ipv4',    re: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g,          action: 'redact' },
];

const REPLACEMENT: Record<string, string> = {
  email:  '[email redacted]',
  phone:  '[phone redacted]',
  ipv4:   '[ip redacted]',
};

export function redactPii(input: string): RedactionResult {
  let text = input;
  const detections: string[] = [];
  let blocked = false;

  for (const { name, re, action } of PATTERNS) {
    re.lastIndex = 0;
    if (re.test(text)) {
      detections.push(name);
      if (action === 'block') {
        blocked = true;
        // Don't process further — caller should reject the payload
        break;
      }
      re.lastIndex = 0;
      text = text.replace(re, REPLACEMENT[name] ?? `[${name} redacted]`);
    }
  }

  return { redacted: text, detections, blocked };
}

// Truncate IPv4 to /24, IPv6 to /48 for log purposes
export function truncateIp(ip: string): string {
  if (ip.includes(':')) {
    // IPv6: keep first 3 groups
    const parts = ip.split(':');
    return parts.slice(0, 3).join(':') + '::';
  }
  // IPv4: zero last octet
  return ip.split('.').slice(0, 3).join('.') + '.0';
}
```

## D1 Redaction on Write

```typescript
// workers/src/routes/posts/create.ts
import { redactPii } from '../../lib/pii-redactor';

export async function handleCreatePost(request: Request, env: Env): Promise<Response> {
  const { body, sessionToken } = await request.json<{ body: string; sessionToken: string }>();

  const { redacted, detections, blocked } = redactPii(body);

  if (blocked) {
    return Response.json(
      { error: 'Post contains sensitive financial or government ID data', detections },
      { status: 422 }
    );
  }

  // Log detection event (no raw PII stored)
  if (detections.length > 0) {
    await env.DB.prepare(`
      INSERT INTO pii_detection_events (id, session_hash, types_detected, detected_at)
      VALUES (?, ?, ?, ?)
    `).bind(
      crypto.randomUUID(),
      sessionToken, // already pseudonymous HMAC token
      JSON.stringify(detections),
      Date.now()
    ).run();
  }

  // Write redacted text only
  const postId = crypto.randomUUID();
  await env.DB.prepare(`
    INSERT INTO posts (id, session_hash, body, created_at)
    VALUES (?, ?, ?, ?)
  `).bind(postId, sessionToken, redacted, Date.now()).run();

  return Response.json({ postId }, { status: 201 });
}
```

```sql
-- migrations/0020_pii_detection_events.sql
CREATE TABLE pii_detection_events (
  id              TEXT    PRIMARY KEY,
  session_hash    TEXT    NOT NULL,     -- pseudonymous; never raw user ID
  types_detected  TEXT    NOT NULL,     -- JSON array e.g. ["email","phone"]
  detected_at     INTEGER NOT NULL
);
-- Retained for 90 days max, then auto-deleted by retention Worker
CREATE INDEX idx_pde_detected ON pii_detection_events(detected_at);
```

## Tail Worker Log Scrubbing

```typescript
// workers/src/tail/log-scrubber.ts
// Deploy as a Tail Worker bound to the main example project Worker

import { redactPii, truncateIp } from '../lib/pii-redactor';

interface TailEvent {
  logs: Array<{ message: unknown[] }>;
  exceptions: Array<{ message: string }>;
  request: { url: string; headers: Record<string, string>; cf: { country: string } };
  response?: { status: number };
  scriptName: string;
}

export default {
  async tail(events: TailEvent[], env: { LOG_SINK: R2Bucket }): Promise<void> {
    const scrubbed = events.map(ev => ({
      ...ev,
      request: {
        // Strip full URL query string (may contain email tokens)
        url: scrubUrl(ev.request.url),
        // Remove PII-bearing headers
        headers: scrubHeaders(ev.request.headers),
        cf: { country: ev.request.cf?.country },
      },
      logs: ev.logs.map(log => ({
        ...log,
        message: log.message.map(m =>
          typeof m === 'string' ? redactPii(m).redacted : m
        ),
      })),
      exceptions: ev.exceptions.map(exc => ({
        ...exc,
        message: redactPii(exc.message).redacted,
      })),
    }));

    const batch = JSON.stringify(scrubbed);
    const key = `tail/${new Date().toISOString().slice(0,13)}/${crypto.randomUUID()}.json`;
    await env.LOG_SINK.put(key, batch, {
      httpMetadata: { contentType: 'application/json' },
    });
  }
};

function scrubUrl(raw: string): string {
  try {
    const u = new URL(raw);
    // Remove all query params except non-PII routing params
    const allowed = new Set(['tab', 'page', 'sort']);
    for (const k of [...u.searchParams.keys()]) {
      if (!allowed.has(k)) u.searchParams.delete(k);
    }
    return u.toString();
  } catch { return '[invalid url]'; }
}

const PII_HEADERS = new Set([
  'authorization', 'cookie', 'x-forwarded-for',
  'cf-connecting-ip', 'x-real-ip', 'x-device-id',
]);

function scrubHeaders(headers: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(headers)
      .filter(([k]) => !PII_HEADERS.has(k.toLowerCase()))
      .map(([k, v]) => [k, redactPii(v).redacted])
  );
}
```

## Mobile Identifier Pseudonymisation

```
Device installs example project app
        |
        v
Generate 32-byte random device secret (SecureRandom)
Store in iOS Keychain / Android Keystore (hardware-backed if available)
        |
        v
On each session: HMAC-SHA256(device_secret, server_salt) → session_token
        |
        v
Server sees only session_token (changes each time salt rotates — every 30 days)
        |
        v
Account deletion: delete device_secret locally → all session_tokens become
unresolvable; server can never re-link past activity
```

```
+------------------------+----------------------------------------------+
| Identifier type        | Pseudonymisation method                      |
+------------------------+----------------------------------------------+
| Device ID (iOS IDFV)   | HMAC-SHA256(IDFV, salt); rotate salt monthly |
| Device ID (Android AID)| HMAC-SHA256(AID, salt); same rotation        |
| IP address             | Truncate to /24 (v4) or /48 (v6)            |
| User-Agent             | Hash, never store raw                        |
| Push token (APNS/FCM)  | Store encrypted; AES-256-GCM, key in KMS    |
+------------------------+----------------------------------------------+
```

## Anti-patterns

- Running PII detection only on the frontend — malformed clients bypass it; always
  re-run server-side in the Worker.
- Logging raw `CF-Connecting-IP` in structured logs — truncate to /24 before any
  persistence.
- Treating pseudonymisation as anonymisation — HMAC tokens are still personal data
  under GDPR if the server holds the salt; apply GDPR obligations accordingly.
- Using a static global salt forever — rotate the HMAC salt periodically so historical
  tokens cannot be linked to new sessions after a data breach.
- Redacting PII in display output but storing raw in D1 — redaction must happen before
  the INSERT, not only in the SELECT/response path.

## Gotchas

- **Regex performance**: the PAN (credit card) pattern is expensive; run it only on
  free-text fields, not on short structured fields like usernames.
- **False positives**: phone-number patterns match ISBN-like numbers; add a confidence
  threshold or Luhn check for PANs; require `+` or country-code prefix for phones.
- **Tail Worker limits**: Tail Workers have a 128 MB memory limit and 10 s CPU budget
  per batch; for high-volume Workers, pipeline logs through a Queue to a batch consumer
  instead of scrubbing inline.
- **D1 constraint**: D1 does not support UPDATE-based row-level encryption natively;
  for fields requiring encryption at rest (push tokens), store in KV with encrypted
  values rather than D1 plaintext columns.
- **Art. 17 erasure**: pseudonymous session tokens do not satisfy erasure if the server
  holds the salt mapping; erasure must also delete or rotate the salt for that user's
  device.

## Verification

```bash
# Test PII redactor unit (Vitest)
cd workers && npx vitest run src/lib/pii-redactor.test.ts

# Confirm no raw emails appear in a sample D1 post body
wrangler d1 execute example project-prod \
  --command "SELECT body FROM posts WHERE body LIKE '%@%' LIMIT 10;"
# Expected: all rows show '[email redacted]' in place of email addresses

# Check Tail Worker R2 output contains no raw IPs
wrangler r2 object get example project-log-sink "tail/$(date -u +%Y-%m-%dT%H)/sample.json" \
  | jq '.[] | .request.url' | grep -E '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'
# Expected: no output (all IPs truncated or removed)

# Verify PII detection event table retention (should be ≤ 90 days of rows)
wrangler d1 execute example project-prod \
  --command "SELECT MIN(detected_at), MAX(detected_at), COUNT(*) FROM pii_detection_events;"
```

## Related

- `gdpr-lawful-basis-workers-d1-consent.md`
- `data-retention-automated-deletion-workers.md`
- `privacy-by-design-checklist.md`
- `gdpr-right-to-erasure-implementation.md`
- `gdpr-article-17-erasure.md`

## Sources

- GDPR Art. 4(5) (pseudonymisation), Art. 5(1)(c) (minimisation), Art. 25 (by design)
- EDPB Guidelines 4/2019 on pseudonymisation
- Cloudflare Tail Workers — developers.cloudflare.com/workers/observability/tail-workers
- OWASP Logging Cheat Sheet — owasp.org
- NIST SP 800-188 (de-identification of government datasets)
