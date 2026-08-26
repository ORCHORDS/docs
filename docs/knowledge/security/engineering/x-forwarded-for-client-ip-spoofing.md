# x-forwarded-for-client-ip-spoofing

**Issue:** Almost every modern deployment terminates TLS at a load balancer or CDN and forwards requests to the application with the original client address in the X-Forwarded-For header. The application then reads that header to obtain "the client IP" for rate limiting, IP allowlists, audit logs, geo-decisions, and fraud scoring. The header is trivially forgeable: any client can send its own X-Forwarded-For value, and naive implementations that take the first entry of the list — or trust the header from any source — let attackers bypass IP-based bans, dodge rate limits, forge audit trails, and defeat admin allowlists. MDN's guidance is blunt: security-relevant use of X-Forwarded-For must rely only on addresses appended by proxies you operate. Because the header is appended hop by hop, the trust question is about position in the chain, not the header's presence, and getting it wrong silently produces attacker-controlled "identity" data used in security decisions.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Trust Problem

1. **Append-only chain semantics.** Each proxy appends the address it saw to X-Forwarded-For, producing a comma-separated list like client, cdn-edge, internal-lb. Only the right-most entries are trustworthy because they were written by your own infrastructure; the left-most entries are attacker-supplied strings.
2. **First-entry fallacy.** Parsing the first element is the most common and worst mistake: it is exactly the value the client controls. The safe direction is right-to-left, skipping known proxy addresses until the first unknown IP is reached.
3. **Any-source trust is equivalent to no trust.** If the application honors X-Forwarded-For regardless of the TCP peer, an attacker bypassing the edge (direct-to-origin, misconfigured DNS, or an open internal route) injects a fully forged chain.
4. **Sibling headers have the same weakness.** X-Real-IP, CF-Connecting-IP, True-Client-IP, Forwarded (RFC 7239), and X-Forwarded-Proto all follow the same model: trustworthy only when set or overwritten by a proxy you control.

## Spoofing Attack Patterns

1. **Rate-limit evasion.** Rotating a forged X-Forwarded-For value per request makes per-IP counters useless for credential stuffing, scraping, or OTP guessing; every request appears to come from a fresh address.
2. **Allowlist bypass.** Internal admin panels or debug endpoints gated on source IP accept the attack when they trust a client-supplied header claiming an approved address such as an office egress IP or 127.0.0.1.
3. **Audit-log poisoning.** Security and compliance logs that record the header value record attacker-chosen strings, contaminating incident forensics and enabling false-flag attribution.
4. **Cache and geo manipulation.** Edge rules that vary cache behavior or content by geography can be nudged by forged region hints derived from the header, compounding into cache key inconsistencies.
5. **Ban evasion.** Blocking the forged address blacklists an innocent third party while the attacker continues unhindered — turning the defense into a denial-of-service against bystanders.

## Correct Proxy Chain Parsing

1. **Start from the connection, not the header.** The only intrinsically known address is the TCP peer of the application server. Work backward: if the peer is a trusted proxy, accept exactly one appended address from it, then repeat for the next trusted proxy.
2. **Maintain an explicit trusted-proxy list.** Express it as infrastructure data (internal CIDRs, CDN ranges) and fail closed — an untrusted peer means the header is ignored entirely and the peer address itself is used.
3. **Use recursive real-IP resolution.** nginx's ngx_http_realip_module with real_ip_recursive on and set_real_ip_from listing your proxies implements the right-to-left walk correctly; Node's express-rate-limit and Go's handlers have equivalent trusted-proxy settings that must be configured explicitly.
4. **Normalize and validate.** Entries must parse as IPv4 or IPv6 literals; reject chains containing malformed entries rather than skipping them, to prevent parser-differential confusion between edge and app.
5. **Prefer PROXY protocol where available.** For internal hops, the PROXY protocol carries connection metadata outside the HTTP headers, removing the ambiguity entirely.

## Hardening Application and Infrastructure

1. **Strip inbound forwarding headers at the edge.** The first trusted proxy should overwrite X-Forwarded-For with the connection address rather than appending to a client-supplied chain, so client-forged entries never survive into the interior.
2. **Bind security decisions to authenticated identity first.** IP-based controls are a backstop; rate limits and access rules should key on user, session, or API-key identity, with IP as a coarse secondary signal.
3. **Keep origin unreachable except from the proxy tier.** Firewall rules, private networking, and mutual TLS between CDN and origin deny attackers the direct-to-origin path that makes header forgery decisive.
4. **Record both values in audit logs.** Log the derived client IP and the raw header separately, so incident responders can detect chains that contain unexpected untrusted hops.
5. **Standardize one helper.** A single, tested getClientIp function (or framework middleware) used by every service prevents each team from re-implementing the parsing and introducing the first-entry bug anew.

## Testing and Monitoring

1. **Forge tests in CI.** Send requests with hostile X-Forwarded-For values through the real edge path and assert that rate limits, bans, and audit entries use the true source address, not the forged one.
2. **Direct-to-origin probing.** From an unprivileged network, verify origin endpoints reject or ignore forwarding headers when the peer is not a listed proxy.
3. **Anomaly alerts on chains.** Alert when X-Forwarded-For contains more entries than the expected proxy hop count, or when the resolved client IP jumps between impossible geographies mid-session.
4. **Review framework defaults.** Express (trust proxy), Django (X_FORWARDED_FOR settings), and similar toggles change behavior silently on upgrade; pin them explicitly in configuration and test after dependency bumps.
