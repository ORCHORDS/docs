# Anonymous Vote Integrity: Double-Vote Prevention in D1 / Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your anonymous social platform lets users upvote posts or react to content without a persistent account.
Within hours of launch, popular posts accumulate impossible vote counts. Bot scripts call
`POST /api/v1/posts/:id/vote` in tight loops. You need to prevent double-voting and vote stuffing while
preserving anonymity — you cannot store a user table mapping votes to identities.

---

## Context

Vote integrity on an anonymous platform is a harder problem than on an authenticated one. The classic
approach — store `(user_id, post_id)` and enforce a UNIQUE constraint — is unavailable when there is no
persistent user identity. The solution combines:

1. **Anonymous vote tokens** — a short-lived, post-scoped HMAC token derived from a stable browser
   fingerprint and a server secret. The server can verify the token without storing the fingerprint.
2. **D1 vote-commitment table** — stores hashed tokens (not the fingerprint) so the server knows a
   token has been used, without being able to reverse-engineer the voter's identity.
3. **Durable Objects for atomic counters** — prevents race conditions where two concurrent requests
   both read count=5 and both write count=6.
4. **Rate limiting per IP+ASN** — a secondary abuse backstop independent of token logic.

---

## 1. Generating the Anonymous Vote Token

The token is `HMAC-SHA256(secret, post_id || ":" || fingerprint || ":" || epoch_window)`.
The epoch window (e.g. floor(Date.now() / 3_600_000)) makes tokens expire automatically every hour
without a server-side clock check against stored state.

```typescript
// src/voting/token.ts
const WINDOW_MS = 3_600_000; // 1 hour

function epochWindow(): number {
  return Math.floor(Date.now() / WINDOW_MS);
}

async function hmac(
  secret: string,
  message: string
): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

export async function issueVoteToken(
  env: Env,
  postId: string,
  fingerprint: string // client-supplied, coarse — not treated as PII
): Promise<string> {
  const window = epochWindow();
  const payload = `${postId}:${fingerprint}:${window}`;
  const sig = await hmac(env.VOTE_TOKEN_SECRET, payload);
  // Token encodes window so the server can validate without clock lookup
  const raw = `${window}.${sig}`;
  return btoa(raw);
}

export async function verifyVoteToken(
  env: Env,
  postId: string,
  fingerprint: string,
  token: string
): Promise<boolean> {
  let decoded: string;
  try {
    decoded = atob(token);
  } catch {
    return false;
  }

  const [windowStr, providedSig] = decoded.split('.');
  const window = parseInt(windowStr, 10);
  const current = epochWindow();

  // Accept current window and the previous one (grace period for clock skew)
  if (current - window > 1 || window > current) return false;

  const payload = `${postId}:${fingerprint}:${window}`;
  const expectedSig = await hmac(env.VOTE_TOKEN_SECRET, payload);

  // Constant-time compare to prevent timing oracle on the HMAC
  const enc = new TextEncoder();
  const a = enc.encode(expectedSig);
  const b = enc.encode(providedSig);
  if (a.length !== b.length) return false;

  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
```

---

## 2. D1 Vote-Commitment Table

Store a hash of the token (not the token itself, not the fingerprint) so used tokens cannot be redeemed
again, and the database cannot be used to reconstruct voter identity.

```sql
-- Migration
CREATE TABLE vote_commitments (
  token_hash TEXT    PRIMARY KEY,   -- SHA-256 of the raw (pre-base64) token
  post_id    TEXT    NOT NULL,
  voted_at   TEXT    NOT NULL,      -- ISO8601
  expires_at TEXT    NOT NULL       -- ISO8601, epoch window end + 1 hour grace
);

CREATE INDEX idx_vote_commit_post ON vote_commitments(post_id);
CREATE INDEX idx_vote_commit_exp  ON vote_commitments(expires_at);
```

```typescript
// src/voting/commitment.ts
async function sha256Hex(value: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value)
  );
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

export async function commitVote(
  env: Env,
  rawToken: string, // decoded (pre-base64) token string
  postId: string
): Promise<boolean> {
  const tokenHash = await sha256Hex(rawToken);
  const now = new Date();
  const expires = new Date(now.getTime() + 2 * 3_600_000); // 2-hour window

  try {
    await env.DB.prepare(
      `INSERT INTO vote_commitments (token_hash, post_id, voted_at, expires_at)
       VALUES (?, ?, ?, ?)`
    )
      .bind(tokenHash, postId, now.toISOString(), expires.toISOString())
      .run();
    return true; // first use
  } catch (err: unknown) {
    // UNIQUE constraint violation = already voted
    if (err instanceof Error && err.message.includes('UNIQUE constraint failed')) {
      return false;
    }
    throw err;
  }
}
```

---

## 3. Atomic Vote Counter via Durable Objects

A D1 `UPDATE post_votes SET count = count + 1` is subject to race conditions under concurrent load.
Use a Durable Object as a serialized counter.

```typescript
// src/durable-objects/VoteCounter.ts
export class VoteCounter implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const action = url.searchParams.get('action');

    if (action === 'increment') {
      const current = (await this.state.storage.get<number>('count')) ?? 0;
      const next = current + 1;
      await this.state.storage.put('count', next);
      return Response.json({ count: next });
    }

    if (action === 'get') {
      const count = (await this.state.storage.get<number>('count')) ?? 0;
      return Response.json({ count });
    }

    return new Response('Bad Request', { status: 400 });
  }
}

// Usage in the vote handler:
export async function incrementVoteCount(
  env: Env,
  postId: string
): Promise<number> {
  const id = env.VOTE_COUNTER.idFromName(postId);
  const stub = env.VOTE_COUNTER.get(id);
  const resp = await stub.fetch(
    new Request(`https://internal/vote?action=increment`)
  );
  const data = await resp.json<{ count: number }>();
  return data.count;
}
```

---

## 4. The Vote Handler: Composing the Full Pipeline

```typescript
// src/handlers/vote.ts
import { verifyVoteToken } from '../voting/token';
import { commitVote } from '../voting/commitment';
import { incrementVoteCount } from '../durable-objects/VoteCounter';

