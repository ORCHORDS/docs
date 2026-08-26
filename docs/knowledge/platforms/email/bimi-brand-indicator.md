# bimi-brand-indicator

**Issue:** Displaying your brand logo in supported email clients via BIMI
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You want your company logo to appear next to emails in Gmail and Apple Mail without relying on client-side contact photos.

## Pattern / Solution
Prerequisites:
1. DMARC at `p=quarantine` or `p=reject`
2. A Verified Mark Certificate (VMC) from Entrust or DigiCert (paid; requires trademark registration)
3. An SVG logo in BIMI-compliant Tiny PS format

DNS record at `default._bimi.yourdomain.com`:
```
v=BIMI1; l=https://yourdomain.com/bimi-logo.svg; a=https://yourdomain.com/bimi-cert.pem
```

- `l=` — URL to the SVG logo (must be HTTPS, publicly accessible)
- `a=` — URL to the VMC PEM certificate chain

SVG requirements:
- Must be SVG Tiny 1.2 Portable/Secure profile
- No external references, no scripts
- Viewbox must be square (1:1 aspect ratio)
- Convert with: `svgomg` or Adobe Illustrator BIMI export

Check compliance: `bimigroup.org/bimi-checker`

## Gotchas
- Gmail requires a VMC; the `a=` tag is mandatory for Gmail display
- Apple Mail supports BIMI without a VMC (as of iOS 16+)
- The VMC costs ~$1,000–$1,500/year and requires an active trademark registration
- Yahoo Mail was an early adopter; Microsoft Outlook does not support BIMI as of 2026
- Selector support (`selector._bimi.domain`) is not universally implemented; `default` is safest

## Related
- `dmarc-policy-setup.md`
- `dkim-record-setup.md`
- `email-reputation-monitoring.md`
