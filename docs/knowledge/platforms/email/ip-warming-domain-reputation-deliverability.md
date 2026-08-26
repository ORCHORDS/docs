# IP Warming and Domain Reputation — Email Deliverability Foundations

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

You migrated to a new email service provider or added a new sending IP,
and your email deliverability dropped dramatically — emails land in spam
or are silently dropped. Your open rates fell from 25% to 5%. Mailbox
providers (Gmail, Outlook, Yahoo) are throttling or blocking your sends
because the new IP has no sending history. You are sending 100,000
emails on day one from a cold IP and getting bulk blocked.

## Context

IP warming is the process of gradually increasing email volume from a
new or dormant IP address to build sender reputation with mailbox
providers. Since February 2024, Gmail and Yahoo require bulk senders
(>5,000 emails/day) to meet mandatory authentication (SPF, DKIM, DMARC),
one-click unsubscribe, and spam complaint rate thresholds — warming is
no longer optional best practice but a compliance requirement. In 2026,
sender reputation is determined by a combination of IP reputation,
domain reputation, engagement metrics, and authentication compliance.
Most warming plans run 4-8 weeks, starting with the most engaged
subscribers and scaling up gradually.

## Reputation components

```
IP reputation:
  → History of emails sent from this IP address
  → Built over weeks/months of consistent sending
  → Damaged by spam complaints, bounces, spam traps
  → Shared IPs inherit reputation from all senders

Domain reputation:
  → History of emails sent from your domain (d= in DKIM)
  → More important than IP reputation in 2026
  → Follows you across IP and ESP changes
  → Built through engagement (opens, clicks, replies)

Content reputation:
  → Patterns in email content (spammy phrases, link quality)
  → HTML structure and image-to-text ratio
  → URL reputation of links in email body

Engagement signals:
  → Open rate, click rate, reply rate
  → Spam complaints (must stay below 0.1%)
  → Unsubscribe rate
  → "Not spam" rescues from spam folder
```

## IP warming schedule

```
Week 1: Seed phase (most engaged subscribers only)
  Day 1:     50 emails
  Day 2:    100
  Day 3:    250
  Day 4:    500
  Day 5:  1,000

Week 2: Growth phase
  Day 8:   2,500
  Day 9:   5,000
  Day 10:  7,500
  Day 11: 10,000
  Day 12: 15,000

Week 3-4: Scale phase
  Day 15:  25,000
  Day 18:  50,000
  Day 22:  75,000
  Day 25: 100,000

Week 5-6: Full volume
  Day 29: 150,000
  Day 33: 250,000
  Day 36: Full volume

Adjust based on bounce/complaint rates:
  → Bounce rate > 5%: pause, clean list, resume at lower volume
  → Spam complaints > 0.1%: pause, review content and targeting
  → Deferrals increasing: slow down, extend warming period
```

## Authentication requirements (2026)

```
Mandatory for bulk senders (>5,000/day):

SPF:
  □ DNS TXT record authorizing sending IPs
  □ Include ESP's SPF mechanism
  □ Stay under 10 DNS lookups

DKIM:
  □ 2048-bit RSA key minimum
  □ Aligned domain (d= matches From domain)
  □ Rotate keys annually

DMARC:
  □ p=quarantine or p=reject (p=none is insufficient)
  □ Aligned with SPF or DKIM (preferably both)
  □ rua= for aggregate reports
  □ ruf= for forensic reports (optional)

Additional:
  □ One-click List-Unsubscribe header (RFC 8058)
  □ Valid reverse DNS (PTR record) for sending IPs
  □ TLS encryption for SMTP connections
```

## Dedicated vs. shared IPs

```
Dedicated IP:
  → You control the reputation entirely
  → Requires warming from scratch
  → Best for: >100K emails/month, consistent volume
  → Risk: low volume = stale reputation

Shared IP:
  → Reputation shared with other senders on same IP
  → No warming needed (already established)
  → Best for: <100K emails/month, variable volume
  → Risk: bad neighbor damages your deliverability

Recommendation:
  → Transactional email: dedicated IP (consistent volume)
  → Marketing email: dedicated IP (control reputation)
  → Low-volume senders: shared IP (insufficient volume to warm)
  → Always separate transactional and marketing IPs
```

## Monitoring during warming

