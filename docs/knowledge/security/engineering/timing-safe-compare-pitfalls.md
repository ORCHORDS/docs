# timing-safe-compare-pitfalls

**Issue:** timingSafeEqual implementations leak secret length
**Date:** 2026-08-09
**Repo:** example-org/example-repo at b12fe5d1
**Author:** the platform team
**Status:** fixed (e2557bf7)

## Symptom
Webhook signature verification using `timingSafeEqual(expected, actual)` with an early-return on length mismatch leaks the secret's byte length via timing side-channel.

## Root cause
The standard pattern `if (a.length !== b.length) return false` before the XOR loop creates a measurable timing difference. An attacker controlling one input can binary-search for the secret's length by sending payloads of varying lengths and measuring response time.

Three independent implementations in example project had this bug:
- `lib/crypto.ts` (shared)
- `admin/adminLogin.ts` (local copy)
- `auth/totp.ts` (local copy)

## Fix
Double-HMAC comparison: HMAC both inputs with a random ephemeral key, then compare the fixed-length digests. The comparison always runs in constant time regardless of input lengths.

```ts
export function secureTokenCompare(a: string, b: string): boolean {
  const key = crypto.getRandomValues(new Uint8Array(32));
  const enc = new TextEncoder();
  const hmacA = await crypto.subtle.sign("HMAC", key, enc.encode(a));
  const hmacB = await crypto.subtle.sign("HMAC", key, enc.encode(b));
  return timingSafeEqual(new Uint8Array(hmacA), new Uint8Array(hmacB));
}
```

## Verification
- **Test:** Webhook endpoints (stream, alerts, tierUpgrade, KYC) authenticate correctly
- **CI:** PR #<number> green
- **Live:** Production deployment successful

## Gotchas
- Do NOT pad to max length — the padding itself creates a timing signal if the pad operation is length-dependent
- Do NOT use `===` for any secret comparison, even "just checking if it's empty"
- The double-HMAC pattern works for variable-length secrets; for fixed-length secrets (e.g. 32-byte keys), a simple length check + timingSafeEqual is acceptable
- Cloudflare Workers support `crypto.subtle.digest (HMAC-based comparison — timingSafeEqual does NOT exist in WebCrypto)` natively

## Related
- `security/owasp-top-10-2025.md`
- `lessons/example project-audit-2026-08.md`
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
