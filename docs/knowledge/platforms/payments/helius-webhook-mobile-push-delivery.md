# helius-webhook-mobile-push-delivery

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Solana payment transactions confirm on-chain while users are
offline or backgrounded. No notification arrives until they
re-open the app manually. The Helius webhook fires within
seconds of confirmation but nothing bridges it to devices
without a live WebSocket connection.

## Context

example project processes Solana payments via Helius RPC. When a
monitored wallet receives a transfer the event must reach
mobile users who are offline at confirmation time. Delivery
chain: on-chain confirm → Helius POST → Cloudflare Worker
→ Web Push (APNs / FCM / browser push service) → notification.
The Worker must return 200 within 1 second and fan out
asynchronously via `waitUntil`.

## Helius authHeader verification

Helius authenticates deliveries with a static `authHeader`
you supply at webhook creation time. It is echoed verbatim in
the `Authorization` header — it is not HMAC-signed.

```typescript
// Store via: wrangler secret put HELIUS_AUTH_SECRET
export default {
  async fetch(req: Request, env: Env,
              ctx: ExecutionContext): Promise<Response> {
    const auth = req.headers.get('Authorization') ?? '';
    if (auth !== env.HELIUS_AUTH_SECRET)
      return new Response('Unauthorized', { status: 403 });

    ctx.waitUntil(handlePayload(req.clone(), env));
    return new Response('ok', { status: 200 });
  },
};
```

Helius retries **3 times at 1-second intervals** on 5xx or
timeout; after 3 failures the event is permanently lost.
A 403 skips retries entirely. Enhanced webhooks deliver only
confirmed (successful) transactions; raw webhooks include
both. Helius auto-disables a webhook at ≥ 95% failure rate
over 7 days (paid) or 24 hours (free) — no automatic
re-enable and no default alert.

## D1 deduplication on transaction signature

`signature` in the enhanced payload is the globally unique
Solana transaction signature. Use it as the idempotency key.

```typescript
// Schema (one-time): CREATE TABLE processed_txns (
//   sig TEXT PRIMARY KEY, received INTEGER NOT NULL);

async function handlePayload(req: Request, env: Env) {
  const events = (await req.json()) as HeliusEnhancedEvent[];
  for (const evt of events) {
    const sig = evt.signature;
    if (!sig) continue;
    // INSERT OR IGNORE is atomic — safe under concurrent
    // retries of the same event
    const { meta } = await env.DB.prepare(
      `INSERT OR IGNORE INTO processed_txns
       (sig, received) VALUES (?, ?)`
    ).bind(sig, Date.now()).run();
    if (meta.changes === 0) continue; // duplicate; skip
    await fanOutPush(evt, env);
  }
}
```

Prune rows older than 7 days in a Cron Trigger:
`DELETE FROM processed_txns WHERE received < ?` with
`Date.now() - 7 * 86_400_000`.

## KV fanout to Web Push subscriptions

Store each `PushSubscription` JSON in KV under a key that
encodes the monitored address:
`push:sub:<wallet-address>:<endpoint-hash>`.

```typescript
import webpush from '@mmmike/web-push'; // edge-compatible

async function fanOutPush(evt: HeliusEnhancedEvent, env: Env){
  const address = evt.accountData?.[0]?.account ?? '';
  webpush.setVapidDetails('mailto:push@example.com',
    env.VAPID_PUBLIC_KEY, env.VAPID_PRIVATE_KEY);

  const { keys } = await env.PUSH_KV
    .list({ prefix: `push:sub:${address}:` });

  await Promise.allSettled(keys.map(async ({ name }) => {
    const raw = await env.PUSH_KV.get(name);
    if (!raw) return;
    try {
      await webpush.sendNotification(JSON.parse(raw),
        JSON.stringify({ title: 'Payment received',
          body: evt.description, data: { sig: evt.signature,
          address } }));
    } catch (e: any) {
      if (e.statusCode === 404 || e.statusCode === 410 ||
          e.statusCode === 401)            // dead or wrong key
        await env.PUSH_KV.delete(name);
      console.error('push failed', e.statusCode, name);
    }
  }));
}
```

## VAPID key rotation

Each `PushSubscription` is bound to the public key active at
subscribe time. Rotating keys requires a drain window.

1. Generate a new key pair:
   `npx web-push generate-vapid-keys`
2. Start serving the new public key to browsers (new
   subscriptions bind to it).
3. Deploy new keys as Worker secrets:
   `wrangler secret put VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY`
