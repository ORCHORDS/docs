# Abuse Prevention on Anonymous Platforms

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The platform permits posting without a persistent account. Within
weeks of launch, a harassment campaign targets a real person, a
coordinated spam ring inflates post counts, and a CSAM upload
bypasses the age gate because there is no account to verify
against. Law enforcement requests identity data the platform does
not hold. Anonymity is a design feature that doubles as the
primary attack surface for every abuse category.

## Context

example project allows adults to post content without registering. This
eliminates the identity layer most platforms use for
accountability. The abuse threat model shifts: bad actors exploit
session gaps, IP churn, and the absence of friction. NCMEC
reporting obligations under 18 U.S.C. § 2258A still apply
regardless of the anonymity model. DSA Article 14 notice-and-
takedown still applies even without user accounts.

## Threat model and content signals

```
Threat              Vector                    Severity
────────────────────────────────────────────────────────
Harassment          Pseudonym + IP churn      High
Spam / botnet       No-account posting        High
CSAM upload         No identity gate          Critical
Radicalization      Recommendation + anon     High

Session-scoped signals (replace account-level trust scores):
  → Posting velocity (posts per hour per session token)
  → Perceptual hash match against CSAM/NCII database
  → Text classifier: harassment, hate speech, spam
  → Image classifier: CSAM probability score
  → Link domain reputation (phishing / malware feeds)
  → Duplicate / near-duplicate content ratio

Platform-level signals:
  → IP subnet reputation (Tor exit, datacenter CIDR)
  → User-report density against this session token
  → Device fingerprint reuse across previously banned sessions
  → Browser automation cues (headless, CDP presence)
```

## IP and device reputation tiers

```
Tier 1 — Deny at edge (Cloudflare WAF):
  Tor exit nodes (cf.botManagement.score)
  Known datacenter CIDRs used by bot farms
  IPs on CISA / Spamhaus DROP lists

Tier 2 — Friction gate (CAPTCHA / proof-of-work):
  Residential proxies (high confidence)
  New subnets with no posting history

Tier 3 — Rate limit only:
  Clean residential IPs
  Mobile carrier NAT ranges (many users per IP)

Device fingerprint:
  Canvas hash + WebGL renderer + screen DPI combo
  Resurfaces banned session's fingerprint → auto-challenge
  Store HMAC of fingerprint token only — never raw canvas
  data; raw fingerprints are personal data (GDPR Recital 30)
```

## Rate limiting anonymous actions

```
Without accounts, rate limits attach to network identifiers
and session tokens.

  POST /content   10 per session per hour
                  100 per /24 subnet per hour
                  Burst: 3 per 10 seconds

  POST /report    5 per session per day (anti-abuse of reports)

  Session token issuance:
    1 token per IP per 30 minutes (hard)
    5 tokens per /24 per hour → CAPTCHA trigger

  IPv6: rate-limit at /48 prefix, not /64 — mobile devices
  rotate through many /64 prefixes on the same carrier.
```

## Appeal flow without an account

```
1. User receives removal notice with a UUID removal token
   embedded in the 403 response body
2. User submits /appeal with the removal token + counter-
   evidence (text, URL) — no email required
3. Human moderator reviews signal record (classifier scores,
   IP subnet, report density) — NOT user identity
4. Decision: restore / uphold / escalate to legal
5. Response delivered via the same removal token

Do NOT require email for appeals — defeats anonymity.
DO require the removal token to prevent spurious flood.
```

## Anti-patterns

- **Blocking entire /16 subnets** — mobile carrier NATs share
  one /24 among thousands of legitimate users. Block at /32
  or session level first.
- **Storing raw device fingerprints** — browser fingerprints
  are personal data under GDPR Recital 30. Store only HMAC.
- **CAPTCHA as the only defense** — CAPTCHAs are solved cheaply
  by human farms. Use as friction, not a hard boundary.
- **Delaying NCMEC reports** — 18 U.S.C. § 2258A requires
  reporting within 24 hours of actual knowledge of CSAM.
  Anonymity of the uploader does not delay this obligation.

## Gotchas

- **Tor exit node lists change daily** — use a live feed, not
  a static blocklist. Stale lists miss new exits.
- **Radicalization is a slow signal** — CSAM and spam are
  detectable in real time. Radicalization emerges over days.
  Behavioral graph analysis across sessions (shared fingerprint
  or subnet) is needed to surface this category.
- **GDPR still applies** — IP addresses are personal data under
  GDPR Recital 30 even without account linkage. Log retention
  for abuse investigation must be bounded (30-90 days) and
  documented in the ROPA.

## Verification

- CSAM hashing runs on every upload before storage.
- Session-scoped rate limits enforced at the edge.
- IP reputation tier evaluated per-request at Cloudflare.
- Appeal flow returns decision without requiring email.
- Device fingerprint stored as HMAC only.
- Tor exit node list refreshes at least daily.

## Related

- `documentation/categories/issues/877-csam-vendor-integration.md`
- `documentation/categories/issues/platform-liability-section-230-dsa.md`
- `documentation/categories/issues/age-verification-online-platforms-regulation.md`
- `documentation/categories/issues/user-privacy-law-enforcement-requests.md`

## Source URLs (verified 2026-08-17)

- NCMEC CyberTipline (18 U.S.C. § 2258A)
  — https://www.missingkids.org/theissues/csam
- Cloudflare bot management signals
  — https://developers.cloudflare.com/bots/concepts/bot-score/
- Tor Project bulk exit list
  — https://check.torproject.org/torbulkexitlist
- GDPR Recital 30 (online identifiers as personal data)
  — https://gdpr-info.eu/recitals/no-30/
- Spamhaus DROP list
  — https://www.spamhaus.org/drop/
