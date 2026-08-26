# jwt-none-algorithm-attack

**Issue:** JWT libraries that accept alg=none allow unsigned tokens to bypass authentication
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The JWT spec includes `"alg": "none"` for unsecured tokens. Vulnerable libraries accept this value and skip signature verification entirely, allowing any attacker to craft arbitrary claims by simply base64-encoding a header with `alg=none` and any payload.

## Pattern / Solution
```javascript
// Attack: forged token
// Header: {"alg":"none","typ":"JWT"}
// Payload: {"sub":"admin","role":"superadmin","exp":9999999999}
// Signature: (empty)
// Token: base64url(header).base64url(payload).

// SECURE — explicitly reject 'none'
jwt.verify(token, secret, { algorithms: ['HS256'] });
// Only HS256 is accepted; 'none' causes verification failure

// Validate before verification — check header manually
const [headerB64] = token.split('.');
const header = JSON.parse(Buffer.from(headerB64, 'base64url').toString());
if (header.alg === 'none') {
  throw new Error('Unsigned tokens not accepted');
}
```
```python
# PyJWT — algorithms list must not include 'none'
jwt.decode(token, key, algorithms=['HS256'])
# Raises DecodeError if alg=none is in token and not in allowed list
```

## Gotchas
- Case variations (`NONE`, `None`) may bypass naive string checks — let the library's algorithm allowlist handle it.
- Some libraries also accept `""` (empty string) for algorithm — test with both.
- Even with explicit algorithms, always validate `exp`, `iss`, and `aud` claims.
- Unit tests should include a token with `alg=none` as a negative test case.

## Related
- `jwt-algorithm-confusion-attack.md`
- `jwt-best-practices.md`
- `jwt-pitfalls-2026.md`
