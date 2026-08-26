# jwt-algorithm-confusion-attack

**Issue:** JWT libraries that accept multiple algorithms allow attackers to switch RS256 tokens to HS256 and sign with the public key
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Some JWT libraries verify signatures using whatever algorithm is declared in the token header. An attacker takes a valid RS256 token, changes the header to `"alg": "HS256"`, and signs the modified payload with the server's public key (which is often publicly available). The server verifies the HMAC signature using the same public key and accepts the forged token.

## Pattern / Solution
```javascript
// INSECURE — accepts any algorithm from token header
jwt.verify(token, publicKey); // library uses alg from token header

// SECURE — explicitly specify allowed algorithms
jwt.verify(token, publicKey, { algorithms: ['RS256'] });

// SECURE — in jsonwebtoken (Node.js)
const payload = jwt.verify(token, publicKey, {
  algorithms: ['RS256'],
  issuer: 'https://auth.example.com',
  audience: 'https://api.example.com',
});
```
```python
# PyJWT — specify algorithms explicitly
import jwt
payload = jwt.decode(
    token,
    public_key,
    algorithms=['RS256'],  # never omit this
    options={'require': ['exp', 'iss', 'aud']}
)
```

## Gotchas
- Never pass `algorithms=None` or omit the algorithms parameter — it allows the attack.
- The `"alg": "none"` attack is related — always reject unsigned tokens unless intentionally designing for them.
- Rotate signing keys periodically; if the public key leaks, issued tokens become forgeable for their lifetime.
- Libraries before JOSE/JWT standardization (pre-2015) are more vulnerable — check your library version.

## Related
- `jwt-none-algorithm-attack.md`
- `jwt-best-practices.md`
- `jwt-pitfalls-2026.md`
