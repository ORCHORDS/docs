# BIMI and Verified Mark Certificate

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The `default._bimi` DNS record is published and the logo
renders in Apple Mail and Yahoo Mail, but Gmail still shows
the generic avatar. BIMI checker passes but Gmail displays
nothing. A phishing lookalike domain appears in the inbox
without a logo, making spoofs visually indistinguishable from
the real sender to users.

## Context

BIMI (Brand Indicators for Message Identification) lets
participating mail clients display a brand's verified logo in
the inbox avatar position beside the sender name. Gmail
requires a Verified Mark Certificate (VMC) from an approved
Certificate Authority to display the logo — the `a=` tag in
the DNS record is mandatory. Apple Mail, Yahoo Mail, and
Fastmail accept BIMI without a VMC using the `l=` tag alone.
The standard is maintained by the AuthIndicators Working
Group; client support and CA requirements are evolving.

## DMARC Prerequisite

BIMI requires DMARC at enforcement level — `p=quarantine`
or `p=reject` — applied to 100 % of mail. A `pct=` value
below 100 disqualifies the domain:

```
# _dmarc.yourdomain.com  TXT
v=DMARC1; p=reject; pct=100;
  rua=mailto:dmarc@yourdomain.com;
  adkim=s; aspf=s;
```

`adkim=s` (strict alignment) is recommended alongside BIMI
to prevent subdomain spoofing. Certificate Authorities
validate the DMARC record before issuing a VMC — confirm
enforcement is active and stable for at least 30 days before
applying. Partial enforcement (`p=quarantine; pct=10`) does
not satisfy requirements.

## SVG Logo Requirements (Tiny PS)

BIMI requires SVG Tiny 1.2 Portable/Secure (Tiny PS) profile:

| Requirement      | Specification                            |
|------------------|------------------------------------------|
| File format      | `.svg` only (no PNG, WebP, or GIF)       |
| SVG profile      | Tiny PS — no scripts, no external refs   |
| Aspect ratio     | 1:1 square `viewBox`                     |
| Background       | Full square, solid colour or `#ffffff`   |
| Safe region      | Logo centred inside inner circle (80 %)  |
| File size        | Under 32 KB recommended                  |
| `<use>` elements | Not permitted                            |
| Raster embeds    | Not permitted (no `<image href>`)        |

Convert with Illustrator → Save As SVG → SVG Tiny 1.2 profile,
or the Inkscape BIMI export extension. Validate at
`https://bimigroup.org/bimi-checker/` — it reports profile
violations, aspect ratio errors, and external references.

## Verified Mark Certificate from DigiCert / Entrust

A VMC cryptographically binds an active trademark to a domain
and a specific SVG file. Approved CAs: DigiCert and Entrust.
Cost: approximately USD 1,200–1,500/year (2026).

Steps: (1) hold an active trademark with USPTO, EUIPO, or
equivalent — pending applications are not accepted;
(2) prepare the Tiny PS SVG at a stable HTTPS URL;
(3) submit the trademark number, SVG, and domain to the CA;
(4) host the resulting PEM chain and reference it in `a=`.

The certificate embeds a hash of the SVG. Updating the SVG
without reissuing the VMC causes Gmail to stop showing the
logo.

## DNS Record

Publish a TXT record at `default._bimi.yourdomain.com`:

```
v=BIMI1;
l=https://cdn.yourdomain.com/bimi/logo.svg;
a=https://cdn.yourdomain.com/bimi/cert.pem
```

| Tag | Value                            | Required for Gmail |
|-----|----------------------------------|--------------------|
| `v` | `BIMI1`                          | Yes                |
| `l` | HTTPS URL to Tiny PS SVG         | Yes                |
| `a` | HTTPS URL to VMC PEM chain       | Yes                |

Use `default` as the selector; named selectors are not
universally supported. Verify after propagation (48 hours):

```sh
dig TXT default._bimi.yourdomain.com +short
```

## Gmail and Apple Mail Support

| Client           | VMC required | DMARC minimum          |
|------------------|--------------|------------------------|
| Gmail (web)      | Yes          | p=quarantine or reject |
| Gmail (iOS)      | Yes          | p=quarantine or reject |
| Apple Mail (iOS) | No           | p=quarantine or reject |
| Apple Mail macOS | No           | p=quarantine or reject |
| Yahoo Mail       | No           | p=quarantine or reject |
| Fastmail         | No           | p=quarantine or reject |
| Outlook (Win)    | No support   | —                      |

Gmail reached full availability in 2024 for VMC senders.
Outlook desktop has no BIMI support as of 2026.

## ROI vs Cost

| Cost item               | Approx. cost (USD)  |
|-------------------------|---------------------|
| VMC annual fee          | 1,200 – 1,500       |
| Trademark registration  | 250 – 400 (USPTO)   |
| Designer SVG prep       | 200 – 500 (one-time)|
| DNS / CDN hosting       | Negligible          |
| **Total year one**      | ~1,650 – 2,400      |

Reported benefits (SendGrid / BIMI Working Group, 2023):
10–21 % higher click-through; 90 % brand recognition after
one send; phishing spoofs display no logo, making them
visually distinguishable. ROI is strongest for high-volume
senders with brand-recognition goals.

## Anti-patterns

- Publishing a BIMI record before DMARC reaches enforcement —
  Gmail silently ignores the BIMI record.
- Embedding raster images in the SVG via `<image href>` —
  this violates Tiny PS; the VMC validation fails.
- Letting the VMC expire — Gmail removes the logo within days
  of certificate expiry. Set a calendar alert 60 days before
  the VMC expiry date.
- Using `pct=50` in DMARC alongside BIMI — partial policy
  does not satisfy requirements; enforcement must be 100 %.
- Changing the SVG file without reissuing the VMC — the
  embedded hash will no longer match.

## Gotchas

- The SVG URL must remain stable; path changes require a DNS
  TTL flush and possible VMC reissuance.
- Only DigiCert and Entrust are approved CAs for VMC as of
  2026; self-signed certificates are not accepted.
- BIMI logos appear in the Gmail inbox list view only, not
  the compose pane; always verify in a real Gmail inbox.
- The `a=` VMC URL must serve a valid PEM chain over HTTPS
  trusted by standard root stores.

## Verification

```sh
# Confirm DMARC enforcement
dig TXT _dmarc.yourdomain.com +short
# Must contain: p=quarantine or p=reject; pct=100

# Confirm BIMI record
dig TXT default._bimi.yourdomain.com +short

# Confirm VMC endpoint is reachable
curl -sI https://cdn.yourdomain.com/bimi/cert.pem \
  | grep -E 'HTTP|Content-Type'

# Online BIMI validator
# https://bimigroup.org/bimi-checker/
```

Send a test email from the BIMI-enabled domain to a Gmail
account and inspect the inbox list view — the brand logo
should appear in the avatar position.

## Related

- email/dmarc-policy-setup.md
- email/dkim-record-setup.md
- email/spf-record-setup.md
- email/email-reputation-monitoring.md
- email/bimi-brand-indicator.md

## Source URLs (verified 2026-08-17)

- https://bimigroup.org/
- https://bimigroup.org/bimi-checker/
- https://support.google.com/mail/answer/2451839
- https://www.digicert.com/tls-ssl/verified-mark-certificates
- https://www.entrust.com/digital-security/certificate-solutions/products/verified-mark-certificate