export async function handleVote(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  postId: string
): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  const body = await request.json<{
    token: string;
    fingerprint: string;
  }>();

  if (!body.token || !body.fingerprint) {
    return new Response(JSON.stringify({ error: 'missing_fields' }), {
      status: 400,
    });
  }

  // 1. Verify HMAC token
  const valid = await verifyVoteToken(
    env,
    postId,
    body.fingerprint,
    body.token
  );
  if (!valid) {
    return new Response(JSON.stringify({ error: 'invalid_token' }), {
      status: 403,
    });
  }

  // 2. Commit to D1 (idempotency guard)
  const rawToken = atob(body.token); // decode to pre-base64 form for hashing
  const committed = await commitVote(env, rawToken, postId);
  if (!committed) {
    // Return 200 (not 409) to avoid leaking whether the fingerprint was seen before
    return Response.json({ success: true, deduplicated: true });
  }

  // 3. Increment atomic counter
  const newCount = await incrementVoteCount(env, postId);

  return Response.json({ success: true, count: newCount });
}
```

Returning 200 on a deduplicated vote (rather than 409 Conflict) prevents an attacker from probing
whether a given fingerprint has already been used.

---

## 5. Expiry Housekeeping

Expired vote commitments accumulate. Purge them in a scheduled Worker to keep the D1 table lean and
prevent scans from becoming expensive as the platform grows.

```typescript
// src/scheduled/purge-vote-commitments.ts
export async function purgeExpiredVoteCommitments(env: Env): Promise<void> {
  const result = await env.DB.prepare(
    `DELETE FROM vote_commitments WHERE expires_at < CURRENT_TIMESTAMP`
  ).run();

  console.log(`Purged ${result.meta.changes} expired vote commitments`);
}
```

Schedule in `wrangler.toml`:

```toml
[triggers]
crons = ["0 * * * *"]  # hourly
```

---

## Anti-patterns

- **Storing the raw fingerprint in vote_commitments** — a DB breach would link voting behavior to browser
  characteristics. Hash first, store the hash.
- **Using `Date.now()` for window comparison without a grace period** — tokens issued at 11:59 PM expire
  at 12:00 AM; clients with slightly slow clocks fail the next request. Allow a 1-window grace.
- **Trusting the fingerprint as a unique identity** — fingerprints are probabilistic. The system is
  designed to make vote stuffing expensive, not impossible. Layer with IP rate limiting.
- **Omitting the constant-time compare on HMAC verification** — a timing oracle on string comparison
  allows offline brute-force of the fingerprint.
- **Using D1 for the vote counter** — concurrent `UPDATE count = count + 1` races under load. Use
  Durable Objects for the counter, D1 for commitment history.

---

## Gotchas

- Durable Object IDs derived from `idFromName(postId)` are deterministic but globally routed — if your
  post IDs are sequential integers, IDs 1–100 all land in the same Cloudflare region. Use a UUID
  or hashed post ID to spread load.
- `crypto.subtle.digest` is not available in the global scope in some Workers polyfill environments
  during local dev. Always test with `wrangler dev --remote` for crypto behavior.
- D1's `INSERT OR IGNORE` does not return whether a row was inserted — use a plain `INSERT` and catch
  the constraint error to distinguish first-use from duplicate.
- Base64 `atob`/`btoa` in Workers uses the standard alphabet. URL-safe base64 (`-` and `_`) will cause
  `atob` to throw. Normalize before decoding.
- A compromised `VOTE_TOKEN_SECRET` invalidates all in-flight tokens instantly on rotation. Use
  `VOTE_TOKEN_SECRET_PREV` for a 1-hour overlap during rotation.

---

## Verification

```bash
# 1. Issue a token
TOKEN=$(curl -s -X POST https://api.example.com/api/v1/posts/post-123/vote-token \
  -H 'Content-Type: application/json' \
  -d '{"fingerprint":"abc123"}' | jq -r .token)

# 2. Cast vote
curl -s -X POST https://api.example.com/api/v1/posts/post-123/vote \
  -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\",\"fingerprint\":\"abc123\"}"

# 3. Attempt duplicate — should return 200 with deduplicated:true
curl -s -X POST https://api.example.com/api/v1/posts/post-123/vote \
  -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\",\"fingerprint\":\"abc123\"}"

# 4. Confirm commitment count in D1
wrangler d1 execute example project-db \
  --command="SELECT COUNT(*) FROM vote_commitments WHERE post_id = 'post-123';"
```

---

## Related

- `api-replay-prevention-nonce-d1-workers.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `durable-objects-auth-patterns.md`
- `timing-safe-compare.md`
- `account-enumeration-prevention.md`

---

## Sources

- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Web Crypto API HMAC — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
- OWASP Testing Guide — Testing for Vote Manipulation (WSTG-BUSL-08)
- D1 — https://developers.cloudflare.com/d1/
- Timing-safe comparison — https://codahale.com/a-lesson-in-timing-attacks/
