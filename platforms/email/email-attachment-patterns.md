# email-attachment-patterns

**Issue:** Best practices for sending file attachments in email
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Emails with attachments have lower deliverability and are more likely to be blocked by corporate filters.

## Pattern / Solution
1. Prefer links over attachments for large files; attach only when recipient expects a file.
2. Common safe attachment types: PDF, DOCX, XLSX, PNG, JPG, CSV.
3. Avoid attaching executables, scripts, or ZIP files containing executables (blocked universally).
4. Size limit: keep attachments under 5 MB total; many servers reject over 10 MB.
5. With Nodemailer:
```js
attachments: [{
  filename: 'invoice.pdf',
  content: pdfBuffer,
  contentType: 'application/pdf'
}]
```

## Gotchas
- ZIP files are blocked by many enterprise mail gateways regardless of content.
- Inline images (Content-Disposition: inline) are not the same as attachments (Content-Disposition: attachment).
- Microsoft Office files trigger antivirus scanning and can delay delivery.
- Total message size including base64 overhead is ~137% of original file size.

## Related
- email-inline-images-cid, multipart-mime-structure, email-size-limits, email-spam-triggers
