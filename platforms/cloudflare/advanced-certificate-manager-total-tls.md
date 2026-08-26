# advanced-certificate-manager-total-tls

**Issue:** A zone has outgrown the default Universal SSL certificate — the team needs wildcard or multi-level subdomain coverage (`api.staging.example.com`), per-hostname minimum TLS, OV/EV certificates from their own CA, or certificates issued for customer domains on a SaaS product — and is staring at four overlapping options: Advanced Certificate Manager (ACM), Total TLS, Custom (uploaded) Certificates, and Cloudflare for SaaS custom hostnames. This article maps what each one buys, on which plan, with the validation methods (HTTP/TXT/delegated DCV), key formats, and the rate-limit/propagation gotchas that cause outages during renewal windows.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What each certificate option buys, on which plan

1. **Universal SSL (free, all plans) — the baseline.** On a full-setup zone it covers the apex and first-level subdomains (`example.com`, `www.example.com`); on a partial (CNAME-setup) zone each proxied hostname gets its own certificate regardless of depth. DV only, Cloudflare-managed issuance and renewal.
2. **Advanced Certificate Manager (ACM) — paid add-on on every plan (Free through Enterprise).** A per-zone monthly subscription (marketed at US$10/month — confirm on the pricing page). It orders "advanced certificates" with: up to 50 covered hostnames each (apex counts as one), multi-level subdomains, wildcards, your choice of CA, validation method, and validity period; plus delegated DCV for CNAME-setup zones, Total TLS, custom origin trust stores, customizable cipher suites, and per-hostname minimum TLS versions. Enterprise can additionally buy an ACM subscription allowing up to 100 edge certificates per zone.
3. **Total TLS — an ACM feature, not a separate product.** Requires ACM purchased and a full DNS setup; automatically issues an individual certificate for every proxied hostname at any subdomain depth.
4. **Custom Certificates (uploaded) — Business and Enterprise.** You bring your own OV/EV/UCC/DV certificate and private key when you need CA control or organization validation; Cloudflare does not manage issuance or renewal — you own the expiry monitoring.
5. **Cloudflare for SaaS custom hostnames — all plans, metered.** Issues certificates for *other people's* domains (your customers' `app.customer.com`) routed to your zone: 100 custom hostnames included, US$0.10 per additional hostname per month, 50,000 max on self-serve, custom pricing at Enterprise (where wildcard SANs, uploaded custom certificates, and CSR support are also gated).

## ACM mechanics and limits

1. **50 SANs per certificate, single domain only.** The apex must be one of the 50 hostnames; a certificate cannot span multiple domains — multi-domain certs require Cloudflare for SaaS.
2. **Wildcards cover exactly one subdomain level.** `*.example.com` does not cover `api.staging.example.com`; combine a wildcard SAN with explicit deeper SANs or use Total TLS.
3. **RFC name-length limits apply to every certificate.** Max 253 characters total per domain, 63 per label, and 64 for the CN. Hostnames longer than the CN limit can only be ordered via the API with `cloudflare_branding: true` (puts `sni.cloudflaressl.com` in the CN and your long hostname in a SAN) — the dashboard refuses them.
4. **Advanced certificates do not cover Pages or R2 custom domains** (those use Cloudflare for SaaS certificates via certificate prioritization), are DV-only (OV/EV → Custom Certificates), and there is no HTTP public key pinning anywhere.
5. **Partial-setup zones may not need ACM at all.** Universal SSL on a partial zone already provisions per-hostname certificates at any depth, provided you proxy and validate each hostname as it is added — ACM's value there is CA/validity choice, delegated DCV, and cipher/min-TLS control, not depth.

## Total TLS gotchas

1. **Requirements.** ACM purchased + full DNS setup. Issued certs appear as type "Advanced – Total TLS" with a default 90-day validity.
2. **Excluded products.** Hostnames used with Cloudflare Load Balancing, Tunnel, or Spectrum do not get Total TLS certificates — order advanced certificates for those manually or use other certificate types.
3. **Deleting a Total TLS certificate is a permanent opt-out.** The system treats deletion as intentional and will never order a new certificate for that hostname again, even if you delete and recreate the DNS record. This is the classic "why is this one subdomain on a self-signed error forever" footgun.
4. **The CN 64-character restriction still applies.** Very long hostnames need API-ordered advanced certificates with `cloudflare_branding: true` instead.

