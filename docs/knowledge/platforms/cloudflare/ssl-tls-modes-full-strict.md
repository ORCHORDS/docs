# ssl-tls-modes-full-strict

**Issue:** Every Cloudflare zone has an SSL/TLS encryption mode — Off, Flexible, Full, or Full (strict) — and it is a zone-wide setting that decides what happens on the leg between Cloudflare's edge and your origin server. Flexible silently downgrades that leg to plaintext HTTP; Full encrypts but validates nothing, so an on-path attacker between Cloudflare and the origin can impersonate the origin with any self-signed certificate. Both modes are extremely common in the wild because they "just work" with no origin certificate installed, and both quietly violate the security model users assume when they see the padlock. The correct production posture is Full (strict) with a valid origin certificate (Cloudflare Origin CA or a public CA like Let's Encrypt), plus hardening around it. This article is the runbook for auditing and landing that posture.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The four modes, precisely

1. **Off.** No HTTPS anywhere; Cloudflare serves plain HTTP. Never in production; exists only for legacy/broken setups.
2. **Flexible.** HTTPS visitor-to-Cloudflare, but Cloudflare fetches the origin over plain HTTP. The origin must listen on port 80, and traffic on that last mile crosses the public internet unencrypted — cookies, tokens, and PII in the clear. Also the classic cause of infinite redirect loops when the origin force-redirects HTTP to HTTPS. Treat any zone on Flexible as a finding.
3. **Full.** HTTPS end-to-end, but Cloudflare accepts any certificate the origin presents — self-signed, expired, wrong hostname. Encryption without authentication: a MITM positioned between Cloudflare and the origin can terminate TLS and re-encrypt. Better than Flexible, still not the target state.
4. **Full (strict).** HTTPS end-to-end and Cloudflare validates the origin certificate: a publicly trusted CA cert (Let's Encrypt etc.) or a Cloudflare Origin CA certificate. This is Cloudflare's explicit recommendation whenever the origin is not using Authenticated Origin Pulls-style mTLS at Enterprise scale, and it is the only mode where the padlock means what users think it means.

## Getting to Full (strict)

1. **Install an origin certificate first, then flip the mode.** Order matters: on a zone currently in Flexible/Full, provision the cert on the origin, verify HTTPS origin fetches work, and only then switch the zone to Full (strict). Flipping first produces 526 errors for every visitor.
2. **Cloudflare Origin CA is the low-maintenance option.** Free certificates from the dashboard/API, valid up to 15 years, trusted only by Cloudflare (which is all that matters when all traffic arrives via Cloudflare). Not suitable if anything bypasses Cloudflare to reach the origin directly.
3. **Public CA when the origin is reachable directly.** If ops tooling, health checks, or DNS-only (grey-cloud) hostnames hit the origin without passing Cloudflare, use Let's Encrypt/ACME with automated renewal instead, since Origin CA certs throw trust errors for non-Cloudflare clients.
4. **Fix redirect loops after upgrading.** With Flexible, origins that redirect HTTP to HTTPS loop forever. Once on Full (strict), the origin can (and should) accept HTTPS and redirect HTTP to HTTPS itself; Cloudflare sends HTTPS on the origin leg, so the loop disappears. Enable Always Use HTTPS at the edge too.
5. **Verify, do not assume.** After the switch, check responses for 526 (invalid origin cert) and use a request through the zone to confirm normal 200s. A curl directly to the origin with SNI confirms the cert the origin actually serves.

## Hardening around the mode

1. **Authenticated Origin Pull (AOP) for mutual TLS.** Full (strict) authenticates the origin to Cloudflare; AOP additionally authenticates Cloudflare to the origin: the origin requires a Cloudflare client certificate on every TLS handshake, so random internet scanners hitting the origin IP get dropped at handshake. Configure in SSL/TLS, Origin Pull, then require client cert verification at the origin (nginx `ssl_verify_client`, Apache `SSLVerifyClient require`). Note the related Workers mTLS pattern is for arbitrary client certs; AOP is the zone-product version for origin protection.
2. **Lock the origin to Cloudflare IPs or Tunnel.** A valid cert does not stop attackers from probing the origin directly. Firewall the origin to Cloudflare IP ranges, or move it behind cloudflared Tunnel so there is no listening public port at all — Tunnel plus Origin CA plus Full (strict) is the strongest simple posture.
3. **Raise the minimum TLS version.** SSL/TLS, Edge Certificates, Minimum TLS Version: set 1.2 minimum (1.3 where your client base allows) and disable old protocol versions; also enable TLS 1.3 for faster handshakes.
4. **HSTS once you are committed.** Enable HSTS (with a short max-age first, then raise it) only after confirming every subdomain and asset hostname serves HTTPS — HSTS is sticky and cannot be un-sent from browsers that received it.
5. **Certificate coverage across hostnames.** The edge Universal certificate covers the apex and first-level wildcards; deeper subdomains need ACM/Total TLS or custom certificates. Do not let a missing hostname cert push a subdomain back to Flexible as a workaround.

## Audit and operations

1. **Audit all zones programmatically.** Pull the `ssl` setting per zone via the API (`/zones?per_page=50` then read `ssl` on each) and flag anything not `strict`. Flexible on a zone touching user data is a High-severity finding, not a style choice.
2. **Watch for 525/526 in logs.** 525 means the SSL handshake failed outright; 526 means the cert failed validation (expired Origin CA cert, wrong hostname, self-signed on a strict zone). Both are origin-leg problems — fix at the origin, never by downgrading the mode.
3. **Track origin cert expiry.** Origin CA's 15-year horizon makes expiry a surprise years later; put expiry dates in inventory. ACME-managed public certs fail differently — monitor renewal job output.
4. **Per-hostname exceptions are intentional and rare.** The mode is zone-wide; a genuinely broken legacy hostname that cannot do TLS belongs on its own zone or behind Tunnel, not on a Flexible whole zone.

## References

1. **SSL/TLS encryption modes.** developers.cloudflare.com/ssl/origin-configuration/ssl-modes/ — the four modes and Cloudflare's recommendation.
2. **Full (strict).** developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/.
3. **Origin CA certificates and Authenticated Origin Pulls.** developers.cloudflare.com/ssl/origin-configuration/origin-ca-cert/ and /authenticated-origin-pull/.
