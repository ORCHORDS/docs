# iOS Push Notifications: APNs via Cloudflare Workers

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Push notifications are delivered on Android (via FCM) but
not on iOS. Alternatively, notifications arrive but are
stale — a new message collapses the old one but the user
sees both. Background content refreshes drain battery.
APNs tokens expire silently and the Worker continues
sending to invalid device tokens without surfacing errors.

## Context

The example project platform (example.com) sends push
notifications from Cloudflare Workers directly to APNs
using the HTTP/2 provider API. No Firebase intermediary
is used on the iOS path. This reduces latency and removes
a third-party dependency, but requires the Worker to
manage APNs JWT token generation and renewal.

---

## 1. APNs HTTP/2 vs Firebase (FCM) Proxy

| Dimension              | APNs Direct (HTTP/2)   | FCM → APNs Proxy       |
|------------------------|------------------------|------------------------|
| Delivery latency       | ~50-150 ms             | ~150-400 ms            |
| Dependencies           | Apple only             | Apple + Google         |
| Auth method            | p8 key JWT / p12 cert  | Firebase service acct  |
| Max payload            | 4 096 bytes            | 4 096 bytes (iOS)      |
| Silent push support    | Yes (content-available)| Yes                    |
| Collapse key           | apns-collapse-id       | FCM collapse_key       |
| Delivery receipts      | Errors only (410, 400) | Errors + some stats    |
| Token invalidation     | 410 response           | FCM invalid-reg event  |
| Per-request overhead   | TLS + HTTP/2 stream    | TLS + HTTP to FCM      |
| Works without GMS      | Yes                    | No (GMS required)      |

Use APNs direct for iOS. Use FCM for Android. Do not route
iOS traffic through FCM unless your team already manages
FCM credentials and cannot store an Apple p8 key securely.

---

## 2. p8 Auth Key vs p12 Certificate

**p8 key (recommended):**

- One key works for all apps in the Apple Developer account
  (up to 2 keys per team).
- Never expires; revoke and reissue manually if compromised.
- Used to sign short-lived JWTs (1 hour validity).
- Stored as `AuthKey_<KEY_ID>.p8`.
- Cannot be re-downloaded after initial creation.

**p12 certificate (legacy):**

- Per-app, per-environment (one for production, one for
  sandbox). Expires annually.
- Requires renewal, re-export from Keychain, and redeploy.
- Passphrase-protected; harder to rotate in Workers secrets.

**Decision:** use the p8 key. Store it in Cloudflare
Workers secrets, not in wrangler.toml.

```bash
wrangler secret put APNS_AUTH_KEY      # paste PEM content
wrangler secret put APNS_KEY_ID        # e.g. ABC123DEF4
wrangler secret put APNS_TEAM_ID       # 10-char Apple Team ID
```

---

## 3. Cloudflare Worker APNs Push Helper

JWT tokens must be signed with ES256 (ECDSA P-256). The
WebCrypto API available in Workers supports this natively.

```ts
// workers/src/apns.ts

const APNS_HOST = 'https://api.push.apple.com';
const APNS_HOST_DEV = 'https://api.sandbox.push.apple.com';

interface ApnsEnv {
  APNS_AUTH_KEY: string;   // PEM p8 key, one-line base64
  APNS_KEY_ID: string;
  APNS_TEAM_ID: string;
  APNS_BUNDLE_ID: string;
}

// Cache the signed JWT; APNs accepts tokens up to 1 h old.
let cachedJwt: { token: string; issuedAt: number } | null
  = null;

async function getJwt(env: ApnsEnv): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  if (cachedJwt && now - cachedJwt.issuedAt < 3000) {
    return cachedJwt.token;
  }

  const header = btoa(JSON.stringify(
    { alg: 'ES256', kid: env.APNS_KEY_ID }
  )).replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');

  const payload = btoa(JSON.stringify(
    { iss: env.APNS_TEAM_ID, iat: now }
  )).replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');

  const data = `${header}.${payload}`;

  // Import p8 key (strip PEM headers, decode base64)
  const pem = env.APNS_AUTH_KEY
    .replace(/-----[^-]+-----/g, '').replace(/\s/g, '');
  const keyData = Uint8Array.from(atob(pem), c =>
    c.charCodeAt(0));

  const key = await crypto.subtle.importKey(
    'pkcs8', keyData,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false, ['sign']
  );

  const sig = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    key,
    new TextEncoder().encode(data)
  );

  const sigB64 = btoa(String.fromCharCode(
    ...new Uint8Array(sig)))
    .replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');

  const token = `${data}.${sigB64}`;
  cachedJwt = { token, issuedAt: now };
  return token;
}

export async function sendApns(
  deviceToken: string,
  notification: Record<string, unknown>,
  env: ApnsEnv,
  opts?: {
    priority?: 10 | 5;
    collapseId?: string;
    contentAvailable?: boolean;
    sandbox?: boolean;
  }
): Promise<void> {
  const jwt = await getJwt(env);
  const host = opts?.sandbox ? APNS_HOST_DEV : APNS_HOST;

  const aps: Record<string, unknown> = {
    ...notification,
  };
  if (opts?.contentAvailable) {
    aps['content-available'] = 1;
  }

  const body = JSON.stringify({ aps });

  const res = await fetch(
    `${host}/3/device/${deviceToken}`,
    {
      method: 'POST',
      headers: {
        authorization: `bearer ${jwt}`,
        'apns-topic': env.APNS_BUNDLE_ID,
        'apns-priority': String(opts?.priority ?? 10),
        'apns-push-type': opts?.contentAvailable
          ? 'background' : 'alert',
        ...(opts?.collapseId
          ? { 'apns-collapse-id': opts.collapseId }
          : {}),
        'content-type': 'application/json',
      },
      body,
    }
  );

  if (!res.ok) {
    const err = await res.json<{ reason: string }>();
    if (res.status === 410) {
      // Device token no longer valid — remove from DB
      throw new Error(`APNS_UNREGISTERED:${deviceToken}`);
    }
    throw new Error(`APNs error ${res.status}: ${err.reason}`);
  }
}
```

