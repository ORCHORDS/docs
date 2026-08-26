# Email Forward-to-Friend Viral Tracking — D1 + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to measure organic email sharing: when a subscriber forwards your newsletter to a friend, you want to know (a) that it happened, (b) who forwarded it, and (c) whether the friend clicked through and converted. Native email forwarding is opaque — the MUA copies the message, strips tracking pixels, and you lose attribution entirely. A "Forward to a Friend" link in the email body solves this with a referral landing page served by a Worker.

## Context

The pattern replaces the user's native forward with a tracked share: the original message contains a personalised link like `https://share.example.com/f/{token}` that opens a browser landing page. The recipient can enter a friend's email, or the link itself can be shared on other channels. The Worker mints a child token tied to the referrer, stores the relationship in D1, and sends the forwarded copy via MailChannels. This gives you a full referral tree: who shared, who received, what they did.

This is distinct from referral programs (which require sign-up) — forward-to-friend is lightweight, frictionless, and works for anonymous recipients.

---

## 1. D1 schema

```sql
CREATE TABLE forward_shares (
  id          TEXT PRIMARY KEY,          -- nanoid, the share token
  campaign_id TEXT NOT NULL,
  referrer_id TEXT NOT NULL,             -- subscriber who forwarded
  referrer_email TEXT NOT NULL,
  recipient_email TEXT,                  -- filled when friend email is known
  child_token TEXT,                      -- token embedded in the forwarded copy
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  opened_at   TEXT,
  clicked_at  TEXT,
  converted_at TEXT,
  source      TEXT NOT NULL DEFAULT 'ftf' -- 'ftf' | 'social'
);

CREATE INDEX idx_forward_shares_referrer ON forward_shares(referrer_id);
CREATE INDEX idx_forward_shares_campaign ON forward_shares(campaign_id);
CREATE INDEX idx_forward_shares_child    ON forward_shares(child_token);
```

## 2. Generate the share token link at send time

```typescript
import { nanoid } from "nanoid";

async function buildShareLink(
  db: D1Database,
  campaignId: string,
  subscriberId: string,
  subscriberEmail: string,
  baseUrl: string
): Promise<string> {
  const token = nanoid(16);

  await db
    .prepare(
      `INSERT INTO forward_shares
       (id, campaign_id, referrer_id, referrer_email, created_at)
       VALUES (?, ?, ?, ?, datetime('now'))`
    )
    .bind(token, campaignId, subscriberId, subscriberEmail)
    .run();

  return `${baseUrl}/f/${token}`;
}

// Embed in template:
// <a >Forward to a friend →</a>
```