| Metric | Healthy | Warning | Critical |
|---|---|---|---|
| **Bounce rate** | <2% | 2-5% | >5% |
| **Spam complaint rate** | <0.05% | 0.05-0.1% | >0.1% |
| **Inbox placement** | >90% | 70-90% | <70% |
| **Open rate** | >20% | 10-20% | <10% |
| **Deferral rate** | <5% | 5-15% | >15% |

```
Monitoring tools:
  → Google Postmaster Tools (Gmail reputation dashboard)
  → Microsoft SNDS (Outlook/Hotmail reputation)
  → Sender Score (Return Path / Validity)
  → MXToolbox (blacklist monitoring)
  → DMARC aggregate reports (rua=)
```

## Recovery from reputation damage

```
1. Identify the cause:
   → Check Google Postmaster Tools for reputation drop
   → Review DMARC reports for authentication failures
   → Scan blacklists (Spamhaus, Barracuda, SORBS)
   → Analyze bounce logs for spam trap hits

2. Stop the bleed:
   → Pause all marketing sends immediately
   → Continue transactional sends only
   → Remove unengaged subscribers (no open in 90 days)
   → Scrub list against known spam trap databases

3. Request delisting:
   → Follow each blacklist's removal process
   → Spamhaus: fill removal form, wait 24-48 hours
   → Barracuda: automated removal after 12 hours of no spam

4. Re-warm:
   → Restart warming schedule with most engaged segment
   → Monitor metrics daily during re-warming
   → Gradually re-add subscriber segments by engagement
```

## Anti-patterns

- **Blasting full volume on day one** — sending your entire list from
  a new IP. Mailbox providers will immediately throttle or block the
  IP. Start with 50-100 emails and scale over 4-6 weeks.
- **Warming with unengaged subscribers** — using your least engaged
  subscribers during warming. These recipients generate low engagement
  signals, teaching mailbox providers that your emails are unwanted.
  Start with your most engaged subscribers.
- **Sharing IPs between transactional and marketing** — a spam
  complaint on a marketing email damages the IP reputation used for
  transactional emails (password resets, order confirmations). Always
  separate transactional and marketing on different IPs.
- **Ignoring DMARC reports** — setting up DMARC with rua= but never
  reading the aggregate reports. DMARC reports reveal authentication
  failures, unauthorized senders using your domain, and alignment
  issues. Review reports weekly.

## Gotchas

- **Domain reputation persists across IPs** — switching to a new IP
  does not reset domain reputation. If your domain has a poor
  reputation, a new IP will inherit it. Fix domain reputation before
  warming a new IP.
- **Weekend sending drops** — sending volume drops on weekends can
  look like irregular sending patterns to mailbox providers. Maintain
  consistent daily volume during warming, even on weekends.
- **ESP migration resets IP reputation** — moving from SendGrid to
  SES (or vice versa) means warming new IPs from scratch, even if
  your domain reputation is excellent. Plan for a 4-6 week warming
  period during ESP migrations.
- **Gmail feedback loop** — Gmail does not provide a traditional
  feedback loop (FBL). Use Google Postmaster Tools instead. Yahoo,
  Outlook, and AOL do provide FBLs — register for all of them.

## Verification

- New IPs follow a 4-6 week warming schedule.
- SPF, DKIM (2048-bit), and DMARC (p=quarantine+) are configured.
- Transactional and marketing email use separate IPs.
- Spam complaint rate stays below 0.1%.
- Google Postmaster Tools and DMARC reports are reviewed weekly.
- List hygiene removes unengaged subscribers and invalid addresses.
- One-click List-Unsubscribe header is present in all marketing email.

## Related

- `documentation/docs/policies/email/dark-mode-email-accessibility.md`
- `documentation/docs/policies/email/spf-dkim-dmarc-setup.md`
- `documentation/docs/policies/monitoring/alerting-strategy-routing-escalation.md`

## Source URLs (verified 2026-08-16)

- What's IP Warm Up 2026 — https://www.mailreach.co/blog/whats-ip-warm-up
- Domain Warming Best Practices for 2026 — https://www.mailforge.ai/blog/domain-warming-best-practices
- IP Warming for Better Email Deliverability — https://clearout.io/blog/ip-warming-for-better-email-deliverability/
- 10 Email Deliverability Best Practices for 2026 — https://mailtani.com/blog/email-deliverability-best-practices
