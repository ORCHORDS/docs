# mobile-api-design

**Issue:** API design specifically for mobile clients
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship an API that works great for the web app. The mobile
team uses the same API. The mobile app is slow on cellular.
The mobile team asks for "a different API." You build a
parallel mobile API. Now you maintain 2 APIs.

## Root cause
**Mobile has different constraints than web:**
- Slower networks (3G/4G/5G, not always wifi)
- Higher latency (round-trip is expensive)
- Limited battery
- Limited data plan
- App updates are slow (App Store review, etc.)

A web-friendly API may not be mobile-friendly.

**Source:** Various mobile API design guides.

## The 5 mobile-API design principles

### 1. Minimize requests
Each request is a round-trip + serialization + parse. On a
slow network, 1 round-trip = 100ms+. 10 round-trips = 1s+.

**Solution:** Aggregate. Provide a "dashboard" endpoint that
returns everything the home screen needs in 1 call.

```ts
// ❌ Multiple calls
GET /api/users/me
GET /api/posts/recent
GET /api/notifications/unread
GET /api/messages/unread

// ✅ One call
GET /api/dashboard
// Returns: { user, posts, notifications, messages }
```

### 2. Use compression
gzip or brotli compress all responses. For text-based
formats (JSON, HTML), the compression ratio is 5-10x. For
binary (images, video), it's already compressed.

```ts
// CF Workers auto-compress if Accept-Encoding: gzip is sent
const response = new Response(JSON.stringify(data), {
  headers: {
    'content-type': 'application/json',
    'content-encoding': 'gzip',  // CF can do this automatically
  },
});
```

### 3. Use efficient data formats
JSON is the standard, but for high-volume data:
- **Protocol Buffers** (protobuf): ~3-10x smaller than JSON
- **MessagePack:** ~2x smaller, JSON-compatible
- **CBOR:** similar to MessagePack

For most apps, JSON is fine. For high-volume (millions of
requests), protobuf is worth it.

### 4. Support offline / sync
Mobile users go offline. The API should:
- **Idempotency keys** (POST/PATCH) for retry safety
- **ETags / If-None-Match** for "give me new data only"
- **Timestamps** for "give me data changed since X"
- **Cursor-based pagination** (not offset-based)

```ts
// Server: respond with the latest timestamp
const response = {
  data: [...],
  timestamp: Date.now(),
  nextCursor: '...',
};
response.headers.set('ETag', hashOfResponse);

// Client: send the previous timestamp
const ifNoneMatch = localStorage.getItem('lastETag');
if (ifNoneMatch) {
  request.headers.set('If-None-Match', ifNoneMatch);
}
// Server returns 304 if unchanged
```

### 5. Optimize for the most common case
- The home screen is the most-trafficked. Optimize for it.
- The login screen is critical. Make it fast.
- Cold start (first request) is the slowest. Pre-warm with
  a small "ping" call.

## The "mobile-first" endpoint design

For a mobile app, the API should support:
- **Pagination (cursor-based):** the client knows where to
  resume
- **Sparse fieldsets:** the client requests only the fields
  it needs
- **Partial responses:** the server returns only what changed
- **Bulk operations:** POST multiple items in one request

```ts
// Sparse fieldsets
GET /api/users/u_123?fields=id,email,displayName
// Returns: { id: 'u_123', email: 'a@x.test', displayName: 'Alice' }

// Partial response
GET /api/users/u_123?since=2026-08-01
// Returns: { id: 'u_123', email: 'a@x.test' } if email changed
// 304 Not Modified if nothing changed

// Bulk operations
POST /api/posts/bulk
// Body: [{ title: 'A', body: '...' }, { title: 'B', body: '...' }]
// Returns: [{ id: 'p_1' }, { id: 'p_2' }]
```

## The "cold start" problem

The first request from a mobile app is slow:
- DNS lookup: ~50ms
- TCP connection: ~100ms
- TLS handshake: ~100-200ms
- First server response: ~200-500ms

Total: ~500-1000ms for the first request.

**Mitigations:**
- **HTTP/2 connection reuse** (mobile OS does this)
- **DNS prefetch** (resolve DNS at app launch, not first use)
- **TLS session resumption** (server-side)
- **Preconnect** to the API domain (warm the connection)

## The "background sync" pattern

For real-time-feeling data without a WebSocket:
- The mobile app polls every 30 seconds
- Server returns "no change" (304) most of the time
- Server returns full data when there's a change
- App uses the latest data on next foreground

```ts
// Client
async function poll() {
  const res = await fetch('/api/posts/recent', {
    headers: { 'If-None-Match': localStorage.getItem('etag') },
  });
  if (res.status === 304) return;  // No change
  const data = await res.json();
  localStorage.setItem('etag', res.headers.get('ETag'));
  updateUI(data);
}

setInterval(poll, 30_000);
```

## The "API key vs session" choice

For a mobile app:
- **Session cookie:** works in browser, but mobile apps have
  issues (cookies in WKWebView are tricky)
- **API key:** simple, works in any context
- **JWT:** stateless, but revocation is hard
- **OAuth with refresh token:** the right answer for long-
  lived apps

For a 21+ social platform with mobile apps, **OAuth with
refresh tokens** is the right answer. The access token (short
lived) is used for API calls; the refresh token (long lived)
is used to get a new access token.

## Verification
- **Test:** `test/mobile-api.test.ts > single dashboard
  endpoint returns all needed data` — passes
- **Live:** Mobile app performance is monitored (time to
  first content, time to interactive)
- **Audit:** Quarterly review of API size + round-trip count

## Gotchas
- **The mobile OS may background the app.** A setInterval
  doesn't fire when the app is backgrounded. Use OS-level
  background fetch (iOS: BGAppRefreshTask; Android:
  WorkManager).
- **The "always-online" assumption is wrong.** Mobile users
  are often offline. Design for offline-first.
- **Cellular networks have higher latency** than wifi. A
  request that takes 50ms on wifi may take 500ms on 3G.
- **The app's network library** can pool connections. Use
  HTTP/2 (or HTTP/3) for connection reuse.
- **Push notifications** are the right answer for "wake the
  app up for this." Don't poll for important events.
- **Battery usage** matters. Background sync every 30s kills
  battery. Sync every 5 minutes + on app foreground.

## Related
- `api-versioning.md`
- `cache-strategies.md`
- `idempotency-keys.md`
- `api-key-authentication.md`
- Apple HIG: https://developer.apple.com/design/human-interface-guidelines/
- Android: https://developer.android.com/develop/connectivity/network-ops
