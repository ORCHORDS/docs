# idempotency-keys

**Issue:** POST /api/x with the same Idempotency-Key should return the same result
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user's mobile app loses connectivity after they tap "Send Money"
in a payment flow. The request reached the server, the payment was
processed, but the response didn't reach the client. The app
retries. The user is charged twice.

## Root cause
**Non-idempotent POSTs are dangerous in any unreliable network.**
The client can't tell whether the previous request succeeded, so
it retries, and the server processes the same operation twice.

This is especially bad for:
- Payments (double charge)
- Email sends (duplicate email)
- Notifications (duplicate push)
- Webhook delivery (downstream confusion)

**Source:** Stripe API docs — idempotent requests:
https://stripe.com/docs/api/idempotent_requests

> "If a request fails for any reason ... you can safely retry the
> same request with the same idempotency key."

## Fix
Require an `Idempotency-Key` header on all state-changing POSTs.
Cache the result in a KV / D1 row keyed by the key + endpoint +
user. Replay the cached result on duplicate requests.

```ts
async function withIdempotency(
  request: Request,
  env: Env,
  handler: (body: unknown) => Promise<Response>
): Promise<Response> {
  const key = request.headers.get('idempotency-key');
  if (!key || key.length < 16) {
    return new Response('Missing Idempotency-Key header', { status: 400 });
  }

  const userId = (await authenticate(request, env))?.user.id;
  if (!userId) return new Response('Unauthorized', { status: 401 });

  const cacheKey = `idem:${userId}:${new URL(request.url).pathname}:${key}`;

  // Check for cached result
  const cached = await env.KV.get(cacheKey, 'json');
  if (cached) {
    return new Response(cached.body, {
      status: cached.status,
      headers: { ...cached.headers, 'x-idempotent-replay': 'true' },
    });
  }

  // Process the request
  const body = await request.json();
  const response = await handler(body);

  // Cache the result (24h TTL)
  if (response.status >= 200 && response.status < 300) {
    const responseBody = await response.clone().text();
    await env.KV.put(cacheKey, JSON.stringify({
      status: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      body: responseBody,
    }), { expirationTtl: 86400 });
  }

  return response;
}
```

The client generates a UUID per logical operation (e.g. one UUID
per "Send $50 to Alice" attempt). On retry, the client sends the
SAME UUID. The server recognizes the key and returns the cached
result.

## Verification
- **Test:** `test/idempotency.test.ts > same Idempotency-Key returns
  same result on retry` — passes
- **Test:** `test/idempotency.test.ts > different Idempotency-Keys
  produce different results` — passes
- **Live:** No double-charge incidents in production

## Gotchas
- **The cache must be per-user** (not global). Otherwise user A's
  key collision with user B's could replay the wrong result.
- **The cache must be per-endpoint.** A payment and a profile
  update with the same key would otherwise collide.
- **TTL: 24h is the industry default.** Stripe uses 24h. After
  that, retries must generate a new key.
- **Failed requests (5xx) are NOT cached.** A retry should be
  allowed to succeed. Only success (2xx) is cached.
- **The Idempotency-Key must be required, not optional.** If it's
  optional, clients forget to send it, and double-charge bugs creep
  in. Reject requests without the header (return 400).
- **Document the key format in your API docs.** "Must be a UUIDv4
  or a 16+ character random string, generated client-side."

## Related
- Stripe API: https://stripe.com/docs/api/idempotent_requests
- IETF draft: https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
