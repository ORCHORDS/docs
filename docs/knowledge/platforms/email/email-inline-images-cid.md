# email-inline-images-cid

**Issue:** Embedding images inline in emails using Content-ID (CID) references
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Externally hosted images may be blocked by email clients; inline CID images are always displayed without external requests.

## Pattern / Solution
1. Attach image with CID header:
```js
attachments: [{
  filename: 'logo.png',
  content: logoBuffer,
  cid: 'logo@yourdomain.com',
  contentDisposition: 'inline'
}]
```
2. Reference in HTML:
```html
<img src="cid:logo@yourdomain.com" alt="Logo" width="200" />
```
3. Image is embedded in MIME as `multipart/related` part; no external HTTP request.

## Gotchas
- CID images increase email size significantly; prefer externally hosted images for non-critical visuals.
- Gmail strips CID images in some contexts; always test in target clients.
- Outlook renders CID images reliably; Apple Mail and web clients vary.
- For marketing emails, externally hosted images with tracking are preferred; CID is better for transactional.

## Related
- email-attachment-patterns, multipart-mime-structure, email-html-rendering-clients, email-size-limits
