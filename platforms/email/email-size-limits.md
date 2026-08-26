# email-size-limits

**Issue:** Understanding and staying within email size limits for deliverability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Oversized emails are deferred, clipped (Gmail), or rejected entirely by receiving mail servers.

## Pattern / Solution
Target limits:
- **Gmail clips:** HTML over 102 KB rendered size; shows "View entire message" link.
- **Most SMTP servers:** 10 MB total message limit (includes attachments base64-encoded).
- **Gmail/Google Workspace:** 25 MB attachment limit via web; 10 MB via API.
- **SendGrid/Mailgun:** 30 MB total message size via API.

Optimization:
1. Minify HTML: remove whitespace, comments, redundant attributes.
2. Use external images instead of inline CID for marketing emails.
3. Remove unused CSS; every byte counts.
4. Compress attachments where possible; link to large files instead.

## Gotchas
- Gmail clipping hides your tracking pixel and unsubscribe link; keep under 102 KB.
- Base64 encoding adds ~37% overhead to attachment sizes.
- Some corporate gateways enforce 5 MB limits regardless of upstream settings.

## Related
- email-attachment-patterns, email-inline-images-cid, email-html-rendering-clients, plain-text-fallback
