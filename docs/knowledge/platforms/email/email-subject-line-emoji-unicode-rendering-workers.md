# Email Subject Line Emoji & Unicode Rendering in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Subject lines with emoji or non-ASCII characters arrive garbled in some clients,
display as `=?UTF-8?B?...?=` blobs in logs, or trigger spam filters because the
encoding is malformed. The example project platform needs a Workers utility that encodes
subject lines correctly, validates emoji rendering support per ESP, and enforces
business rules (max emoji count, subject length after encoding, blocked codepoints).

---

## Context

RFC 2047 defines encoded-word syntax (`=?charset?encoding?encoded_text?=`) for
non-ASCII in headers. Modern ESPs (MailChannels, SendGrid, SES) accept raw UTF-8
subjects in MIME, but the underlying MTA must still fold long lines correctly.
Emoji occupy 2 bytes (UTF-16) or 4 bytes (UTF-8) and vary widely across clients:
- Gmail renders most Emoji 15.x codepoints.
- Outlook 2019/2021 renders only Emoji 12.
- Apple Mail renders everything in its OS Emoji font.

Subject line length limits: Gmail truncates display at ~77 characters; mobile clients
at ~30–40 characters. Encoded words inflate length: a single 4-byte emoji becomes
`=?UTF-8?B?8J+Ygg==?=` (20 characters). Workers perform encoding and validation
before handing off to MailChannels.

---

## Encoding Utility

```typescript
// src/email/subject.ts

/** Encode a subject line to RFC 2047 quoted-printable or base64 as needed. */
export function encodeSubject(raw: string): string {
  // If purely ASCII and ≤ 998 chars, pass through unchanged
  if (/^[\x20-\x7E]+$/.test(raw) && raw.length <= 998) return raw;

  // Split into words, encode only those containing non-ASCII
  const words = raw.split(' ');
  return words
    .map((word) => {
      if (/^[\x20-\x7E]+$/.test(word)) return word;
      // Base64 encode the UTF-8 bytes of the word
      const bytes = new TextEncoder().encode(word);
      const b64   = btoa(String.fromCharCode(...bytes));
      return `=?UTF-8?B?${b64}?=`;
    })
    .join(' ');
}

/** Decode an RFC 2047 subject for logging / display. */
export function decodeSubject(encoded: string): string {
  return encoded.replace(
    /=\?UTF-8\?B\?([A-Za-z0-9+/=]+)\?=/gi,
    (_, b64) => {
      const binary = atob(b64);
      const bytes  = Uint8Array.from(binary, (c) => c.charCodeAt(0));
      return new TextDecoder().decode(bytes);
    },
  );
}
```

---

## Emoji Validation and Normalisation

```typescript
// src/email/emoji.ts

/** Segmenter is available in the V8 runtime used by Workers. */
const segmenter = new Intl.Segmenter('en', { granularity: 'grapheme' });

export interface SubjectAudit {
  graphemeCount: number;
  emojiCount: number;
  hasZwjSequences: boolean;
  estimatedDisplayLength: number;   // chars as most clients would count
  warnings: string[];
}

const EMOJI_REGEX =
  /\p{Emoji_Presentation}|\p{Emoji}️|\p{Emoji_Modifier_Base}/u;

export function auditSubject(raw: string): SubjectAudit {
  const segments = [...segmenter.segment(raw)];
  const graphemes = segments.map((s) => s.segment);

  let emojiCount  = 0;
  let hasZwj      = false;
  const warnings: string[] = [];

  for (const g of graphemes) {
    if (EMOJI_REGEX.test(g)) {
      emojiCount++;
      if (g.includes('‍')) hasZwj = true;  // ZWJ sequence
    }
  }

  // Display length heuristic: emoji count as 2, ASCII as 1
  const estimatedDisplayLength = graphemes.reduce(
    (acc, g) => acc + (EMOJI_REGEX.test(g) ? 2 : g.length),
    0,
  );

  if (emojiCount > 3) {
    warnings.push(`High emoji density (${emojiCount}); may trigger spam filters.`);
  }
  if (estimatedDisplayLength > 77) {
    warnings.push(
      `Estimated display length ${estimatedDisplayLength} exceeds Gmail 77-char limit.`,
    );
  }
  if (hasZwj) {
    warnings.push('ZWJ sequences render inconsistently in Outlook 2019/2021.');
  }

  return {
    graphemeCount: graphemes.length,
    emojiCount,
    hasZwjSequences: hasZwj,
    estimatedDisplayLength,
    warnings,
  };
}
```

