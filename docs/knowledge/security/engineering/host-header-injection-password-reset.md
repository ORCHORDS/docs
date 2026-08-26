# host-header-injection-password-reset

**Issue:** The application generates absolute URLs — password-reset links, email-verification links, canonical/OG tags, redirect targets — by reading the `Host` header (or the `X-Forwarded-Host` override header) from the incoming request, on the flawed assumption that the header is not user-controllable. An attacker requests a password reset for the victim while rewriting `Host: evil-user.net`; the emailed link becomes `https://evil-user.net/reset?token=...`, and when the victim clicks it (or an email-scanner bot fetches it), the genuine reset token lands on the attacker's server. The same trust enables Host-based cache poisoning, routing-based SSRF, and authentication bypass. Off-the-shelf apps are the most exposed because they don't know their deployment domain and default to deriving it from the request.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Attack vectors that come from Host trust

1. **Password reset poisoning.** Attacker triggers a reset for the victim with a tampered `Host`; the app mails a reset link pointing at the attacker's domain containing a valid token; the token leak (click or automated fetch) yields full account takeover. Boost click rates by sending a fake "breach notification" email first.
2. **Host override headers.** Even when `Host` is validated, frameworks and proxies commonly trust `X-Forwarded-Host` (often enabled by default) when constructing URLs — probe both, because hardening only one leaves the path open.
3. **Web cache poisoning via Host.** The Host value is reflected into cached response content (canonical links, absolute asset URLs), poisoning every user served that cache entry.
4. **Routing-based SSRF.** Intermediaries that route on the Host value can be steered toward internal systems; combine with proxy allowlist gaps to reach back-ends that were never meant to be public.
5. **Dangling markup fallback.** If the reset link itself can't be flipped, an injected Host can still break out into the email HTML; JavaScript won't run in mail clients, but dangling-markup exfiltration of the token inside the same email often still works.
6. **Ambiguity probes.** Testers send duplicate Host headers, absolute-URI request lines, and malformed-but-partially-valid Hosts — flawed validation (substring matching, parsing quirks) frequently lets the malicious value through.

## Defenses

1. **Prefer relative URLs in server-side code.** If a link works as `/reset?token=...`, never build an absolute one; most email flows need only one absolute base, so shrink the attack surface to that single template.
2. **Hardcode the domain in configuration.** For the places an absolute URL is genuinely required (email templates), define the base URL in config/environment — never read it from the request. This alone kills password-reset poisoning.
3. **Validate Host against an allowlist and fail closed.** Use framework enforcement such as Django's `ALLOWED_HOSTS`; reject (or at minimum redirect) any request whose Host is not exactly a permitted value — no substring or suffix matching.
4. **Do not trust host-override headers.** Strip or ignore `X-Forwarded-Host` (and `X-Original-URL`, `X-Rewrite-URL`) unless the proxy layer overwrites them deterministically before they reach the app; if the proxy must set them, the app should only accept the proxy's value.
5. **Enforce the allowlist at the load balancer too.** Proxy-level Host filtering (and only forwarding to permitted back-ends) stops routing-based SSRF and virtual-host brute forcing before they touch the app.
6. **Separate internal and public virtual hosts.** Never host internal-only admin apps on the same server/origin as public content; Host-based segregation is not an access control.

## Verification checklist for this codebase

1. **Grep for URL construction from request data.** Search for `req.headers.host`, `X-Forwarded-Host`, `request.host`, `base_url` derived from the request object, and templating that interpolates a host into emails; every hit is either config-backed or it is a finding.
2. **Test the reset flow with a rewritten Host.** Request a reset for a test account with `Host` and then `X-Forwarded-Host` set to a controlled domain; inspect the received email's link — the base URL must never change.
3. **Check duplicated/absolute-form requests.** Send two `Host` headers and an absolute-URI request line; the server must reject ambiguity, not pick one silently.
4. **Verify cache behavior.** Confirm cached pages contain no Host-derived absolute URLs, or that the cache varies on nothing Host-influenced.
5. **Regression-test the allowlist.** Add a test asserting a request with an unknown Host gets rejected/redirected — the class of bug resurfaces every time a new deployment domain or proxy hop is added.

## Sources

1. **PortSwigger Web Security Academy — HTTP Host header attacks.** https://portswigger.net/web-security/host-header (root cause, attack classes, prevention list).
2. **PortSwigger — Password reset poisoning.** https://portswigger.net/web-security/host-header/exploiting/password-reset-poisoning (step-by-step exploit, dangling markup, first documented 2013 by James Kettle).
