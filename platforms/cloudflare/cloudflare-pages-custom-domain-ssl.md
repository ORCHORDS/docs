# cloudflare-pages-custom-domain-ssl

**Issue:** Custom domain and SSL setup for Cloudflare Pages —
         CNAME flattening, Universal SSL timing, mobile cert
         pinning risks with auto-renewal, www vs apex routing,
         and Pages-specific SSL behaviours that differ from
         Workers and zone-level settings
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

The Cloudflare Pages project is deployed and `example project.pages.dev`
loads fine, but the custom domain `example.com` returns a 522
(Connection Timed Out) or an SSL_ERROR_RX_RECORD_TOO_LONG error
for up to 30 minutes after adding the domain in the Pages
dashboard. Or: `www.example.com` works but `example.com` (apex)
returns a 404 from the Pages routing layer. Or: a mobile app
with certificate pinning starts throwing SSL errors after a cert
auto-renewal the team did not initiate.

## Context

Cloudflare Pages custom domains involve three distinct systems
working in sequence: DNS (CNAME or CNAME-flattened A for apex),
Universal SSL certificate provisioning (Cloudflare's CA issues
the cert), and the Pages routing layer (which subdomain or apex
maps to which Pages project and branch). Each system has a
separate propagation timeline and failure mode. This article
covers all three and the specific ways Pages differs from a
standard zone setup.

---

## How Pages Custom Domain DNS Works

Pages custom domains require the zone to be on Cloudflare. The
DNS record type depends on whether you are adding a subdomain or
the apex:

```
Subdomain (www.example.com):
  Type:  CNAME
  Name:  www
  Value: example project.pages.dev
  Proxy: Enabled (orange cloud)
  → Cloudflare CNAME-follows pages.dev, proxies the response

Apex (example.com):
  Type:  A (CNAME flattening — CF converts it internally)
  Name:  @
  Value: 192.0.2.1  (placeholder — CF overrides for CNAME target)
  Proxy: Enabled (orange cloud)
  → CF's DNS returns its own anycast IPs, but internally
    routes the traffic to the Pages project
```

CNAME flattening is automatic for apex records on CF. When you
point the apex CNAME to `example project.pages.dev`, CF returns its own
anycast A record to external resolvers while routing traffic to
the Pages project internally.

---

## Adding the Custom Domain Step by Step

```
Step 1 — Pages Dashboard
  Project → Custom Domains → Add a Custom Domain
  Enter: example.com
  CF creates the DNS record automatically if the zone is in the
  same account.

Step 2 — DNS record verification (automated)
  CF checks that the CNAME/A record resolves to its infrastructure.
  Time: immediate if same-account zone; up to 24 h if external DNS
  is delegating only the subdomain to CF nameservers.

Step 3 — TLS certificate provisioning
  CF's Let's Encrypt integration issues a Universal SSL cert for:
    example.com AND www.example.com (SAN cert)
  Time: 1–15 min in normal conditions; up to 24 h on first-time
  setup or during CF cert issuance backlog.

Step 4 — Pages routing activation
  CF's Pages routing layer maps the hostname to the correct project
  and branch (production branch for the custom domain).
  Time: immediate after cert is issued.
```

During Step 3, HTTPS requests to the custom domain will receive
a cert mismatch or connection error. HTTP requests on port 80 may
return a CF redirect to HTTPS which then fails. Do not test prod
until the Pages dashboard shows "Active" for the custom domain.

---

## SSL Timing Table

| Phase                        | Typical Duration   | Max Observed    |
|------------------------------|--------------------|-----------------|
| DNS record created (same acct)| < 1 min           | 2 min           |
| DNS resolves to CF IPs       | < 5 min (TTL)      | 30 min (ext DNS)|
| Universal SSL cert issued    | 1–15 min           | 24 h (backlog)  |
| Pages routing active         | Immediate post-cert| N/A             |
| Full propagation (global)    | 5–30 min total     | 2 h (rare)      |

If the Pages dashboard shows "Active" but HTTPS still errors,
flush your local DNS cache and try from a different network.
The issue is almost always a cached negative DNS response or a
CDN/ISP resolver that has not propagated yet.

---

## www vs Apex Routing

Cloudflare Pages does not automatically redirect `www` to apex
or vice versa. Both must be added as separate custom domains, and
Pages will serve the project at both. Canonical redirect (www →
apex or apex → www) must be handled by a Pages Function, a Bulk
Redirect rule, or a Transform Rule.

```ts
// functions/_middleware.ts — canonical redirect in Pages Function
export const onRequest: PagesFunction = async ({ request, next }) => {
  const url = new URL(request.url);
  // Redirect www → apex
  if (url.hostname === "www.example.com") {
    url.hostname = "example.com";
    return Response.redirect(url.toString(), 301);
  }
  return next();
};
```

Or use a Bulk Redirect rule in the CF dashboard:

```
Source URL:      https://www.example.com/
Target URL:      https://example.com/
Status:          301
Preserve path suffix: Yes
Include subpaths:     Yes
```

The Bulk Redirect approach fires before the Pages Function and
is more efficient for simple www/apex canonicalisation.

---

## Universal SSL vs Advanced Certificate Manager

