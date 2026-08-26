# platform-trust-score-cloudflare-signals

**Issue:** Anonymous user trust scores are mis-calibrated for mobile
  clients — WKWebView Bot Scores are consistently lower than desktop
  for genuine users; JA4 fingerprints rotate per iOS app session,
  invalidating score continuity; KYC-verified scores decay below the
  action threshold after 30 days of inactivity
**Date:** 2026-08-22
**Author:** example.com
**Status:** open

## Symptom

1. 23% of iOS users have a trust score below 30 on first session,
   triggering a visible Turnstile challenge on every action. The
   same users on desktop score above 60 with no challenge.
2. JA4 TLS fingerprints for WKWebView rotate approximately every
   15 minutes. The scoring Worker treats each rotation as a new,
   untrusted identity, resetting the score to the unverified
   baseline of 50.
3. Trust scores for KYC-verified accounts decay to below the
   posting threshold (score < 40) after 30 days of inactivity,
   triggering re-challenges even though age verification is valid.

## Context

example project is anonymous. Users have no persistent credentials beyond
a device-bound session token stored in `localStorage`. Trust scoring
is the primary mechanism for distinguishing genuine humans from bots
and for progressively unlocking platform features (posting, DMs,
reactions) without requiring account registration.

## Cloudflare Signals Available in Workers

```
┌──────────────────────────────┬───────────────────────────────┐
│ Signal                       │ Source / Notes                │
├──────────────────────────────┼───────────────────────────────┤
│ cf.botManagement.score       │ CF Bot Management (0–99;      │
│                              │ lower = more likely bot)      │
├──────────────────────────────┼───────────────────────────────┤
│ cf.botManagement.ja4         │ JA4 TLS fingerprint string    │
├──────────────────────────────┼───────────────────────────────┤
│ cf.asn                       │ Autonomous System Number      │
├──────────────────────────────┼───────────────────────────────┤
│ cf.country                   │ ISO 3166-1 alpha-2            │
├──────────────────────────────┼───────────────────────────────┤
│ cf.tlsVersion                │ 'TLSv1.2' | 'TLSv1.3' | etc  │
├──────────────────────────────┼───────────────────────────────┤
│ Turnstile verify score       │ 0.0–1.0 from Turnstile API    │
│                              │ (separate HTTP call)          │
└──────────────────────────────┴───────────────────────────────┘
```

Access them in a Worker via `request.cf`:

```ts
const cf      = request.cf as IncomingRequestCfProperties;
const botMgmt = cf.botManagement;

const signals = {
  botScore:       botMgmt?.score ?? 50,
  ja4:            botMgmt?.ja4 ?? '',
  asn:            cf.asn ?? 0,
  country:        cf.country ?? 'XX',
  tls:            cf.tlsVersion ?? 'TLSv1.2',
  turnstileScore: await verifyTurnstile(token, env),
};
```

## Trust Score Formula

The score is a weighted sum clamped to [0, 100]:

```ts
function computeScore(
  s: Signals,
  isVerified: boolean,
  isMobileWebView: boolean
): number {
  // Bot score 0 (bot)–99 (human). Rescale to 0–40 contribution.
  // Apply +25 adjustment for mobile WebView (see section below).
  const adjustedBot   = isMobileWebView
    ? Math.min(99, s.botScore + 25)
    : s.botScore;
  const botContrib    = (adjustedBot / 99) * 40;

  // Turnstile: 0.0 (bot)–1.0 (human). Contribution 0–30.
  const tsContrib     = s.turnstileScore * 30;

  // Datacenter / VPN ASN penalty
  const asnPenalty    = DATACENTER_ASNS.has(s.asn) ? -20 : 0;

  // KYC age-verified bonus
  const kycBonus      = isVerified ? 15 : 0;

  // TLS version signal
  const tlsPenalty    = s.tls === 'TLSv1.3' ? 0 : -5;

  const raw = botContrib + tsContrib + asnPenalty
            + kycBonus + tlsPenalty;

  return Math.max(0, Math.min(100, Math.round(raw)));
}
```

## Mobile vs Desktop Baseline Differences

```
┌───────────────────────┬──────────────────┬──────────────────────┐
│ Factor                │ Desktop Chrome   │ iOS WKWebView        │
├───────────────────────┼──────────────────┼──────────────────────┤
│ CF Bot Score baseline │ 80–99 (genuine   │ 30–70 — WebView      │
│                       │ users)           │ lacks the JS signals │
│                       │                  │ CF uses for scoring  │
├───────────────────────┼──────────────────┼──────────────────────┤
│ JA4 stability         │ Stable per       │ Rotates per          │
│                       │ browser version  │ WKWebView session    │
│                       │                  │ (~15-min intervals)  │
├───────────────────────┼──────────────────┼──────────────────────┤
│ Turnstile completion  │ Usually invisible│ Often visible        │
│ mode                  │ (auto-solved)    │ challenge — missing  │
│                       │                  │ JS environment cues  │
├───────────────────────┼──────────────────┼──────────────────────┤
│ ASN classification    │ Residential ISP  │ Mobile carrier; not  │
│                       │                  │ a datacenter ASN;    │
│                       │                  │ no penalty applies   │
└───────────────────────┴──────────────────┴──────────────────────┘
```

The +25 Bot Score adjustment for mobile WebView compensates for
Cloudflare's inability to collect JS telemetry inside WKWebView.
Re-calibrate quarterly using the `mobile_client` column in D1.

