# postmessage-wildcard-origin

**Issue:** postMessage(data, "*") enables data exfiltration via malicious embedding
**Date:** 2026-08-09
**Repo:** example-org/example-repo at bc47a2fc
**Author:** the platform team
**Status:** fixed (bc47a2fc)

## Symptom
Embedded content widgets (EmbedCard, EmbedCertClient) used `postMessage(data, "*")` to communicate iframe height and content data to the parent frame. Any website could embed the widget and receive the postMessage data.

## Root cause
`window.parent.postMessage(payload, "*")` sends the message to ANY parent origin. An attacker embeds the widget on `evil.com`, receives the postMessage containing content data, and exfiltrates it.

## Fix
Derive the target origin from `document.referrer`:

```ts
function getTargetOrigin(): string {
  try {
    return new URL(document.referrer).origin;
  } catch {
    return "*"; // fallback for empty/unparseable referrer
  }
}

window.parent.postMessage(payload, getTargetOrigin());
```

## Verification
- **Test:** Embedding on evil.com does not receive postMessage (unless referrer matches)
- **CI:** PR #<number> green

## Gotchas
- `document.referrer` may be empty if the parent uses `Referrer-Policy: no-referrer` — the `"*"` fallback is still needed but is acceptable because no referrer means no embedding context to protect
- For high-security iframes, maintain an explicit allowlist of embedding origins instead of deriving from referrer
- The `message` event listener on the RECEIVING side should also validate `event.origin`
- Content-Security-Policy `frame-ancestors` is the server-side complement to this fix

## Related
- `lessons/example project-audit-2026-08.md`
- `security/owasp-top-10-2025.md` (XSS)
- `security/localstorage-api-url-hijack.md`