## Custom Certificates (bring your own)

1. **Upload requirements.** PEM, PKCS#7, or PKCS#12 encoding; no key-file password; at least 14 days of remaining validity at upload; a SAN matching at least one hostname in the zone; private key ≥ 2048-bit RSA or ≥ 225-bit ECDSA; publicly trusted (unless bundling methodology is `User Defined`); type must be UCC, EV, DV, or OV.
2. **Use `sni_custom`, not `legacy_custom`.** The API treats uploads as legacy by default — explicitly set `"type": "sni_custom"` unless a specific client cannot send SNI. `legacy_custom` is additionally incompatible with BYOIP.
3. **You own the lifecycle.** Upload, renewal-before-expiry, and expiry monitoring are all on you — unlike every other option here, an expired custom certificate is an outage you caused. Optional geo-key restrictions can limit where the private key is decryptable (e.g., `{"label": "us"}`).
4. **Bundle method matters on upload.** With `compatible` or `modern` bundling, upload only the leaf certificate so Cloudflare handles intermediate/root expiry; `ubiquitous` is the maximum-compatibility default.

## SSL for SaaS: issuing certificates for customer domains

1. **Custom hostnames + fallback origin.** The customer CNAMEs `app.customer.com` at your SaaS zone; Cloudflare issues a per-custom-hostname certificate and routes to your fallback (or per-hostname custom) origin. Never create a custom hostname matching the zone name itself. Customers already on Cloudflare lose control of Argo, Early Hints, Page Shield, Spectrum, and wildcard DNS for those hostnames.
2. **Two separate validations per hostname.** Hostname ownership (`ownership_verification` / `ownership_verification_http` → drives `status`) and certificate issuance (`ssl.validation_records` → drives `ssl.status`) use different tokens. Production traffic needs `status: active`, `ssl.status: active`, and DNS pointed at your SaaS target — all three.
3. **HTTP vs TXT certificate validation.** HTTP validation needs the hostname already proxying through Cloudflare (customer just adds the CNAME; accepts a few minutes of pre-cert downtime) and cannot validate wildcards. TXT validation requires the customer to publish a TXT record at their authoritative DNS, works for wildcards, and lets you pre-validate before cutting traffic over for near-zero downtime. Exactly one `ssl.method` (`http` | `txt`) per custom hostname.
4. **Delegated DCV beats asking customers repeatedly.** A one-time delegation record lets Cloudflare auto-issue and auto-renew future certificates (including wildcard renewals) without per-renewal customer action.
5. **Incompatibilities.** Custom hostnames fronted by another CDN fail validation (obfuscated DNS), and a restrictive CAA record at the customer's domain blocks the CA from issuing — check CAA before blaming Cloudflare. Issuance after validation is minutes, not instant; poll the API rather than assuming success.

## Operational checklist

1. **Before buying ACM, list what you actually need.** Multi-level coverage on a full-setup zone, per-hostname min TLS, ciphers, or Total TLS → ACM. OV/EV or CA mandate → Custom Certificates. Customer domains → SaaS. Nothing above → stay on Universal SSL.
2. **Renewal monitoring on anything you uploaded.** Custom Certificates expire silently if unmanaged; Total TLS and advanced certificates renew automatically. Alert on edge-certificate expiry regardless, via the API or dashboard notifications.
3. **Keep CAA records aligned with your chosen CA** for both your own zones and SaaS customer guidance — a CAA mismatch is the most common "certificate stuck pending validation" cause after DNS propagation.
4. **Propagation patience.** New certificates take minutes to deploy globally after validation succeeds; do not delete-and-recreate certificates in a loop while waiting, and remember the Total TLS delete-is-forever rule above.

## Related

- `paid-tier-security-upgrade-runbook.md` — where ACM/Total TLS sit in a paid-tier security upgrade sequence (written in parallel with this article).
- `free-tier-domain-security-runbook.md` — the $0 baseline (zone-level min TLS 1.2, HSTS ordering) that per-hostname ACM controls extend.
- `dnssec-enablement.md` — the other half of DNS-layer trust; enable before or alongside certificate work.
- `workers-custom-domains.md` — custom domains on Workers and their certificate behavior.
- `workers-mtls-certificates.md` — mutual TLS (origin-side client certificates), which composes with, but is distinct from, edge certificate choices here.
