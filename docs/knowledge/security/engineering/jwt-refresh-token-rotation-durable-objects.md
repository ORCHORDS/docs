# JWT Refresh Token Rotation with Workers Durable Objects

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Storing refresh tokens in Workers KV introduces race conditions: two simultaneous refresh requests can both succeed with the old token before KV propagation completes, enabling replay attacks. Durable Objects provide a single-threaded, strongly consistent actor that makes rotation truly atomic with no external locking.

## Context

OAuth 2.1 Section 6 mandates refresh token rotation — each use must invalidate the old token and issue a new one atomically. Workers KV's eventual consistency creates a TOCTOU window where a stolen token can be replayed across different edge PoPs before the invalidation propagates. A Durable Object instance scoped per user serialises all refresh operations behind a single-threaded actor, closing the replay window entirely. Token-family tracking detects potential theft when an already-rotated token is presented again.

## Durable Object Token Store

```typescript
import { DurableObject } from 'cloudflare:workers';

interface TokenRecord {
  token: string;
  family: string;       // rotation family — reused tokens in same family signal breach
  issuedAt: number;
  expiresAt: number;
  rotationCount: number;
}

export class RefreshTokenStore extends DurableObject<Env> {
  async rotate(incoming: string): Promise<{ newToken: string } | { error: string }> {
    const stored = await this.ctx.storage.get<TokenRecord>('current');

    if (!stored) return { error: 'no_token' };

    // Constant-time comparison to prevent timing oracle
    const expected = new TextEncoder().encode(stored.token);
    const provided  = new TextEncoder().encode(incoming);
    const same = expected.length === provided.length &&
      crypto.subtle.timingSafeEqual(expected, provided);

    if (!same) {
      // Mismatch inside an active family => potential breach; invalidate everything
      await this.ctx.storage.put('family_compromised', true);
      await this.ctx.storage.delete('current');
      return { error: 'token_reuse_detected' };
    }

    if (Date.now() > stored.expiresAt) {
      await this.ctx.storage.delete('current');
      return { error: 'token_expired' };
    }

    const newToken = crypto.randomUUID() + '-' + crypto.randomUUID();
    const next: TokenRecord = {
      token: newToken,
      family: stored.family,
      issuedAt: Date.now(),
      expiresAt: Date.now() + 30 * 24 * 60 * 60 * 1000, // 30-day sliding window
      rotationCount: stored.rotationCount + 1,
    };

    await this.ctx.storage.put('current', next);
    return { newToken };
  }

  async issue(userId: string): Promise<string> {
    const token = `${userId}-${crypto.randomUUID()}-${crypto.randomUUID()}`;
    const record: TokenRecord = {
      token,
      family: crypto.randomUUID(),
      issuedAt: Date.now(),
      expiresAt: Date.now() + 30 * 24 * 60 * 60 * 1000,
      rotationCount: 0,
    };
    await this.ctx.storage.put('current', record);
    return token;
  }

  async revoke(): Promise<void> {
    await this.ctx.storage.deleteAll();
  }

  async isCompromised(): Promise<boolean> {
    return (await this.ctx.storage.get<boolean>('family_compromised')) ?? false;
  }
}
```

## Worker Token Endpoint

```typescript
import { SignJWT } from 'jose';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/token') {
      const body = await request.formData().catch(() => null);
      if (!body || body.get('grant_type') !== 'refresh_token') {
        return Response.json({ error: 'unsupported_grant_type' }, { status: 400 });
      }

      const incoming = (body.get('refresh_token') as string | null)?.trim();
      if (!incoming) return Response.json({ error: 'invalid_request' }, { status: 400 });

      // Token format: {userId}-{uuid}-{uuid} — derive DO name from userId segment
      const userId = incoming.split('-')[0];
      if (!userId) return Response.json({ error: 'invalid_token' }, { status: 400 });

      const stub = env.REFRESH_TOKENS.get(env.REFRESH_TOKENS.idFromName(userId));
      const result = await stub.rotate(incoming);

      if ('error' in result) {
        const status = result.error === 'token_reuse_detected' ? 401 : 400;
        return Response.json({ error: result.error }, { status });
      }

      const secretKey = await crypto.subtle.importKey(
        'raw', new TextEncoder().encode(env.JWT_SECRET),
        { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
      );

      const accessToken = await new SignJWT({ sub: userId })
        .setProtectedHeader({ alg: 'HS256' })
        .setJti(crypto.randomUUID())
        .setIssuedAt()
        .setExpirationTime('15m')
        .sign(secretKey);

      return Response.json({
        access_token: <redacted-secret>
        token_type: 'Bearer',
        expires_in: 900,
        refresh_token: result.newToken,
      });
    }

    if (request.method === 'POST' && url.pathname === '/login') {
      // ... credential validation omitted
      const userId = 'user-123'; // resolved from credentials
      const stub = env.REFRESH_TOKENS.get(env.REFRESH_TOKENS.idFromName(userId));
      const refreshToken = await stub.issue(userId);
      return Response.json({ refresh_token: refreshToken });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Breach Response — Forced Logout on Reuse Detection

```typescript
async function handleTokenReuseDetected(userId: string, env: Env): Promise<void> {
  // Revoke DO state (already cleared inside rotate(), belt-and-suspenders)
  const stub = env.REFRESH_TOKENS.get(env.REFRESH_TOKENS.idFromName(userId));
  await stub.revoke();

  // Optionally: publish to a deny-list so active JTIs also stop working
  // until all access tokens expire (15-minute window)
  await env.BREACH_KV.put(`breach:${userId}`, '1', { expirationTtl: 900 });
}
```

## Anti-patterns

- Storing refresh tokens in Workers KV and performing read-then-delete — eventual consistency creates a replay window across PoPs
- Embedding user claims inside the refresh token body — the token is a bearer credential and must be opaque; claims belong in the access token
- Using a single Durable Object for all users — creates a serialisation hot-spot; scope one DO instance per user identity

## Gotchas

- `crypto.subtle.timingSafeEqual` requires both inputs to have the same `byteLength`; check lengths before calling or the comparison itself leaks via thrown TypeError
- Durable Object storage is billed per read/write; batch related reads with `getMultiple()` where possible to reduce cost on the hot path
- After a `token_reuse_detected` response, also invalidate in-flight access tokens via a short-lived KV deny-list keyed on the user ID, since access tokens issued before the breach detection remain valid until expiry

## Verification

```bash
# Login and get initial refresh token
REFRESH=$(curl -s -X POST https://api.example.com/login | jq -r .refresh_token)

# First rotation must succeed
NEW=$(curl -s -X POST https://api.example.com/token \
  -d "grant_type=refresh_token&refresh_token=$REFRESH" | jq -r .refresh_token)

# Replay old token — must return 401 token_reuse_detected
curl -s -X POST https://api.example.com/token \
  -d "grant_type=refresh_token&refresh_token=$REFRESH" | jq .error
```

## Related

- `security/jwt-sliding-window-refresh-workers-kv.md`
- `security/durable-objects-auth-patterns.md`
- `security/jwt-best-practices.md`

## Sources

- https://www.rfc-editor.org/rfc/rfc6749#section-6
- https://developers.cloudflare.com/durable-objects/
- https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics#section-4.14
