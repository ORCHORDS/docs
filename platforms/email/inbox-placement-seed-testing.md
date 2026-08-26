# Inbox placement seed-list testing

**Issue:** Deliverability metrics (open/click rates) only show what recipients *did* with email that arrived — they are blind to mail that never reached the inbox. You ship a campaign, the ESP reports "delivered: 99.8%", but replies drop 40% because Gmail quietly routed everything to Promotions or Spam.
**Date:** 2026-08-13
**Author:** ORCHORDS
**Status:** documented

Inbox placement testing (seed-list testing) sends a controlled test message to a panel of monitored mailboxes across Gmail, Outlook, Yahoo, Apple, and regional providers, then reports where each message landed: Primary inbox, Promotions/Updates tab, Spam, Junk, or not received at all. It is the only way to measure true inbox placement before a campaign goes to real recipients.

## Symptom

- ESP reports high delivery (250 OK from the receiving MTA) but engagement collapses anyway.
- Open rates vary wildly by recipient domain — Gmail fine, Outlook dead, or vice versa.
- A/B winner in your ESP differs from the A/B winner in actual replies/revenue.
- Complaints arrive ("I never got the email") from domains your bounce webhook shows as delivered.
- Deliverability "feels" broken but every dashboard is green.

The cause is almost always tab placement or foldering after successful SMTP delivery. "Delivered" means the MTA accepted the message; it says nothing about where the mailbox provider filed it.

## Gotchas

- **Seed lists are synthetic, not behavioral.** Seed addresses are not real users; they have no engagement history, no opens, no replies. A seed test measures *pure filtering* and will understate placement for senders with strong engagement signals. Treat a seed result as a lower bound, not a forecast.
- **Seed tests cannot measure tab placement accurately at scale.** Gmail's Promotions/Updates/Primary routing depends heavily on recipient engagement, which seed accounts lack. A seed test landing in Promotions does not mean your engaged users see it there.
- **Seed panels are small and get burn-in.** Most providers run 50–500 seed addresses per mailbox provider. If you test daily against the same panel, the panel's reputation shifts and results drift. Rotate test cadence and vary the sending domain/content.
- **One-shot tests are noise.** Placement fluctuates day-to-day based on volume, content, and the provider's own filtering updates. Run placement tests on a fixed cadence (e.g., every campaign, or weekly for high-volume senders) and track the trend, not a single data point.
- **Placement differs by recipient geography and provider version.** Outlook.com, Outlook desktop (Exchange), and Outlook for Mac can filter the same message differently. Confirm which Outlook variant your panel represents before generalizing.
- **Seed tests do not catch IP/domain reputation issues that build over time.** A seed test is a snapshot; pair it with Google Postmaster Tools and Microsoft SNDS for ongoing reputation signal.
- **Free tools (mail-tester, GlockApps free tier) have tiny panels and high variance.** Useful for content/spam-score sanity checks, not for placement decisions on production volume.

## Practical implementation

**1. Pick a tool matched to your volume and providers:**
- **GlockApps** — broadest provider coverage, good for recurring production tests.
- **MailReach** — strong on inbox-vs-spam split, good deliverability scoring.
- **Mailgun Optimize / Validity Everest / 250ok** — enterprise-grade panels with provider breakdowns.
- **Mailtrap Email Testing** — good for pre-send content/spam-score checks in CI.

**2. Test cadence:**
- Test every major campaign blast before send (content + IP reputation snapshot).
- Run a baseline weekly test during IP/domain warming.
- Test immediately after any DNS/authentication change (SPF/DKIM/DMARC/MTA-STS).

**3. What to capture per test (store as a time series):**
```
{
  "timestamp": "2026-08-13T14:00:00Z",
  "campaign_id": "aug-newsletter-3",
  "sending_domain": "mail.example.com",
  "sending_ip": "203.0.113.10",
  "results": {
    "gmail":      {"inbox": 18, "promotions": 7, "spam": 0, "missing": 0},
    "outlook":    {"inbox": 12, "junk": 13, "missing": 0},
    "yahoo":      {"inbox": 22, "spam": 3, "missing": 0},
    "apple_icloud":{"inbox": 20, "junk": 5, "missing": 0}
  },
  "content_hash": "sha256-of-rendered-html",
  "subject": "August update"
}
```

**4. Interpret the trend, not the snapshot:**
- A single 70% inbox rate is not necessarily bad if last week was 95% — investigate the delta.
- Sustained drop below ~85% inbox across providers is an actionable signal: check authentication alignment, recent volume spikes, complaint rate, and content triggers.

**5. Pair with direct provider intelligence:**
- Google Postmaster Tools — domain/IP reputation, spam rate, delivery errors, authentication pass rate.
- Microsoft SNDS — outbound IP reputation and filtering status on Outlook/Hotmail/Live.
- Yahoo Complaint Feedback Loop (CFL) — complaint signals.

Seed testing tells you *that* something is wrong; Postmaster/SNDS tells you *why*.

**6. Do not optimize seed scores in isolation.** High inbox placement with collapsing engagement is worse than moderate placement with strong replies. The business metric is revenue/replies/retention, not the seed inbox percentage.

## Verification
- Confirm the test panel covers every mailbox provider your real recipients actually use (check recipient-domain analytics — don't assume Gmail+Outlook is enough).
- Re-run the same test message 3x across 48h to confirm variance; a single run is not signal.
- Cross-check a "spam" seed result against Google Postmaster Tools spam-rate graph for the same window.
- After any deliverability fix (auth change, content edit, volume throttle), re-run the seed test and store the before/after result.

## Sources
- [Inbox Placement Testing Guide 2026 — MailReach](https://www.mailreach.co/blog/inbox-placement-testing)
- [Seed List Testing for Email Deliverability — MailNeo](https://www.mailneo.co/blog/seed-list-deliverability-testing)
- [Inbox Placement Explained (2026) — Mailtrap](https://mailtrap.io/blog/inbox-placement/)
- [10 Best Email Deliverability Tools Compared (2026) — Overloop](https://overloop.com/blog/email-deliverability-tools)