---

## Blocked Codepoint Policy

```typescript
// src/email/blocked-codepoints.ts

/**
 * Codepoints that major spam filters flag or that render as tofu in common clients.
 * Extend this list as intelligence is gathered via MailChannels rejection webhooks.
 */
const BLOCKED_RANGES: [number, number][] = [
  [0x1F910, 0x1F92F],  // Face with hand / sneezing — overused, flagged by SpamAssassin
  [0x1FA70, 0x1FAFF],  // Extended pictographs — Outlook 2019 tofu
  [0xE0000, 0xE01FF],  // Tags block — invisible chars used in phishing subjects
];

export function hasBlockedCodepoints(subject: string): boolean {
  for (const cp of subject) {
    const code = cp.codePointAt(0) ?? 0;
    if (BLOCKED_RANGES.some(([lo, hi]) => code >= lo && code <= hi)) {
      return true;
    }
  }
  return false;
}

export function stripBlockedCodepoints(subject: string): string {
  return [...subject]
    .filter((cp) => {
      const code = cp.codePointAt(0) ?? 0;
      return !BLOCKED_RANGES.some(([lo, hi]) => code >= lo && code <= hi);
    })
    .join('');
}
```

---

## Worker Pipeline Integration

```typescript
// src/email/pipeline.ts
import { encodeSubject }          from './subject';
import { auditSubject }           from './emoji';
import { hasBlockedCodepoints, stripBlockedCodepoints } from './blocked-codepoints';

export interface SubjectProcessResult {
  encoded: string;
  audit: ReturnType<typeof auditSubject>;
  modified: boolean;
}

export function processSubject(raw: string): SubjectProcessResult {
  let working = raw.trim();
  let modified = false;

  if (hasBlockedCodepoints(working)) {
    working  = stripBlockedCodepoints(working);
    modified = true;
  }

  // Truncate to keep display length within safe bounds
  const segs = [...new Intl.Segmenter('en', { granularity: 'grapheme' }).segment(working)];
  const EMOJI_REGEX = /\p{Emoji_Presentation}/u;
  let displayLen = 0;
  let cutAt = segs.length;

  for (let i = 0; i < segs.length; i++) {
    displayLen += EMOJI_REGEX.test(segs[i].segment) ? 2 : segs[i].segment.length;
    if (displayLen > 77) {
      cutAt    = i;
      modified = true;
      break;
    }
  }

  working = segs
    .slice(0, cutAt)
    .map((s) => s.segment)
    .join('');

  return {
    encoded:  encodeSubject(working),
    audit:    auditSubject(working),
    modified,
  };
}
```

---

## MailChannels Payload with Encoded Subject

```typescript
// src/email/send.ts
import { processSubject } from './pipeline';

export async function sendTransactional(
  to: string,
  rawSubject: string,
  htmlBody: string,
  textBody: string,
): Promise<Response> {
  const { encoded, audit, modified } = processSubject(rawSubject);

  if (audit.warnings.length > 0) {
    console.warn('Subject audit warnings:', audit.warnings);
  }

  const payload = {
    personalizations: [{ to: [{ email: to }] }],
    from:    { email: 'hello@example project.example.com', name: 'example project' },
    subject: encoded,
    content: [
      { type: 'text/plain', value: textBody },
      { type: 'text/html',  value: htmlBody  },
    ],
    headers: {
      'X-Subject-Modified': modified ? '1' : '0',
    },
  };

  return fetch('https://api.mailchannels.net/tx/v1/send', {
    method:  'POST',
    headers: { 'content-type': 'application/json' },
    body:    JSON.stringify(payload),
  });
}
```

