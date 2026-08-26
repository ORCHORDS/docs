# BIMI — Brand Indicators for Message Identification

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your marketing emails land in the inbox but look generic — no brand logo
appears next to your sender name. Customers cannot visually distinguish
your legitimate emails from phishing attempts that spoof your domain.
You have invested in SPF, DKIM, and DMARC but see no visible benefit
in the recipient's inbox. Open rates are below industry benchmarks, and
your brand lacks visual presence in crowded inboxes.

## Context

BIMI (Brand Indicators for Message Identification) is an email
authentication standard that displays a verified brand logo next to
authenticated emails in supported inboxes. In 2026, BIMI is supported
by Gmail, Yahoo Mail, Apple Mail (iOS 16+/macOS Ventura+), Fastmail,
and several regional providers. BIMI builds on the foundation of SPF,
DKIM, and DMARC — it requires DMARC enforcement (p=quarantine or
p=reject) as a prerequisite. The standard is defined in an IETF draft
and is overseen by the AuthIndicators Working Group.

## Prerequisites

BIMI requires a fully deployed email authentication stack:

```
1. SPF  → Published SPF record for your sending domain
2. DKIM → All outgoing mail signed with DKIM
3. DMARC → Published with p=quarantine or p=reject (not p=none)
4. BIMI → DNS TXT record pointing to your logo and certificate
```

BIMI will not work with DMARC policy set to `p=none` (monitoring only).
You must enforce DMARC before implementing BIMI.

## Implementation

### 1. Prepare the logo

BIMI requires a logo in SVG Tiny Portable/Secure (SVG P/S) format:

| Requirement | Specification |
|---|---|
| Format | SVG Tiny 1.2 Portable/Secure |
| Shape | Square (displayed as circle in most clients) |
| Background | Solid color (no transparency) |
| File size | < 32 KB |
| Content | Trademarked logo (for VMC) or brand logo (for CMC) |
| No text | Avoid small text — logo is displayed at ~40px |

The SVG P/S format is a restricted subset of SVG — no JavaScript, no
external references, no animations. Use a BIMI logo generator tool to
convert your logo.

### 2. Obtain a certificate

| Certificate type | Requirement | Cost | Supported by |
|---|---|---|---|
| **VMC** (Verified Mark Certificate) | Registered trademark | $1,000-1,500/year | Gmail, Apple Mail |
| **CMC** (Common Mark Certificate) | No trademark required | $100-300/year | Gmail (since 2024), Yahoo |
| **None** | Self-asserted logo | Free | Yahoo, Fastmail (limited) |

Gmail requires either a VMC or CMC. Yahoo and Fastmail display
self-asserted logos without a certificate (but with DMARC enforcement).

### 3. Publish the DNS record

```dns
default._bimi.example.com. IN TXT "v=BIMI1; l=https://example.com/logo.svg; a=https://example.com/cert.pem"
```

| Field | Description |
|---|---|
| `v=BIMI1` | BIMI version |
| `l=` | URL to SVG P/S logo file (HTTPS required) |
| `a=` | URL to VMC/CMC certificate (PEM format). Empty for self-asserted |

### 4. Verify

```bash
# Check BIMI DNS record
dig TXT default._bimi.example.com

# Use BIMI Inspector
# https://bimigroup.org/bimi-generator/
```

## How BIMI works in the inbox

```
1. Email arrives at recipient's mail server
2. Server checks SPF, DKIM, and DMARC → all pass
3. DMARC policy is p=quarantine or p=reject → enforced
4. Server queries BIMI DNS record for sender domain
5. Server fetches SVG logo and verifies certificate
6. Logo is displayed next to sender name in inbox
```

The logo is cached by mail providers — updates to the logo may take
24-48 hours to propagate.

## Impact on deliverability and engagement

| Metric | Without BIMI | With BIMI |
|---|---|---|
| Brand recognition | Sender name only | Logo + sender name |
| Open rate | Baseline | +10-39% uplift (reported by early adopters) |
| Phishing protection | DMARC only | Visual verification for recipients |
| Trust signals | None visible | Verified brand indicator |

BIMI does not directly improve deliverability (inbox placement) — it
improves engagement by making authenticated emails visually distinct.

## Anti-patterns

- **Deploying BIMI before DMARC enforcement** — BIMI requires
  p=quarantine or p=reject. Deploying with p=none wastes effort because
  no mail provider will display the logo.
- **Using a complex logo** — logos are displayed at approximately 40x40
  pixels. Detailed logos with small text are unrecognizable. Use a
  simplified icon version of your brand mark.
- **Skipping the VMC/CMC for Gmail** — self-asserted logos (no
  certificate) work on Yahoo but not Gmail. If Gmail is your primary
  audience, invest in a VMC or CMC.
- **Forgetting subdomain BIMI records** — if you send from
  marketing.example.com, you need a BIMI record for that subdomain,
  not just example.com.

## Gotchas

- **SVG P/S format is strict** — standard SVG files exported from
  design tools (Figma, Illustrator) do not comply with SVG Tiny P/S.
  Use a dedicated converter or validator.
- **Certificate renewal** — VMC/CMC certificates expire annually.
  Missing renewal means logos stop displaying with no warning.
- **Apple Mail requirements** — Apple Mail requires a VMC (not CMC)
  and displays the logo only when the message is from a known sender
  or in the VIP list.
- **Logo caching** — mail providers cache BIMI logos aggressively.
  After updating your logo, it may take days for recipients to see the
  new version. There is no cache invalidation mechanism.

## Verification

- DMARC is published with p=quarantine or p=reject.
- BIMI DNS TXT record exists for all sending domains and subdomains.
- SVG logo passes BIMI validator (bimigroup.org/bimi-generator).
- VMC or CMC certificate is valid and not expired.
- Logo displays correctly in Gmail, Yahoo Mail, and Apple Mail.
- Logo is recognizable at 40x40 pixel display size.

## Related

- `documentation/categories/email/spf-dkim-dmarc-authentication.md`
- `documentation/categories/email/email-deliverability-best-practices.md`
- `documentation/categories/security/dns-security.md`

## Source URLs (verified 2026-08-16)

- BIMI Group — https://bimigroup.org/
- BIMI email authentication 2026 — https://www.hustlermarketing.com/blog/email-authentication-2026-everything-you-need-to-know-about-bimi-and-brand-logo-display/
- Sectigo BIMI guide — https://www.sectigo.com/blog/what-is-bimi
- Adobe BIMI implementation — https://experienceleague.adobe.com/en/docs/deliverability-learn/deliverability-best-practice-guide/additional-resources/technotes/implement-bimi
