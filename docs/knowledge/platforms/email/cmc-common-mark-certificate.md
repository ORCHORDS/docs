# CMC (Common Mark Certificate) for BIMI

**Issue:** BIMI (Brand Indicators for Message Identification) displays your logo in recipients' inboxes, but the established VMC (Verified Mark Certificate) costs $1,000–$3,000/year, requires a registered trademark, and is out of reach for brands that use an unregistered logo. You want the BIMI logo without the VMC cost and trademark overhead.
**Date:** 2026-08-13
**Author:** ORCHORDS
**Status:** documented

The **Common Mark Certificate (CMC)** is a lower-cost BIMI certificate type introduced as an alternative to the VMC. It allows a sender to publish a logo via BIMI without proving registered trademark ownership. As of 2025–2026, Gmail accepts CMCs for BIMI logo rendering, broadening BIMI access to brands that lack a registered mark.

## Symptom

- You want the inbox logo visibility of BIMI but the brand logo is not a registered trademark (or trademark registration is pending/in another jurisdiction).
- VMC quotes come back at $1,500+/year and the legal workflow (trademark verification, affidavits) blocks you.
- You have DMARC at `p=quarantine` or `p=reject`, SPF and DKIM aligned, and a correctly formatted BIMI DNS record, but the logo still does not render in Gmail.
- Competitors' logos show in Gmail; yours does not, despite identical authentication.

The cause is usually one of: no certificate attached to the BIMI record (Gmail requires a VMC *or* CMC for logo display), or using a VMC where a CMC would have been accepted more cheaply.

## Gotchas

- **CMC vs VMC is a real distinction, not marketing.** VMC requires registered trademark proof (USPTO/UKIPO/EUIPO registration number verified by the CA). CMC requires only that you own the domain and the logo artwork — no trademark registration. The cert chain and the BIMI record `l=` URL point to the same kind of PEM file, but the validation behind it differs.
- **Provider support is not uniform.** Gmail accepts CMC as of 2025. Verify current support for Yahoo, Apple, and Microsoft before committing — support has been rolling out unevenly. A CMC that renders in Gmail may be ignored elsewhere.
- **DMARC enforcement is still required.** BIMI (with either cert type) requires DMARC at `p=quarantine` or `p=reject` with `pct=100` and aligned SPF/DKIM. `p=none` disqualifies you regardless of cert.
- **The logo SVG must match the certificate.** The SVG in the BIMI record must be byte-identical (or hash-matched per the CA's policy) to the logo embedded in the certificate. Editing the SVG after issuance breaks the display.
- **CMCs are still issued by approved CAs only.** You cannot self-sign. As of 2026, authorized issuers include DigiCert and Entrust; check the [BIMI Group's approved CA list](https://bimigroup.org/) before buying.
- **CMC does not give the legal warranty a VMC implies.** VMC's trademark verification gives receivers higher assurance the logo is legitimately owned. Some security-conscious receivers may treat CMC logos as lower-trust in the future. Monitor for policy changes.
- **BIMI Authority (the `a=` URL) is optional and separate.** Google's BIMI Authority endpoint can re-check logo validity at render time; it is not a substitute for the cert.
- **Logo rendering can take days to weeks after DNS/cert setup.** Gmail caches BIMI lookups; do not assume failure because the logo does not appear in 5 minutes.

## Practical setup

**1. Prerequisites:**
- SPF, DKIM, DMARC all passing with alignment.
- DMARC at `p=quarantine` or `p=reject`, `pct=100`.
- A logo as SVG (specific format: `<svg>` root, no JavaScript, specific viewBox — follow the BIMI SVG specification).

**2. Obtain a CMC:**
- Choose an approved CA (DigiCert, Entrust — verify on [bimigroup.org](https://bimigroup.org/)).
- Submit domain control validation (DCV) and the logo SVG.
- Receive the certificate as a PEM file.

**3. Host the certificate and logo:**
- Host the PEM certificate at a stable HTTPS URL (e.g., `https://example.com/.well-known/bimi/cmc.pem`).
- Host the SVG logo at another HTTPS URL.
- Both URLs must serve correct `Content-Type` and be publicly fetchable.

**4. Publish the BIMI DNS record:**
```
default._bimi.example.com.  IN TXT  "v=BIMI1; l=https://example.com/.well-known/bimi/logo.svg; a=https://example.com/.well-known/bimi/auth-logo.svg; e=cmc.pem-url-or-vmc.pem-url"
```
- `l=` — the logo SVG URL.
- `a=` — optional authority URL (Google's enhanced check).
- `e=` — the certificate URL (CMC or VMC PEM).

Actually, the standard record format omits the cert in the DNS record itself in some implementations; the cert is referenced via the BIMI Authority mechanism. Follow the [current BIMI specification](https://bimigroup.org/bimi-specification/) for the exact field your receiver expects — the spec has evolved and different receivers parse it differently.

**5. Verify:**
- Use [MXToolbox BIMI lookup](https://mxtoolbox.com/BIMILookup.aspx) or [dmarcian's BIMI inspector](https://dmarcian.com/bimi/).
- Send a test message to a Gmail account and wait up to 2 weeks for logo caching to refresh.

## Verification
- DMARC must be at enforcement (`p=quarantine`/`p=reject`, `pct=100`) — verify via [MXToolbox DMARC](https://mxtoolbox.com/DMARC.aspx).
- BIMI record resolves and the cert URL returns HTTP 200 with `Content-Type: application/x-pem-file`.
- Logo SVG passes the BIMI SVG validator (correct root element, dimensions, no forbidden elements).
- Logo renders in Gmail (allow up to 14 days for cache refresh).
- If using a CMC, confirm current Gmail support — re-check quarterly, as provider support is still evolving.

## Sources
- [BIMI: VMC vs CMC, DNS prerequisites and 2025 compatibility — CaptainDNS](https://www.captaindns.com/en/blog/bimi-vmc-cmc-compatibilite-dns)
- [Email Authentication 2026: BIMI & Brand Logo — Hustler Marketing](https://www.hustlermarketing.com/blog/email-authentication-2026-everything-you-need-to-know-about-bimi-and-brand-logo-display/)
- [Is a VMC certificate required for BIMI in Gmail? — r/sysadmin](https://www.reddit.com/r/sysadmin/comments/1t1r301/is_a_vmc_certificate_required_for_bimi_in_gmail/)
- [BIMI Group — specification and approved CA list](https://bimigroup.org/)