Pages always uses Universal SSL (free, auto-managed, shared SAN
cert per zone). Advanced Certificate Manager (ACM) is a paid
add-on that allows:
- Single-hostname dedicated certs
- Custom certificate validity periods
- Custom CA chains (not Let's Encrypt)
- Certificate pinning-safe cert rotation policies

If your mobile app pins certificates, you need ACM with a custom
CA or controlled rotation policy. Universal SSL certs rotate on
Let's Encrypt's schedule (roughly every 90 days) with no advance
notice and no fixed public key.

---

## Mobile Certificate Pinning Risk

Universal SSL for Pages rotates automatically. If a mobile app
pins the leaf certificate or the full certificate chain, it will
break at the next auto-renewal.

```
Anti-pattern (pins leaf cert or chain):
  pinned cert:  CN=example.com, issued by Let's Encrypt R3
  Renewal date: unknown (Cloudflare-managed, no customer control)
  Effect:       App fails SSL validation after renewal
                Returns NSURLErrorCancelled or CERTIFICATE_VERIFY_FAILED

Safe pattern (pins SPKI of intermediate CA only):
  Pinned SPKI:  Let's Encrypt R3 intermediate — stable across rotations
  OR:           Move to ACM with a custom CA + controlled rotation
```

Extracting the intermediate CA SPKI for pinning:

```bash
# Get the cert chain for the Pages domain
openssl s_client -connect example.com:443 -showcerts 2>/dev/null \
  | openssl x509 -noout -pubkey \
  | openssl pkey -pubin -outform der \
  | openssl dgst -sha256 -binary \
  | base64
# → This gives the SPKI hash to pin in the app
```

For iOS (NSPinnedDomains in Info.plist) and Android (network_
security_config.xml), pin the intermediate CA's SPKI, not the
leaf. This survives cert rotation as long as the CA does not
change, which Let's Encrypt R3/E1 have not done since 2021.

---

## Pages-Specific SSL Behaviours

```
Behaviour 1 — SSL mode is always Full (Strict) for Pages
  Pages does not use a customer-provided origin cert; it IS the
  origin. The zone's SSL/TLS mode setting (flexible/full/strict)
  does not apply to Pages requests. They are always encrypted
  end-to-end between the browser and CF.

Behaviour 2 — Minimum TLS version applies
  The zone's minimum TLS version setting (Security → SSL/TLS →
  Edge Certificates) DOES apply to Pages custom domains.
  Default is TLS 1.0; set to TLS 1.2 for mobile API clients.

Behaviour 3 — HSTS must be enabled explicitly
  Strict-Transport-Security is not set by default on Pages
  responses. Add it in a Pages Function or _headers file:
    /_headers:
      https://example.com/*
        Strict-Transport-Security: max-age=31536000; includeSubDomains

Behaviour 4 — Pages dev previews use *.pages.dev cert, not custom
  Preview deployments (example project-<hash>.pages.dev) use the Pages
  wildcard cert, not the custom domain cert. If your mobile app
  is pointed at a preview URL, no custom cert applies.
```

---

## _headers File for SSL-Related Headers

```
# public/_headers
# Applied to all Pages responses on custom domain

https://example.com/*
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), camera=(), microphone=()

https://www.example.com/*
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

---

## Anti-patterns

- **Adding the custom domain before the zone is on Cloudflare.**
  Pages requires the zone to be proxied through CF. External DNS
  CNAMEs pointing to `example project.pages.dev` bypass the Pages routing
  layer and do not receive the custom-domain SSL cert.
- **Pinning the Pages leaf certificate in a mobile app.** Cert
  rotates every ~90 days silently. Use intermediate CA SPKI
  pinning or ACM with a controlled rotation.
- **Assuming the www and apex share the same cert state.** Each
  hostname is a separate SAN on the Universal SSL cert; each
  propagates on its own timeline.
- **Using SSL mode "Flexible" on the zone and expecting Pages to
  honour it.** Pages always terminates TLS at the CF edge; the
  zone's SSL mode has no effect.

## Gotchas

- Removing a custom domain from the Pages project does NOT remove
  the DNS record or invalidate the SSL cert. The cert and record
  must be cleaned up separately in the zone's DNS tab and Edge
  Certificates panel.
- A Pages project cannot have two projects mapped to the same
  custom domain. Attempting to add a domain already claimed by
  another Pages project results in an error with no clear message
  in the dashboard. Check existing projects first.
- The Pages dashboard shows "Active" when the cert is issued and
  the DNS record resolves correctly. It does NOT wait for global
  DNS propagation. A status of "Active" does not mean all users
  can reach the domain yet.
- Pages Free plan has a maximum of 100 custom domains per project.
  Paid plan (Workers Paid) raises this, but the limit is per-
  project, not per-account.

## Verification

```bash
# Check cert is issued and valid
curl -vI https://example.com/ 2>&1 | grep -E "SSL|subject|issuer"
# → SSL connection using TLSv1.3 / ...
# → subject: CN=example.com
# → issuer: C=US, O=Let's Encrypt, CN=R3

# Check HSTS header is present
curl -sI https://example.com/ | grep -i strict
# → strict-transport-security: max-age=31536000; includeSubDomains

# Check www redirect
curl -sI https://www.example.com/ | grep -i location
# → Location: https://example.com/

# Check TLS minimum version (should reject TLS 1.0)
openssl s_client -connect example.com:443 -tls1
# → handshake failure (expected, if minimum is TLS 1.2)
```

## Related

- `cloudflare/pages-best-practices.md`
- `cloudflare/pages-headers-config.md`
- `cloudflare/ssl-tls-modes-full-strict.md`
- `cloudflare/advanced-certificate-manager-total-tls.md`
- `cloudflare/cloudflare-dns-workers-custom-domains.md`

## Source URLs

- https://developers.cloudflare.com/pages/configuration/
  custom-domains/
- https://developers.cloudflare.com/ssl/edge-certificates/
  universal-ssl/
- https://developers.cloudflare.com/ssl/advanced-certificate-
  manager/
- https://developers.cloudflare.com/pages/configuration/
  headers/
