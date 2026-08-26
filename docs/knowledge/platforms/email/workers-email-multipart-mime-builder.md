# Building Multipart MIME Emails in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to send a rich email that contains both a plain-text fallback, an HTML
body, and an inline image (logo or signature graphic) embedded with a Content-ID
(CID) reference — all without an external email library. The MailChannels `/send`
endpoint accepts raw MIME as a base64-encoded string.

## Context

Multipart MIME follows a boundary-delimited structure:

```
multipart/related
  └─ multipart/alternative
       ├─ text/plain
       └─ text/html  (references cid:logo@example.com)
  └─ image/png (Content-ID: <logo@example.com>, Content-Disposition: inline)
```

Workers have `btoa()` for base64 encoding and `TextEncoder` for byte conversion.
No Node.js `Buffer` or `nodemailer` is available.

---

## Section 1 – Boundary and Header Helpers

```typescript
// src/lib/mime/boundary.ts

export function makeBoundary(prefix: string): string {
  const rand = crypto.randomUUID().replace(/-/g, '');
  return `${prefix}_${rand}`;
}

export function mimeHeader(name: string, value: string): string {
  return `${name}: ${value}\r\n`;
}

export function encodedWordSubject(text: string): string {
  // RFC 2047 Q-encoding for non-ASCII subjects
  const encoded = btoa(unescape(encodeURIComponent(text)));
  return `=?UTF-8?B?${encoded}?=`;
}
```

---

## Section 2 – Base64 Encoding for Binary Attachments

Workers do not have Node's `Buffer`. Use a `Uint8Array` → `btoa` path.

```typescript
// src/lib/mime/encode.ts

/**
 * Encode a Uint8Array to a base64 string, split into 76-char lines
 * as required by RFC 2045.
 */
export function uint8ToBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunkSize = 8192; // avoid call-stack overflows
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  const b64 = btoa(binary);
  // Fold at 76 characters per RFC 2045 §6.8
  return b64.match(/.{1,76}/g)?.join('\r\n') ?? b64;
}

/**
 * Encode a UTF-8 string to base64 (for text parts).
 */
export function stringToBase64(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return uint8ToBase64(bytes);
}
```

---

## Section 3 – Assembling the Full MIME Message

```typescript
// src/lib/mime/builder.ts

import { makeBoundary } from './boundary';
import { uint8ToBase64, stringToBase64 } from './encode';

export interface InlineImage {
  cid: string;          // e.g. "logo@example.com"
  filename: string;     // e.g. "logo.png"
  mimeType: string;     // e.g. "image/png"
  data: Uint8Array;
}

export interface MimeEmailOptions {
  from: string;
  to: string;
  subject: string;
  textBody: string;
  htmlBody: string;
  inlineImages?: InlineImage[];
}

export function buildMimeMessage(opts: MimeEmailOptions): string {
  const { from, to, subject, textBody, htmlBody, inlineImages = [] } = opts;

  const altBoundary = makeBoundary('alt');
  const relBoundary = makeBoundary('rel');

  const hasInline = inlineImages.length > 0;

  const lines: string[] = [];

  // Outer headers
  lines.push(`From: ${from}`);
  lines.push(`To: ${to}`);
  lines.push(`Subject: ${subject}`);
  lines.push('MIME-Version: 1.0');

  if (hasInline) {
    lines.push(`Content-Type: multipart/related; boundary="${relBoundary}"`);
  } else {
    lines.push(`Content-Type: multipart/alternative; boundary="${altBoundary}"`);
  }

  lines.push('');

  if (hasInline) {
    // Open related
    lines.push(`--${relBoundary}`);
    lines.push(`Content-Type: multipart/alternative; boundary="${altBoundary}"`);
    lines.push('');
  }

  // --- text/plain part ---
  lines.push(`--${altBoundary}`);
  lines.push('Content-Type: text/plain; charset=UTF-8');
  lines.push('Content-Transfer-Encoding: base64');
  lines.push('');
  lines.push(stringToBase64(textBody));
  lines.push('');

  // --- text/html part ---
  lines.push(`--${altBoundary}`);
  lines.push('Content-Type: text/html; charset=UTF-8');
  lines.push('Content-Transfer-Encoding: base64');
  lines.push('');
  lines.push(stringToBase64(htmlBody));
  lines.push('');

  lines.push(`--${altBoundary}--`);

  // --- inline image parts ---
  if (hasInline) {
    for (const img of inlineImages) {
      lines.push('');
      lines.push(`--${relBoundary}`);
      lines.push(`Content-Type: ${img.mimeType}; name="${img.filename}"`);
      lines.push('Content-Transfer-Encoding: base64');
      lines.push(`Content-Disposition: inline; filename="${img.filename}"`);
      lines.push(`Content-ID: <${img.cid}>`);
      lines.push('');
      lines.push(uint8ToBase64(img.data));
      lines.push('');
    }
    lines.push(`--${relBoundary}--`);
  }

  return lines.join('\r\n');
}
```

