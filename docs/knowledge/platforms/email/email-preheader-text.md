# email-preheader-text

**Issue:** Adding preheader text that appears in inbox preview next to the subject line
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Inbox preview text (shown after the subject) is one of the highest-impact elements for open rates yet often left as the first visible line of email body.

## Pattern / Solution
Add hidden preheader immediately after `<body>`:
```html
<span style="display:none;font-size:1px;color:#ffffff;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">
  Your preheader text here — 85-100 characters max to avoid truncation.
  &zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;
</span>
```
Keep preheader 85-100 characters; shorter texts may show body content after them.

## Gotchas
- Without filler spaces/zero-width non-joiners, inbox preview may show the next visible content.
- Some clients show more than 100 characters; filler prevents leaking structural HTML.
- Do not duplicate subject line in preheader; use complementary information.
- Emojis count toward character limit and display well in most modern clients.

## Related
- email-subject-line-best-practices, email-html-rendering-clients, email-a-b-testing
