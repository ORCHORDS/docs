# smtp-relay-outbound-architecture

**Issue:** Every application eventually needs to send email — password resets, invoices, alerts, digests — and the architecture decision of how those messages leave the infrastructure is deceptively hard. Self-hosting outbound SMTP hands the team full control but also full responsibility for IP reputation, bounce handling, and the 2024+ bulk-sender requirements that Gmail and Microsoft now enforce (SPF, DKIM, DMARC, one-click unsubscribe). Blindly handing everything to a managed API service solves deliverability but adds per-message cost, vendor lock-in, and a third party in the data path for sensitive mail. This article covers the sending-architecture options, when each makes sense, how to design a hybrid relay topology, and how to warm and monitor sender reputation so outbound email does not silently degrade.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three architectural options

1. **Fully self-hosted MTA.** Running Postfix or Haraka on your own IPs gives maximum control and near-zero marginal cost per message, but 2025 practitioner consensus (Hacker News, r/selfhosted) is that it is only worth operating below the pain line or above roughly 50K messages per month: below that volume the 1-2 hours of monthly maintenance never amortizes, and inbox placement at Google and Microsoft is dominated by IP reputation you cannot quickly build.
2. **Managed transactional API.** Postmark, SMTP2GO, SendGrid, MailerSend, and similar services accept messages over HTTPS or authenticated SMTP and handle IP pools, bounce parsing, feedback loops, and compliance. Independent deliverability testing (EmailToolTester) consistently ranks these providers at 95-99% inbox placement, which is the core product being purchased.
3. **Hybrid relay.** The pattern most small operators converge on: self-host inbound mail (receiving is easy — spam filtering is your problem, not your reputation) and relay all outbound through a cheap transactional service or a smarthost. You keep your domain and mailboxes local while outsourcing the part that is genuinely hard.

## Why self-hosting outbound is hard

1. **IP reputation is the real product.** Most of the world's mailboxes sit behind Google and Microsoft filtering, and both weight sending-IP history heavily; a fresh VPS IP, or one previously used by a spammer, starts effectively blocked regardless of how correct your configuration is, and rehabilitation is measured in weeks of slow warm-up.
2. **The 2024+ bulk-sender rules are now enforced.** Gmail and Microsoft require SPF and DKIM alignment, DMARC at least at p=none, and RFC 8058 one-click unsubscribe for bulk mail; messages failing these checks are rejected or bulk-foldered, so "correct setup" is a moving compliance target, not a one-time configuration.
3. **Shared infrastructure contamination.** On cloud IPs or shared hosting, other tenants' spam behavior damages the reputation of ranges you share; a dedicated IP with proper warm-up is the mitigation, but an unwarmed dedicated IP performs worse than a reputable provider's shared pool.
4. **Operational surface area.** Queue management, TLS certificate hygiene, bounce and complaint loops, DNS email security records across every sending domain, and blocklist delisting all become your on-call burden; these are precisely the functions a relay provider has already industrialized.

## Designing the relay topology

1. **Local submission MTA, remote delivery.** Point applications at a local Postfix (or container-side smtpd) bound to loopback that accepts mail, rewrites envelopes as needed, and relays through the upstream provider over authenticated SMTP on submission port 587 (STARTTLS) or 465 (implicit TLS); apps never talk to the internet directly and gain a spooling queue for free when the provider has an outage.
2. **One relay credential per environment.** Give production, staging, and CI separate relay credentials and, ideally, separate subdomains (staging mails from mtatest.example.com); test messages hitting the production domain's reputation is a classic self-inflicted wound.
3. **Separate identity domains from delivery.** Keep transactional mail (password resets) on a different subdomain than marketing or human correspondence (news.example.com vs example.com) so a spam complaint against a newsletter never drags down password-reset deliverability; each identity gets its own SPF and DKIM keys.
4. **Document the exit points.** Inventory everything that can send mail — cron daemons, monitoring, SaaS integrations, application servers — and route them all through the relay; a single appliance mailing directly from a raw cloud IP is enough to poison domain reputation for everyone.

## Warming and monitoring reputation

1. **Warm new senders gradually.** Ramp volume over 2-4 weeks — start at tens of messages per day to engaged recipients and double every few days while watching bounce and complaint rates; providers' shared pools arrive pre-warmed, which is a large part of what you pay them for.
2. **Instrument bounce and complaint rates.** Keep hard bounces under 2% and spam complaints under 0.1% (Google's enforcement threshold); surface these as dashboards and alerts, because the first symptom of a reputation problem is usually a slow drift in these numbers before any blocklist listing.
3. **Consume feedback loops and blocklists.** Register with provider feedback loops where available, monitor Spamhaus and similar blocklists for your sending IPs, and set up DMARC aggregate reports (rua) parsing — the reports tell you exactly which sources are failing alignment before receivers start penalizing you.
4. **Check the basics before escalating.** When deliverability drops, verify forward-confirmed reverse DNS on the sending IP, SPF/DKIM/DMARC alignment with a free validator, and one-click unsubscribe headers; nine out of ten "Gmail is eating our mail" incidents trace to a record that regressed during a DNS or vendor change.
