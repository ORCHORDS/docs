# Secondary sending domain strategy

**Issue:** Sending marketing, transactional, and cold-outreach email from the same domain risks contaminating your primary domain's reputation. One bad blast (high spam complaints, a blocklist hit, a sudden volume spike) drags down the corporate domain — and suddenly password-reset emails and invoices land in spam too.
**Date:** 2026-08-13
**Author:** ORCHORDS
**Status:** documented

A secondary sending domain strategy segregates email streams across separate subdomains (or separate registered domains) so that reputation problems in one stream do not poison the others. Each stream gets its own SPF/DKIM/DMARC/BIMI setup, its own IP reputation (optionally its own IP), and its own deliverability trajectory.

## Symptom

- A marketing campaign generates high spam complaints → corporate transactional email (password resets, receipts) starts landing in spam.
- Cold outreach / sales prospecting pollutes the primary domain and the compliance team's emails start bouncing.
- A newsletter signup confirmation competes for inbox placement with a high-volume promotional blast sent minutes earlier from the same domain.
- One ESP's poor sending reputation (shared IP pool) drags down another ESP's deliverability on the same domain.
- The CEO's email to a partner lands in spam because a marketing blast the night before triggered Outlook filtering.

The cause is shared reputation: mailbox providers track reputation per organizational domain (and per IP). Mixing high-risk, high-volume, and high-trust streams on one domain means one bad stream tanks all of them.

## Gotchas

- **Reputation is tracked per organizational domain, not just per subdomain.** `news.example.com` and `promo.example.com` share the `example.com` reputation for DMARC purposes. To fully isolate reputation, you need a separate *registered* domain (e.g., `examplemail.com` for marketing), not just a subdomain. Subdomain segregation helps with some providers but is weaker than a separate apex domain.
- **DMARC aggregates across subdomains.** Because DMARC policy applies to the organizational domain, a `p=reject` on `example.com` affects `mail.example.com` too. Plan authentication at the org-domain level; do not assume subdomain isolation under DMARC.
- **Separate domains need full warming.** A new secondary domain starts with no reputation. Sending full volume on day one guarantees spam-folder placement. Budget 4–8 weeks of IP/domain warming (see `ip-warming-strategy.md`, `domain-warming-strategy.md`) per new sending domain.
- **The `From:` display name still matters.** Even with `news@examplemail.com`, recipients see the brand name in the display name. If recipients do not recognize the secondary domain and mark it spam, reputation tanks regardless of strategy. Use consistent branding in the display name and warm recipients into recognizing the new address.
- **Reply-to handling is a leak point.** If replies go back to `support@example.com` but the mail was sent from `news@examplemail.com`, reply forwarding can break DMARC/SPF and confuse recipients. Decide deliberately where replies land and authenticate that path.
- **Separate ESPs do not auto-isolate reputation.** Two ESPs sending from the same domain share that domain's reputation. The point of a secondary domain is to isolate the *domain*, not just the ESP.
- **Cold email needs the strongest isolation.** Cold outreach has the highest spam-complaint risk. Use a dedicated registered domain (not a subdomain of the corporate domain), separate IP, and accept that this domain may need periodic replacement if it gets burned.
- **BIMI/logo setup must be repeated per domain.** Each sending domain that should show a logo needs its own BIMI record and (for VMC/CMC) its own certificate — they are not inherited.
- **DNS sprawl is real.** Three sending domains × (SPF + DKIM + DMARC + BIMI + MTA-STS + TLS-RPT) = a lot of records to keep in sync. Use DNS infrastructure-as-code (Terraform, octoDNS) or a managed DNS provider to prevent drift.

## Practical domain architecture

**Typical 3-domain split for a mid-size company:**
```
example.com              → corporate/personal email (Google Workspace / M365)
                           ONLY human-to-human mail. Never bulk send.

transactional.example.com → password resets, receipts, security alerts
                           ESP: Resend / Postmark / SES
                           Auth: SPF/DKIM/DMARC strict, BIMI optional

marketing.examplemail.com → newsletters, promotions, lifecycle campaigns
                           (separate registered domain to isolate reputation)
                           ESP: SendGrid / Mailgun / dedicated IP
                           Auth: full suite, warmed 4-8 weeks

outreach.examplemail2.com → cold sales prospecting
                           (separate registered domain, disposable)
                           ESP: specialized cold-email infra
                           Auth: full suite, aggressive warmup, monitor daily
```

**Decision rules:**
- Isolate by *risk tier*, not by department. Marketing and lifecycle belong together (similar risk); cold outreach must be alone.
- Use a subdomain of the corporate domain for transactional (recipients recognize `transactional.example.com` and trust it). Use a *separate registered domain* for cold outreach (recipients will not recognize it, and you may need to burn it).
- Volume over ~50k/day in any one stream justifies a dedicated IP for that stream.

**Per-domain setup checklist (repeat for each):**
1. Register/configure the domain.
2. Configure MX records (for inbound, if replies are handled there).
3. Publish SPF including only that domain's sending services.
4. Publish DKIM selectors for that domain's ESP(s).
5. Publish DMARC starting at `p=none` with `rua=` monitoring, ramp to enforcement.
6. (Optional) Publish BIMI with cert.
7. Publish MTA-STS (`mode=enforce`) and TLS-RPT.
8. Warm the domain/IP over 4-8 weeks before full volume.
9. Set up Postmaster Tools / SNDS monitoring for the domain/IP.

## Verification
- Confirm each sending domain has independent SPF/DKIM/DMARC — no shared include that would cross-contaminate.
- Verify DMARC `rua` reports for the corporate domain show near-zero marketing/transactional volume (proving isolation).
- Send a test blast from the marketing domain and confirm corporate domain reputation (Postmaster Tools) does not move.
- Periodically (quarterly) audit DNS records across all sending domains for drift.
- For cold-outreach domains, check daily: blocklist status, inbox placement, complaint rate. Be ready to retire and replace a burned domain within 48h.

## Sources
- [Cold Email in 2026: Domains, Deliverability, Replies — UnifyGTM](https://www.unifygtm.com/explore/cold-email-2026-domain-setup-deliverability-sequences)
- [Email Deliverability 2026: Best Practices, Updates & Guide — MessageFlow](https://messageflow.com/blog/email-deliverability-2026/)
- [Bulk Email Sender Rules For Google, Yahoo, Microsoft & Apple (2026) — PowerDMARC](https://powerdmarc.com/bulk-email-sender-requirements/)