## 3. Landing page Worker — collect friend's email

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const token = url.pathname.split("/f/")[1];
    if (!token) return new Response("Not found", { status: 404 });

    const share = await env.DB.prepare(
      "SELECT * FROM forward_shares WHERE id = ?"
    ).bind(token).first<ForwardShare>();

    if (!share) return new Response("Invalid share link", { status: 404 });

    if (req.method === "POST") {
      const form = await req.formData();
      const friendEmail = form.get("email")?.toString().trim();
      if (!friendEmail) return new Response("Email required", { status: 400 });

      // Mint a child token for the forwarded copy
      const childToken = nanoid(16);
      await env.DB.prepare(
        `UPDATE forward_shares
         SET recipient_email = ?, child_token = ?
         WHERE id = ?`
      ).bind(friendEmail, childToken, token).run();

      await sendForwardedCopy(env, share, friendEmail, childToken);
      return new Response(shareConfirmationHtml(), {
        headers: { "Content-Type": "text/html" },
      });
    }

    return new Response(shareFormHtml(share.campaign_id), {
      headers: { "Content-Type": "text/html" },
    });
  },
};
```

## 4. Send the forwarded copy via MailChannels

```typescript
async function sendForwardedCopy(
  env: Env,
  share: ForwardShare,
  friendEmail: string,
  childToken: string
): Promise<void> {
  // Fetch original rendered HTML from R2
  const obj = await env.EMAIL_ASSETS.get(`campaigns/${share.campaign_id}/rendered.html`);
  if (!obj) throw new Error("Campaign render not found");

  let html = await obj.text();

  // Swap all tracking pixels and share links to use child token context
  html = html.replace(/\/f\/[A-Za-z0-9_-]{16}/g, `/f/${childToken}`);

  // Inject forwarded-by attribution
  html = html.replace(
    "</body>",
    `<p style="font-size:11px;color:#888">Forwarded by ${share.referrer_email}</p></body>`
  );

  await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: friendEmail }] }],
      from: { email: env.FROM_EMAIL, name: env.FROM_NAME },
      subject: `${share.referrer_email} thought you'd enjoy this`,
      content: [{ type: "text/html", value: html }],
    }),
  });
}
```

## 5. Track friend engagement via child token

When the forwarded copy's tracking pixel or click link fires, look up by `child_token`:

```typescript
async function recordFriendEngagement(
  db: D1Database,
  childToken: string,
  event: "opened" | "clicked" | "converted"
): Promise<void> {
  const col = `${event}_at`;
  await db
    .prepare(
      `UPDATE forward_shares SET ${col} = datetime('now')
       WHERE child_token = ? AND ${col} IS NULL`
    )
    .bind(childToken)
    .run();
}
```

## 6. Referral attribution query

```typescript
async function getCampaignShareStats(
  db: D1Database,
  campaignId: string
): Promise<object> {
  return db.prepare(`
    SELECT
      COUNT(*)                                     AS total_shares,
      COUNT(recipient_email)                       AS delivered,
      COUNT(opened_at)                             AS friends_opened,
      COUNT(clicked_at)                            AS friends_clicked,
      COUNT(converted_at)                          AS friends_converted,
      COUNT(DISTINCT referrer_id)                  AS unique_forwarders
    FROM forward_shares
    WHERE campaign_id = ?
  `).bind(campaignId).first();
}
```

---

## Anti-patterns

- **Relying on pixel-based native-forward detection** — forwarded pixels fire on the forwarder's open, then again for the friend; you cannot tell them apart or attribute conversions.
- **Using the referrer's original token in the forwarded copy** — engagement by the friend inflates the referrer's own stats.
- **Sending the forwarded copy without rate-limiting** — a single forward link can be posted publicly. Cap forwarded sends per token (e.g. max 5) and per referrer per day.
- **Exposing referrer_email in the child token lookup** — the friend's tracking endpoint should never reveal who forwarded; return only campaign context.

## Gotchas

- MailChannels blocks sending to the same domain if SPF/DKIM is mis-configured for the forwarded-from identity. Always use your verified sending domain, not the referrer's.
- Unsubscribe links in the forwarded copy must point to an unsubscribe flow for `friendEmail`, not the referrer's subscriber ID — or omit them and rely on the List-Unsubscribe header pointing to a landing page.
- GDPR: you are emailing `friendEmail` without direct consent. Many operators treat a single forwarded send as legitimate interest under the "personal recommendation" framing, but you must not add the friend to your main marketing list without an explicit opt-in.
- `nanoid` is ESM-only from v4; import via `npm:nanoid` in Workers or use `crypto.randomUUID()` and strip hyphens for a shorter token.

## Verification

1. Forward a test campaign to yourself; confirm a row appears in `forward_shares` with `child_token` populated.
2. Open the forwarded message's tracking pixel URL; confirm `opened_at` is set on the share row.
3. Check `total_shares` vs `delivered` — a gap means form submissions are failing before the MailChannels call.
4. Confirm the rate-limit guard prevents a share link from sending more than N forwarded copies.

## Related

- `email-newsletter-referral-tracking-d1-workers.md`
- `email-click-tracking.md`
- `email-open-tracking.md`
- `email-transactional-idempotency-workers-d1.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://mailchannels.zendesk.com/hc/en-us/articles/4565898358413
- https://developers.cloudflare.com/r2/
- https://nanoid.ai/
