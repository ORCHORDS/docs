# Bounce Classification and List Hygiene

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Sender reputation degrades without obvious cause. Deliverability
to major ISPs drops week over week. ESP dashboards show bounce
rates above 2 %. Marketing campaigns land in spam for otherwise
engaged subscribers. Feedback loop complaint counts rise after
a list import or a lapsed-subscriber re-send.

## Context

ISPs use bounce rate and spam complaint rate as primary signals
to determine whether a sender is trustworthy. Hard bounces —
permanent delivery failures — must be suppressed on first
occurrence. Soft bounces — transient failures such as a full
mailbox — must be retried with exponential backoff, then
suppressed after repeated failure. Ignoring these signals
causes SMTP reputation damage that can take months to repair.

## SMTP Error Code Classification

SMTP response codes indicate the class of failure:

| Code  | Meaning                          | Classification |
|-------|----------------------------------|----------------|
| 2xx   | Accepted                         | Delivered      |
| 421   | Service temporarily unavailable  | Soft           |
| 450   | Mailbox temporarily unavailable  | Soft           |
| 451   | Local error in processing        | Soft           |
| 452   | Insufficient storage             | Soft           |
| 500   | Syntax error in command          | Hard           |
| 501   | Bad sender or recipient address  | Hard           |
| 550   | Mailbox does not exist           | Hard           |
| 551   | User not local; please forward   | Hard           |
| 552   | Storage limit exceeded (perm)    | Hard           |
| 553   | Mailbox name invalid             | Hard           |
| 554   | Transaction failed / spam block  | Hard           |

Threshold: bounce rate < 2 % per send. Above 5 % risks ISP
blocks. Google and Yahoo enforced 0.3 % spam complaint rate
limits for bulk senders as of February 2024.

## Bounce Handling Workflow

```
Send attempt
     │
     ▼
SMTP response / DSN received
     │
     ├─ 2xx ─────────► Log delivered; update last_sent_at
     │
     ├─ 4xx ─────────► Increment soft_bounce_count
     │                      │
     │                      ├─ count < 3 ──► Retry with
     │                      │                backoff
     │                      └─ count ≥ 3 ──► Suppress
     │
     └─ 5xx ─────────► Suppress immediately
                        Record code, reason, timestamp
```

Parse Delivery Status Notifications (DSN) from bounce inboxes
when using VERP or SES bounce webhooks:

```python
import re

def classify_bounce(dsn_body: str) -> str:
    """Return 'hard', 'soft', or 'unknown'."""
    # RFC 3464 status code format: X.Y.Z
    m = re.search(r'Status:\s*(\d)\.\d+\.\d+', dsn_body)
    if m:
        return 'hard' if int(m.group(1)) == 5 else 'soft'
    c = re.search(r'\b([45]\d{2})\b', dsn_body)
    if c:
        return 'hard' if c.group(1)[0] == '5' else 'soft'
    return 'unknown'
```

## Suppression Lists

Maintain a centralised suppression list across all sending
systems and channels:

```sql
CREATE TABLE email_suppressions (
  email         TEXT PRIMARY KEY,
  reason        TEXT NOT NULL, -- 'hard_bounce'|'complaint'
                               -- |'unsubscribe'|'soft_limit'
  smtp_code     INTEGER,
  suppressed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source        TEXT          -- ESP name or sending system
);
CREATE INDEX ON email_suppressions (suppressed_at);

-- Gate every send attempt
SELECT 1 FROM email_suppressions WHERE email = $1 LIMIT 1;
```

ESPs (Resend, SendGrid, Postmark, SES) maintain their own
suppression lists. Mirror them into your store via webhooks
so that campaign sends from every channel respect the same
suppressions.

## ISP Feedback Loops

Major ISPs offer Feedback Loop (FBL) programmes that deliver
spam complaint reports in Abuse Reporting Format (ARF):

| ISP             | FBL format  | Registration               |
|-----------------|-------------|----------------------------|
| Yahoo / AOL     | ARF         | postmaster.yahooinc.com    |
| Outlook/Hotmail | JMRP/SNDS   | postmaster.live.com        |
| Comcast         | ARF         | postmaster.comcast.net     |
| Gmail           | None (FBL)  | Use Google Postmaster Tools|

Processing FBL complaints: parse the ARF message, extract the
recipient from `Original-Rcpt-To` or `X-Forwarded-To`, insert
into the suppression table with `reason = 'complaint'`, and
never re-add the address to any list.

Acceptable complaint rate: < 0.08 % (Google/Yahoo 2024
bulk sender threshold). Rates above 0.3 % trigger active
blocks at both providers.

## Anti-patterns

- Continuing to send to hard-bounced addresses — each retry
  counts against sender reputation.
- Treating a 554 (blocked by ISP) as a transient soft bounce
  — this is an active spam block; do not retry without
  investigating and remediating the blocklist entry.
- Importing purchased or harvested lists without prior
  email verification — spam trap addresses inflate bounces
  and complaint rates immediately.
- Using "last open date" for list hygiene — Apple MPP fakes
  open events; use click or purchase dates instead.
- Reactivating suppressed addresses without first verifying
  them via ZeroBounce, NeverBounce, or Kickbox.

## Gotchas

- Gmail does not offer an FBL; use Google Postmaster Tools
  (`postmaster.google.com`) to monitor complaint rate and
  domain reputation.
- SES automatically suppresses hard-bounced addresses
  account-wide. Attempting to send to a suppressed address
  via SES returns a `MessageRejected` API error, not an SMTP
  bounce. Check the suppression list before each send in
  high-volume flows.
- Some 452 (storage full) soft bounces resolve within hours;
  others indicate a permanently inactive mailbox. Cap retries
  at three attempts over 72 hours before moving to
  suppression.
- Spam traps — pristine (never registered), recycled (old
  inactive addresses), and typo traps — do not bounce; they
  simply accept mail and report the sender. List hygiene tools
  can identify recycled traps but not pristine ones.

## Verification

```sh
# Check SES account-level suppression for an address
aws sesv2 get-suppressed-destination \
  --email-address user@example.com

# View recent SES sending statistics
aws ses get-send-statistics \
  --query 'SendDataPoints[-5:]'

# Monitor via CloudWatch alarms
# Metric: AWS/SES Reputation.BounceRate  threshold: 0.02
# Metric: AWS/SES Reputation.ComplaintRate  threshold: 0.001
```

Review bounce and complaint metrics daily. Set alerts at
50 % of threshold to allow remediation time before ISP
blocks occur.

## Related

- email/suppression-list-management.md
- email/verp-bounce-addressing.md
- email/ses-bounce-complaint-webhooks.md
- email/ip-warming-strategy.md
- email/email-list-hygiene.md

## Source URLs (verified 2026-08-17)

- https://www.rfc-editor.org/rfc/rfc5321
- https://www.rfc-editor.org/rfc/rfc3464
- https://postmaster.yahooinc.com/
- https://postmaster.live.com/
- https://docs.aws.amazon.com/ses/latest/dg/monitor-sending-activity.html