---

## Logging Audit Results to Analytics Engine

```typescript
// src/email/analytics.ts
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';
import type { SubjectProcessResult }    from './pipeline';

export function logSubjectAudit(
  ae: AnalyticsEngineDataset,
  tenantId: string,
  campaignId: string,
  result: SubjectProcessResult,
): void {
  ae.writeDataPoint({
    blobs:   [tenantId, campaignId, result.audit.warnings.join('; ')],
    doubles: [
      result.audit.emojiCount,
      result.audit.estimatedDisplayLength,
      result.audit.hasZwjSequences ? 1 : 0,
      result.modified ? 1 : 0,
    ],
    indexes: [tenantId],
  });
}
```

---

## Anti-patterns

- **Encoding the entire subject as one encoded word** — produces a very long single
  token that some MTAs reject. Encode word-by-word instead.
- **Using QP encoding for emoji** — base64 is shorter and avoids `=` escaping of
  multi-byte sequences. Use QP only for text with sparse non-ASCII.
- **Counting `subject.length` for display length** — JavaScript `String.length`
  counts UTF-16 code units; emoji with surrogate pairs count as 2. Use
  `Intl.Segmenter` to count grapheme clusters.
- **Assuming all clients handle Emoji 15** — target Emoji 12 for maximum Outlook
  compatibility or provide a plain-text fallback subject via `X-Alt-Subject`.

---

## Gotchas

- `btoa()` in Workers requires converting the UTF-8 `Uint8Array` to a Latin-1 string
  first; passing a multi-byte string directly throws `InvalidCharacterError`.
- `Intl.Segmenter` is available in Workers runtime v8 but **not** in Miniflare < 3.
  Pin Miniflare ≥ 3 in `devDependencies`.
- Some DKIM signers canonicalise headers before signing; RFC 2047 words with embedded
  spaces can break if the MTA re-folds the subject line during canonicalisation.
  Keep each encoded word to a single token (no spaces inside the word being encoded).
- Gmail's promotions tab scoring partially weights subject emoji count; more than 2
  emoji in promotional mail raises tab classification probability.

---

## Verification

```typescript
// test/subject.test.ts
import { processSubject } from '../src/email/pipeline';

const cases: [string, { emojiCount: number; modified: boolean }][] = [
  ['Hello world',         { emojiCount: 0, modified: false }],
  ['🎉 Welcome 🎉 🎊',  { emojiCount: 3, modified: false }],
  ['Sale 1 now',    { emojiCount: 0, modified: true  }],  // tags block stripped
];

for (const [raw, expected] of cases) {
  const result = processSubject(raw);
  console.assert(result.audit.emojiCount === expected.emojiCount,   `emoji count`);
  console.assert(result.modified          === expected.modified,     `modified flag`);
}
```

---

## Related

- `email-subject-line-best-practices.md`
- `email-spam-score-preflight-workers.md`
- `email-a-b-subject-testing-workers-analytics-engine.md`
- `email-send-time-optimization-analytics-engine.md`
- `mime-encoded-words-rfc2047.md`

---

## Sources

- RFC 2047 — MIME (Multipurpose Internet Mail Extensions) Part Three: Message Header Extensions
- RFC 6532 — Internationalized Email Headers
- Unicode Emoji 15.1 data — https://unicode.org/reports/tr51/
- Litmus Email Client Emoji Support table — https://www.litmus.com/blog/emoji-in-email-subject-lines/
- MailChannels Send API — https://api.mailchannels.net/tx/v1/documentation
