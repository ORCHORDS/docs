# Email Newsletter Referral Program Tracking — Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want subscribers to invite friends and earn rewards, but your ESP has no
native referral engine. Clicks arrive, signups happen, and you cannot connect
them back to the referrer — so credit is never awarded and the loop stalls.

---

## Context

A referral loop needs four primitives: (1) a unique referral code embedded in
every newsletter, (2) a landing-page Worker that reads the code and sets a
first-party cookie, (3) a signup Worker that reads the cookie and writes the
conversion to D1, and (4) a reward-check cron that queries D1 and triggers
perks. Workers + D1 give you all four without a third-party tool.

---

## D1 Schema

```sql
CREATE TABLE referrals (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  referrer_id TEXT    NOT NULL,
  referee_email TEXT,
  clicked_at  INTEGER NOT NULL,
  converted_at INTEGER,
  rewarded_at INTEGER
);

CREATE INDEX idx_ref_referrer ON referrals(referrer_id);
CREATE INDEX idx_ref_unconverted ON referrals(converted_at) WHERE converted_at IS NULL;
```

---

## Generating Per-Subscriber Referral Codes

Codes must be deterministic so they survive re-sends without duplicating rows.
HMAC-SHA-256 over the subscriber ID with a secret keeps them unforgeable.

```typescript
// src/referral-code.ts
export async function generateReferralCode(
  subscriberId: string,
  secret: string
): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(subscriberId)
  );
  // 8-char base64url prefix — collision risk negligible for <10M subscribers
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
    .slice(0, 8);
}
```

Inject into your template as `https://example.com/join?ref={code}`.

---

## Landing-Page Worker — Record Click, Set Cookie

```typescript
// src/workers/referral-landing.ts
export interface Env {
  DB: D1Database;
  REFERRAL_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const ref = url.searchParams.get('ref');
    if (!ref) return Response.redirect('https://example.com/join', 302);

    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      `INSERT INTO referrals (referrer_id, clicked_at)
       VALUES (?, ?)
       ON CONFLICT DO NOTHING`
    ).bind(ref, now).run();

    const dest = new URL('https://example.com/join');
    const resp = Response.redirect(dest.toString(), 302);
    // HttpOnly, Secure, 30-day cookie
    const headers = new Headers(resp.headers);
    headers.append(
      'Set-Cookie',
      `ref=${encodeURIComponent(ref)}; Max-Age=2592000; Path=/; HttpOnly; Secure; SameSite=Lax`
    );
    return new Response(null, { status: 302, headers });
  }
};
```

---

## Signup Worker — Convert Click to Referral

```typescript
// src/workers/signup.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    const { email } = await request.json<{ email: string }>();
    const cookie = request.headers.get('Cookie') ?? '';
    const ref = cookie.match(/ref=([^;]+)/)?.[1];

    // Always insert the subscriber regardless of referral
    await env.DB.prepare(
      `INSERT INTO subscribers (email, created_at) VALUES (?, ?)`
    ).bind(email, Math.floor(Date.now() / 1000)).run();

    if (ref) {
      await env.DB.prepare(
        `UPDATE referrals
         SET referee_email = ?, converted_at = ?
         WHERE referrer_id = ? AND converted_at IS NULL
         LIMIT 1`
      ).bind(email, Math.floor(Date.now() / 1000), decodeURIComponent(ref)).run();
    }

    return new Response(JSON.stringify({ ok: true }), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
};
```

---

## Reward Cron — Grant Perks After N Referrals

```typescript
// src/workers/reward-cron.ts
const REWARD_THRESHOLD = 3; // referrals needed for a reward

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const eligible = await env.DB.prepare(
      `SELECT referrer_id, COUNT(*) AS cnt
       FROM referrals
       WHERE converted_at IS NOT NULL AND rewarded_at IS NULL
       GROUP BY referrer_id
       HAVING cnt >= ?`
    ).bind(REWARD_THRESHOLD).all<{ referrer_id: string; cnt: number }>();

    for (const row of eligible.results) {
      await grantReward(env, row.referrer_id);
      await env.DB.prepare(
        `UPDATE referrals
         SET rewarded_at = ?
         WHERE referrer_id = ? AND converted_at IS NOT NULL AND rewarded_at IS NULL`
      ).bind(Math.floor(Date.now() / 1000), row.referrer_id).run();
    }
  }
};

async function grantReward(env: Env, referrerId: string): Promise<void> {
  // Call your ESP or internal API to grant a coupon / upgrade
  await fetch('https://internal.example.com/rewards', {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.REWARDS_SECRET}` },
    body: JSON.stringify({ subscriber_id: referrerId })
  });
}
```

---

## Anti-patterns

- **Referral code in URL only, no cookie** — any redirect or UTM stripping
  breaks attribution before the user lands on the signup form.
- **Rewarding on click, not conversion** — trivially gamed with self-clicks;
  always gate rewards on a confirmed email signup or purchase.
- **One row per click** — if a subscriber clicks their own link twice you
  double-count; the `ON CONFLICT DO NOTHING` + `LIMIT 1 UPDATE` pattern above
  prevents this.

---

## Gotchas

- D1's `LIMIT` on `UPDATE` requires SQLite ≥ 3.33; Cloudflare D1 supports it.
- The HMAC code is stable per `(subscriberId, secret)` pair. Rotate the secret
  only in a maintenance window — existing links in inboxes will break.
- `SameSite=Lax` allows the cookie to be sent on top-level GET redirects (the
  landing Worker). `SameSite=Strict` would drop it.

---

## Verification

```bash
# 1. Simulate a referral click
curl -i "https://landing.example.com/join?ref=abc12345"
# Expect: 302, Set-Cookie: ref=abc12345

# 2. Check D1 row
wrangler d1 execute MY_DB --command \
  "SELECT * FROM referrals WHERE referrer_id='abc12345'"

# 3. Simulate signup
curl -X POST https://signup.example.com/register \
  -H "Cookie: ref=abc12345" \
  -H "Content-Type: application/json" \
  -d '{"email":"new@example.com"}'

# 4. Confirm conversion row
wrangler d1 execute MY_DB --command \
  "SELECT * FROM referrals WHERE referrer_id='abc12345'"
```

---

## Related

- `email-newsletter-double-opt-in-workers-d1.md`
- `email-click-tracking-privacy-preserving-workers.md`
- `email-engagement-scoring-segmentation.md`

---

## Sources

- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- Web Crypto HMAC — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
- RFC 6265 — HTTP State Management Mechanism (cookies)
