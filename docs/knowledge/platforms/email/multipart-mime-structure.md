# multipart-mime-structure

**Issue:** Understanding MIME structure for email messages with multiple parts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Email rendering issues and attachment problems often stem from incorrect MIME structure.

## Pattern / Solution
Standard hierarchy:
```
multipart/mixed          (has attachments)
  multipart/related      (has inline images)
    multipart/alternative
      text/plain
      text/html
    image/png (Content-ID: <logo@domain>)
  application/pdf (attachment)
```

- `multipart/alternative`: plain text + HTML versions; client picks best.
- `multipart/related`: HTML + inline images referenced by CID.
- `multipart/mixed`: adds file attachments to the above.

Use Nodemailer or similar library to handle MIME construction:
```js
const msg = {
  text: '...',
  html: '...',
  attachments: [{ filename: 'doc.pdf', content: buffer }]
};
```

## Gotchas
- Wrong nesting order causes some clients to show attachments as body or vice versa.
- Inline images in `multipart/related` must be referenced by CID: `<img src="cid:logo@domain">`.
- Base64-encoded parts should use 76-character line wrapping per RFC 2045.
- Content-Disposition: inline vs. attachment determines how clients display the part.

## Related
- email-attachment-patterns, email-inline-images-cid, plain-text-fallback, email-size-limits