---

## 4. Token Caching and JWT Validity

APNs accepts JWTs issued within the last 60 minutes. Reuse
the same JWT across requests within a Worker instance to
avoid re-importing the key on every call. The cache above
uses a 50-minute window (`< 3000` seconds) to provide a
10-minute safety margin before Apple rejects the token.

Workers are per-isolate, so each isolate maintains its own
`cachedJwt`. Under high traffic, multiple isolates sign
independent JWTs — this is acceptable and expected.

---

## 5. Priority 10 vs 5 and Collapse ID

```
apns-priority: 10  → Deliver immediately (alert, sound)
apns-priority: 5   → Deliver at a power-efficient time
                     (background refresh, badge updates)
```

For social activity alerts (likes, comments, DMs) use
priority 10. For background data prefetch use priority 5.

`apns-collapse-id` replaces an existing notification with
the same ID on the lock screen and Notification Center.
Use this for "3 new likes on your post" to avoid stacking:

```ts
await sendApns(token, {
  alert: { title: 'New activity', body: '5 likes' },
  badge: 5,
}, env, { collapseId: `likes:${postId}` });
```

---

## 6. Background Push and Battery Impact

`content-available: 1` with `apns-priority: 5` triggers a
silent background fetch. iOS throttles these aggressively:

- Apps in the background receive at most a few silent
  pushes per hour.
- iOS may defer or drop them entirely based on battery
  state and usage patterns.
- Do not use background push for time-critical delivery;
  use alert pushes with `apns-priority: 10` instead.
- Each background push wakes the app for ~30 seconds of
  CPU time. Batch data fetches within that window.

---

## Anti-patterns

- Re-signing a JWT for every push request. Key import in
  WebCrypto is expensive; cache the signed token.
- Sending `content-available: 1` with `apns-priority: 10`.
  Apple rejects this combination silently in some versions;
  background pushes must use priority 5.
- Ignoring 410 responses. Continuing to push to an
  unregistered token wastes quota and can trigger Apple's
  rate-limiting on the team's APNs connection.
- Using the sandbox endpoint (`api.sandbox.push.apple.com`)
  in production. Tokens registered via TestFlight target
  sandbox; production app tokens target production.

## Gotchas

- A Workers `fetch` to `api.push.apple.com` goes over
  HTTP/1.1 inside the Worker runtime (Workers uses HTTP/2
  to the origin but the underlying implementation detail
  varies). APNs still accepts HTTP/1.1 on port 443 with
  the same API structure; there is no functional change.
- The APNs JWT must be re-issued if the p8 key is revoked.
  There is no grace period; all in-flight JWTs signed by
  the old key are immediately invalid.
- `apns-collapse-id` is limited to 64 bytes. Use short,
  deterministic identifiers (e.g. `likes:<postId>`).

## Verification

```bash
# Send a test push from the terminal using curl
curl -v --http2                                    \
  -H "authorization: bearer <JWT>"                 \
  -H "apns-topic: app.example project"                      \
  -H "apns-priority: 10"                           \
  -H "apns-push-type: alert"                       \
  -H "content-type: application/json"              \
  -d '{"aps":{"alert":"test","sound":"default"}}'  \
  https://api.push.apple.com/3/device/<device-token>

# Expected: HTTP/2 200 with empty body
```

## Related

- `android-background-work-limits-workmanager.md`
- `mobile-ci-cd-expo-eas-build.md`
- Cloudflare Workers Secrets documentation

## Source URLs (verified 2026-08-17)

- https://developer.apple.com/documentation/usernotifications/establishing-a-token-based-connection-to-apns
- https://developer.apple.com/documentation/usernotifications/sending-notification-requests-to-apns
- https://developer.apple.com/documentation/usernotifications/pushing-background-updates-to-your-app
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developer.apple.com/documentation/usernotifications/setting-the-push-notification-payload