4. Old subscriptions return 401 when sent with the new
   private key — treat 401 the same as 410 (delete KV entry,
   let client re-subscribe on next open).
5. After 2–4 weeks the old cohort fully drains; confirm via
   401 count dropping to zero before retiring old secrets.

Never rotate both keys simultaneously across all clients —
existing subscriptions will silently stop receiving pushes.

## iOS 16.4+ and mobile push requirements

Web Push on iOS only works for home-screen PWAs. Regular
browser tabs and in-app WebViews (Instagram, TikTok, X)
do not receive push on iOS regardless of iOS version.

| Platform          | Min version | Requirement             |
|-------------------|-------------|-------------------------|
| iOS Safari        | 16.4        | Add to Home Screen PWA  |
| iOS Chrome / Edge | 16.4        | Same WKWebView; same    |
| Android Chrome    | modern      | No install required     |

`manifest.json` must set `"display": "standalone"` (or
`"fullscreen"`). A value of `"browser"` silently disables
push on iOS. Permission denied by the user cannot be
re-prompted — they must delete and re-add the PWA.

**EU caveat:** Apple removed standalone PWA support in the
EU under the Digital Markets Act; EU iOS users cannot
receive Web Push until Apple restores the feature.

Latency chain (device awake, good network):
`Solana confirm (~400 ms) → Helius POST → Worker auth +
D1 write (< 100 ms) → KV fanout + push dispatch
(50–400 ms) → push service delivery → notification`
Typical end-to-end: **1–3 seconds**. Offline devices are
queued by APNs / FCM; only the most recent message per topic
survives while the device is unreachable.

## Anti-patterns

- Processing D1 and KV work in the synchronous response
  path — Worker times out, Helius retries, duplicates pile up.
- Using `INSERT ... WHERE NOT EXISTS` without `OR IGNORE`
  or a transaction — concurrent retries can both pass the
  guard.
- Putting `HELIUS_AUTH_SECRET` or VAPID private key in
  `wrangler.toml [vars]` — leaks to source control.
- Calling `pushManager.subscribe()` in an iOS Safari tab —
  the endpoint always 404s; subscribe only after the PWA is
  launched from the home screen.
- Rotating VAPID keys without a drain window — all active
  subscriptions stop receiving notifications immediately.

## Gotchas

- `authHeader` is a bearer token, not HMAC. A leaked value
  requires updating the Helius webhook AND the Worker secret
  atomically.
- `Promise.allSettled` never throws — log failure counts
  explicitly; a fully-failed fanout still "succeeds."
- KV `list()` is eventually consistent; a subscription
  written milliseconds before may not appear. For critical
  fanouts, use a D1 table instead (stronger read-after-write).
- Helius webhook auto-disable is silent; add a monitoring
  job that polls the webhook status endpoint daily.
- iOS 16.5 improved push reliability over 16.4; reference
  16.5+ in user-facing install guidance.

## Verification

- POST a payload with a wrong `Authorization` value; confirm
  403 and zero D1 rows written.
- Send the same valid payload twice; confirm the second
  skips `fanOutPush` via the `OR IGNORE` no-op.
- Subscribe a test Android Chrome session, trigger a devnet
  payment, confirm notification within 3 s.
- Install as iOS home-screen PWA (16.5+), background the app,
  trigger a devnet transfer, confirm lock-screen notification.
- Manually delete a KV entry; trigger a push to it; confirm
  the 410 handler cleans up without throwing.
- Return 500 three times deliberately; confirm the Helius
  dashboard shows exactly 3 retry attempts at 1-second spacing.

## Related

- `payments/nowpayments-webhook-hmac-sha512.md`
- `payments/stripe-webhook-idempotency.md`
- `payments/solana-wallet-adapter-mobile-browser.md`
- `cloudflare/kv-best-practices.md`
- `mobile/pwa-web-push-notifications.md`

## Source URLs (verified 2026-08-17)

- https://www.helius.dev/docs/api-reference/webhooks/create-webhook
- https://www.helius.dev/docs/webhooks/faqs
- https://developers.cloudflare.com/agents/guides/push-notifications/
- https://documentation.onesignal.com/docs/en/web-push-for-ios
- https://www.magicbell.com/blog/ios-now-supports-web-push-notifications-and-why-you-should-care
- https://webscraft.org/blog/pwa-pushspovischennya-na-ios-u-2026-scho-realno-pratsyuye
- https://www.rfc-editor.org/rfc/rfc9749.pdf
- https://github.com/draphy/pushforge
