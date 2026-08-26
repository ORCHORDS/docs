# email-parsing-patterns

**Issue:** Reliably parsing email content, headers, and attachments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Raw email MIME messages are complex; parsing them correctly requires handling encoding, multipart, and threading headers.

## Pattern / Solution
Using `mailparser` (Node.js):
```js
import { simpleParser } from 'mailparser';
const parsed = await simpleParser(rawEmailBuffer);
const { from, to, subject, text, html, attachments, headers } = parsed;
// Thread correlation
const inReplyTo = headers.get('in-reply-to');
const references = headers.get('references');
```

Key fields:
- `from.value[0].address`: sender address
- `to.value[0].address`: recipient address
- `text`: plain text body
- `html`: HTML body (sanitize before storage)
- `attachments[].content`: Buffer of attachment content

Reply stripping with `email-reply-parser`:
```js
import EmailReplyParser from 'email-reply-parser';
const reply = new EmailReplyParser().read(text).getVisibleText();
```

## Gotchas
- Encoded words (`=?UTF-8?B?...?=`) in headers must be decoded; mailparser handles this.
- HTML from untrusted senders must be sanitized (use DOMPurify or sanitize-html).
- `text` may be null if no plain-text part; always check before accessing.

## Related
- inbound-email-processing, email-to-ticket-pattern, multipart-mime-structure, email-inline-images-cid