Use JA4 as a *consistency signal* only, not as a primary identity
key. If the incoming JA4 matches the stored `last_ja4` for the
session token, award +3 points. If it rotates, apply no penalty
(normal on iOS) but do not carry forward the prior session's score.

## D1 Storage Schema

```sql
CREATE TABLE trust_scores (
  user_id        TEXT PRIMARY KEY,
  score          INTEGER NOT NULL DEFAULT 50,
  last_ja4       TEXT,
  last_asn       INTEGER,
  last_country   TEXT,
  mobile_client  INTEGER NOT NULL DEFAULT 0,  -- 1 = mobile/WebView
  computed_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  decay_floor    INTEGER NOT NULL DEFAULT 10
);

CREATE TABLE trust_score_events (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL,
  delta      INTEGER NOT NULL,   -- positive or negative adjustment
  reason     TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_tse_user
    ON trust_score_events(user_id, created_at);
```

## Score Decay Over Time

Inactive accounts decay toward `decay_floor`. KYC-verified accounts
use a floor of 40 (KYC bonus is permanent; only activity-derived
points decay):

```
┌──────────────────────┬──────────────────────────────────────────┐
│ Inactivity period    │ Decay applied                            │
├──────────────────────┼──────────────────────────────────────────┤
│ 7 days               │ -5 pts (unverified only)                 │
├──────────────────────┼──────────────────────────────────────────┤
│ 14 days              │ -10 pts (unverified); -3 pts (verified)  │
├──────────────────────┼──────────────────────────────────────────┤
│ 30 days              │ -20 pts (unverified); -5 pts (verified)  │
├──────────────────────┼──────────────────────────────────────────┤
│ 90 days              │ Reset to decay_floor (both)              │
└──────────────────────┴──────────────────────────────────────────┘
```

Cron Trigger (daily at 02:00 UTC) applies decay:

```ts
// workers/trust-decay-cron.ts
export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    await env.DB.prepare(
      `UPDATE trust_scores
          SET score = MAX(decay_floor,
                score - CASE
                  WHEN unixepoch()-computed_at > 7776000 THEN 100
                  WHEN unixepoch()-computed_at > 2592000 THEN 20
                  WHEN unixepoch()-computed_at > 1209600 THEN 10
                  WHEN unixepoch()-computed_at > 604800  THEN 5
                  ELSE 0
                END)
        WHERE computed_at < unixepoch() - 604800`
    ).run();
  },
};
```

## Anti-patterns

- **Using JA4 as the primary user identity key for anonymous
  accounts.** JA4 rotates on iOS WKWebView every session. Use a
  device-bound session token in `localStorage` as the primary key;
  treat JA4 as a consistency check only.
- **Applying datacenter ASN penalties to mobile carrier ASNs.**
  Some mobile carriers (T-Mobile, Vodafone) share ASN block
  listings with datacenters. Maintain a separate allow-list of
  known carrier ASNs to prevent false penalties.
- **Letting scores drop below decay_floor for KYC-verified
  accounts.** Age verification is the strongest trust signal on
  the platform. Set `decay_floor = 40` for verified users and
  enforce it in the cron query with a `WHERE` on the
  `verification_status` join.
- **Re-running Turnstile on every request.** Turnstile is an
  action-gate, not a per-request signal. Cache the result in KV
  for 10 minutes keyed by session token.

## Gotchas

- `cf.botManagement` is only available on plans that include Bot
  Management. On the Free plan, `cf.botManagement` is `undefined`.
  Gate scoring logic on
  `typeof cf.botManagement !== 'undefined'`.
- Cloudflare Bot Management scores Playwright/Puppeteer test
  sessions at 0–20 even with stealth plugins. Mock `request.cf`
  in unit tests; do not rely on real CF signals in CI.
- The `cf` object in Workers is read-only. You cannot inject fake
  Bot Score values via `wrangler dev` request headers without a
  custom middleware shim in development mode.

## Verification

```
# Compute score for a test session, confirm stored in D1
curl -X POST https://example project.app/api/session/trust \
  -H 'X-Session-Token: sess_test_001'
# → { "score": 72, "actions_unlocked": ["post","react"] }

wrangler d1 execute example project-db --command \
  "SELECT score, mobile_client
     FROM trust_scores
    WHERE user_id = 'sess_test_001'"
# → 72 | 0

# Simulate inactivity, run decay cron, confirm score reduced
wrangler d1 execute example project-db --command \
  "UPDATE trust_scores
      SET computed_at = unixepoch() - 700000
    WHERE user_id = 'sess_test_001'"

wrangler dispatch-scheduled-event trust-decay-cron

wrangler d1 execute example project-db --command \
  "SELECT score FROM trust_scores
    WHERE user_id = 'sess_test_001'"
# → value lower than 72, ≥ decay_floor
```

## Related

- `documentation/docs/policies/issues/age-verification-cloudflare-workers-kyc.md`
- `documentation/docs/policies/issues/anonymous-content-reporting-worker-pipeline.md`
- `documentation/docs/policies/issues/cookie-samesite-lax-oauth-redirect.md`
- `documentation/docs/policies/issues/content-moderation-appeals-workflow.md`

## Source URLs

- https://developers.cloudflare.com/bots/concepts/bot-score/
- https://developers.cloudflare.com/bots/reference/ja4-signals/
- https://developers.cloudflare.com/turnstile/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