---

## Section 4 – Sending via MailChannels with Raw MIME

```typescript
// src/lib/mime/send.ts

import { buildMimeMessage, MimeEmailOptions } from './builder';

export async function sendMimeEmail(opts: MimeEmailOptions): Promise<void> {
  const raw = buildMimeMessage(opts);
  const encodedRaw = btoa(unescape(encodeURIComponent(raw)));

  // MailChannels accepts a pre-encoded raw MIME payload
  const payload = {
    personalizations: [{ to: [{ email: opts.to }] }],
    from: { email: opts.from },
    subject: opts.subject,
    // raw_message overrides content[] when present
    raw_message: encodedRaw,
  };

  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`MailChannels error ${res.status}: ${await res.text()}`);
  }
}
```

---

## Section 5 – Worker Entry Point

```typescript
// src/index.ts

import { sendMimeEmail } from './lib/mime/send';

export interface Env {
  LOGO_BUCKET: R2Bucket;  // store the logo PNG in R2
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Fetch the inline logo from R2
    const logoObject = await env.LOGO_BUCKET.get('logo.png');
    if (!logoObject) return new Response('logo not found', { status: 500 });
    const logoBytes = new Uint8Array(await logoObject.arrayBuffer());

    await sendMimeEmail({
      from: 'noreply@example.com',
      to: 'user@example.com',
      subject: 'Welcome to Orchords',
      textBody: 'Welcome! View this email in an HTML-capable client.',
      htmlBody: `<html><body>
        <img src="cid:logo@example.com" alt="Logo" width="200"/>
        <h1>Welcome to Orchords</h1>
        <p>Your account is ready.</p>
      </body></html>`,
      inlineImages: [
        {
          cid: 'logo@example.com',
          filename: 'logo.png',
          mimeType: 'image/png',
          data: logoBytes,
        },
      ],
    });

    return new Response('Sent', { status: 200 });
  },
};
```

---

## Anti-patterns

- **Using `btoa(rawString)` directly on multi-byte text** – breaks on any non-ASCII
  character. Always encode via `TextEncoder` → `uint8ToBase64`.
- **Skipping `Content-Transfer-Encoding: base64`** on binary parts – clients will
  display garbled data.
- **Nesting `multipart/related` inside `multipart/alternative`** – the correct
  nesting is `related` outermost, `alternative` inside it.
- **Using the same boundary string** for both the `related` and `alternative`
  levels – causes parsing failures in strict MIME parsers.

## Gotchas

- `btoa` in Workers accepts only Latin-1 strings. Binary data must go through
  the `String.fromCharCode` path shown in `uint8ToBase64`.
- MailChannels has a 25 MB limit on `raw_message`; large images should be hosted
  externally and linked with `<img src="https://…">`.
- CID references in HTML must match exactly: `cid:logo@example.com` in `<img>`
  and `<logo@example.com>` (with angle brackets) in the `Content-ID` header.
- Gmail sometimes strips inline images if the CID is not referenced in the HTML.

## Verification

```bash
# Upload a test logo to R2
wrangler r2 object put my-bucket/logo.png --file ./assets/logo.png

# Invoke the Worker locally
wrangler dev --local
curl http://localhost:8787/

# Inspect raw MIME output by adding a debug route that returns the raw string
# instead of calling sendMimeEmail, then paste into https://mimeparser.com
```

## Related

- `workers-email-threading-message-id.md`
- `workers-email-pgp-signature-verification.md`
- `workers-email-scheduled-digest-cron.md`

## Sources

- RFC 2045 – MIME Part One: Format of Internet Message Bodies
- RFC 2387 – The MIME Multipart/Related Content-type
- https://mailchannels.zendesk.com/hc/en-us/articles/4565898358413
- https://developers.cloudflare.com/r2/
