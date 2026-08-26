# plain-text-fallback

**Issue:** Providing a plain-text alternative in multipart MIME email messages
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Some email clients, spam filters, and accessibility tools prefer or require a plain-text part alongside HTML.

## Pattern / Solution
1. Always send as `multipart/alternative` with both `text/plain` and `text/html` parts.
2. Plain text should convey all essential information, not just "View in browser".
3. Generate plain text from HTML using a library:
```js
import { htmlToText } from 'html-to-text';
const text = htmlToText(html, { wordwrap: 80 });
```
4. Or write plain text manually for important emails to ensure quality.
5. Most ESPs auto-generate plain text if not provided, but quality is poor; provide your own.

## Gotchas
- SpamAssassin scores poorly for HTML-only emails; plain text part improves deliverability.
- Auto-generated plain text often includes navigation noise and repeated whitespace.
- URLs in plain text should be full and untracked where possible (or use clearly labeled links).
- Some recipients have HTML disabled by policy (enterprise, legal); plain text is their only view.

## Related
- multipart-mime-structure, email-html-rendering-clients, email-spam-triggers, email-content-guidelines
