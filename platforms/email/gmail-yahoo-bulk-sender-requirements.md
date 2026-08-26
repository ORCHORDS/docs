# Gmail / Yahoo / Microsoft bulk sender requirements (2024–2026)

**Issue:** Since February 2024, Google and Yahoo enforce mandatory authentication and unsubscribe requirements on any sender delivering 5,000+ messages per day to their users. Microsoft and Apple followed. Non-compliant senders are rejected or bulk-filed, and the failure looks like a mysterious deliverability collapse with no bounce explanation.
**Date:** 2026-08-13
**Author:** ORCHORDS
**Status:** documented

The requirements apply **per sending domain**, aggregated across all subdomains and IPs that authenticate under the same organizational domain. The 5,000/day threshold is counted against the recipient provider's users (e.g., messages delivered to Gmail addresses), not your total outbound volume.

## Symptom

- Sudden drop in Gmail/Yahoo/Outlook deliverability starting around Feb 2024 (or later, as each provider turned on enforcement).
- Bounces like "550 5.7.1 — our system has detected that this message is likely unsolicited mail" or provider-specific policy rejection codes.
- Mail reaches some providers (smaller ones, B2B) but is consistently filtered or blocked at Gmail/Outlook/Yahoo.
- Google Postmaster Tools shows the domain as "Low" or "Bad" reputation with authentication failures spiking.
- The same content and volume worked fine for years and nothing obvious changed on your side.

The cause is the provider enforcing one or more of: missing DMARC record, DMARC at `p=none`, SPF/DKIM/DMARC not passing domain alignment, missing one-click unsubscribe header, spam complaint rate above 0.3%, or missing TLS transport.

## Gotchas

- **The 5,000/day threshold is per organizational domain, not per subdomain or per IP.** Splitting volume across `news.example.com` and `promo.example.com` does not exempt you — both authenticate under `example.com` and the aggregate counts.
- **`p=none` DMARC is not compliant.** Google and Yahoo require DMARC to exist, but enforcement effectively pushes senders toward `p=quarantine` or `p=reject`. A `p=none` record that has existed for years may now silently cap your reputation.
- **Domain alignment is mandatory.** SPF, DKIM, and the `From:` header must all align to the same organizational domain. A third-party ESP signing DKIM with its own domain while you send `From: you@example.com` fails alignment unless the ESP signs with a selector under your domain (most do — verify it).
- **One-click unsubscribe (RFC 8058) is required, not just `List-Unsubscribe`.** The `List-Unsubscribe-Post: List-Unsubscribe=One-Click` header plus a working HTTPS POST endpoint is mandatory for bulk senders. A mailto-only unsubscribe header is not sufficient.
- **The unsubscribe must be honored within 2 days (Google) / 48h (Yahoo).** Lazy batch processing that takes a week will get you flagged.
- **Spam complaint rate threshold is 0.3% (Google).** Above this, reputation drops and enforcement tightens. Monitor via Google Postmaster Tools, not your ESP's reported complaint rate (which only counts FBL-registered complaints).
- **TLS is required for transport.** Opportunistic TLS that downgrades to plaintext will fail; receiving MTAs increasingly refuse non-TLS SMTP.
- **Forwarded mail breaks everything.** Mailing lists and forwarders break SPF/DKIM; without ARC sealing by the forwarder, forwarded bulk mail fails DMARC at the final recipient. This is a forwarder-side problem you cannot fully fix.
- **Marketing vs. transactional matters.** These rules technically apply to bulk/commercial mail; pure transactional mail (password resets, receipts) is generally exempt from the unsubscribe requirement but still must pass authentication. Misclassify marketing as transactional to dodge the rules and you risk being reclassified as bulk retroactively.
- **Microsoft's enforcement timeline lagged Google/Yahoo.** Senders who were "fine" at Gmail in 2024 may hit Microsoft enforcement later. Verify SNDS/JMRP status independently.

## Practical compliance checklist

**Authentication (all three, aligned):**
```
; SPF — include all sending services
example.com.  IN TXT  "v=spf1 include:_spf.google.com include:amazonses.net ~all"

; DKIM — at minimum one signing selector per sending service
selector1._domainkey.example.com.  IN CNAME  selector1.example.com.dkim.amazonses.org.

; DMARC — start at p=none with monitoring, ramp to quarantine then reject
_dmarc.example.com.  IN TXT  "v=DMARC1; p=quarantine; adkim=s; aspf=s; rua=mailto:dmarc-reports@example.com; pct=100; fo=1"
```
- Ramp DMARC: `p=none` (monitor) → `p=quarantine; pct=10` → `pct=100` → `p=reject; pct=100`.
- Use `adkim=s` and `aspf=s` (strict alignment) — relaxed alignment can mask misconfigurations that bite later.

**One-click unsubscribe headers (required for bulk):**
```
List-Unsubscribe: <https://unsubscribe.example.com/u/eyJhbGci...>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```
- The HTTPS URL must accept a POST with no body and return 200, removing the recipient immediately.
- Sign the unsubscribe token; do not expose a sequential user ID.
- Process unsubscribes within 48h and make the endpoint idempotent (re-POST is a no-op).

**Spam complaint rate monitoring:**
- Register Google FBL (Postmaster Tools), Microsoft JMRP, Yahoo CFL.
- Alert if rolling 7-day complaint rate exceeds 0.2% (buffer under the 0.3% ceiling).

**TLS transport:**
- Publish MTA-STS policy enforcing TLS (`mode=enforce`) so receiving MTAs refuse downgrade attacks.
- Publish TLS-RPT to receive failure reports.

## Verification
- Run the message through Google's [Postmaster Tools](https://postmaster.google.com) — confirm domain/IP reputation, spam rate, and authentication pass rate are all "High" / green.
- Use [mail-tester](https://www.mail-tester.com/) or MXToolbox Delivery Audit for a quick auth + content check.
- Verify DMARC reports (`rua`) show ~0% failures over a 2-week window before escalating to `p=reject`.
- Send a real test campaign to a small (5%) segment first, confirm complaint rate and placement, then scale.
- Confirm the one-click POST endpoint returns 200 from outside your network (curl from a clean IP).

## Sources
- [Bulk Email Sender Rules For Google, Yahoo, Microsoft & Apple (2026) — PowerDMARC](https://powerdmarc.com/bulk-email-sender-requirements/)
- [Gmail & Yahoo Bulk Sender Requirements 2026 (Updated Jan 2026) — MailRisk](https://mailrisk.io/guides/gmail-yahoo-sender-requirements-2026)
- [Google & Yahoo Email Sender Requirements 2026 — MXScan](https://mxscan.me/google-yahoo-email-requirements-2026)
- [Email Authentication 2026: BIMI & Brand Logo — Hustler Marketing](https://www.hustlermarketing.com/blog/email-authentication-2026-everything-you-need-to-know-about-bimi-and-brand-logo-display/)
- [RFC 8058 — Signaling One-Click Functionality for List Email Headers](https://datatracker.ietf.org/doc/html/rfc8058)
