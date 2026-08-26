# ssrf-url-fetch-guard

**Issue:** The example project platform fetches user-supplied URLs (link previews, media imports, webhooks). Any endpoint that does this is a server-side request forgery (SSRF) surface: an attacker submits `http://169.254.169.254/latest/meta-data`, `http://127.0.0.1:6379/`, or a DNS name that resolves to an internal address, and your server happily fetches from inside the network perimeter. Naive guards fail in two well-documented ways: string checks on the URL miss alternate IP encodings and IPv6, and a hostname that resolves to a public IP at validation time can resolve to a private IP at connection time (DNS rebinding TOCTOU). The platform ships a single guard module that every outbound fetch of user-supplied URLs must go through: scheme allowlist, DNS resolve, private/reserved-range block, connect to the validated IP, and full re-validation on every redirect hop.

**Date:** 2026-08-15
**Repo:** example-org/example-repo (fork example-org/example-repo)
**Author:** ORCHORDS
**Status:** published

## Threat model

1. **The server is the pivot.** The attacker does not need network access to your internals — they need your fetcher to have it. SSRF turns a public "paste a URL" feature into a read/write probe of loopback services, cloud metadata endpoints, and RFC1918 infrastructure.
2. **Cloud metadata is the primary target.** `169.254.169.254` (AWS/GCP/Azure IMDS, with Azure's variant requiring the `Metadata: true` header) yields credentials that escalate SSRF into full account compromise; IMDSv2 and session-token requirements mitigate but must not be assumed.
3. **DNS rebinding is the standard bypass.** The attacker controls a DNS zone with a low TTL that alternates answers between a public IP (passes validation) and `127.0.0.1` (used at connect time). This is not theoretical — CVE-2026-73410 (Budibase REST connector) was exactly a rebinding bypass of an IP check, giving authenticated users access to internal services.
4. **Redirects are a second validation boundary.** A URL that validates cleanly and then 302s to `http://169.254.169.254/` defeats any guard that only checks the original URL. Every hop is a new user-controlled destination.

## The guard pipeline

1. **Parse with a real URL parser, then allowlist the scheme.** `new URL(input)` (never regex), then require `http:` or `https:` — this kills `file:`, `gopher:`-style schemes, and malformed input in one step. Reject embedded credentials (`user:pass@host`) and non-default ports where the use case has none.
2. **Reject literal IPs before resolving.** If the hostname is already an IP literal, run the range check immediately; this also catches `127.0.0.1`, `[::1]`, and IPv4-mapped IPv6 (`::ffff:127.0.0.1`) without any DNS dependency.
3. **Resolve DNS yourself, then check every answer.** Call the resolver directly (`dns.lookup(..., { all: true })` semantics) and range-check *all* returned addresses — a multi-answer response where only one record is public is a classic partial-check bypass.
4. **Connect to the validated IP, not the hostname.** Pin the resolved IP into the actual connection (custom dialer/agent that overrides DNS, or rewrite the URL to the IP and set the original `Host` header / SNI). This closes the rebinding window: there is no second resolution to poison.
5. **Never let the HTTP client re-resolve.** If the underlying stack performs its own DNS lookup after your validation, the TOCTOU gap is still open — the pin must reach the socket, which is why ready-made guards (e.g., `ssrf-agent` for Node's `request`, or a custom `HTTPAdapter` in Python `requests` that validates in `getaddrinfo`) are structured as connection-layer hooks rather than pre-checks.

## Blocked destination ranges

1. **IPv4 private and reserved.** `127.0.0.0/8` (loopback), `10.0.0.0/8` and `172.16.0.0/12` and `192.168.0.0/16` (RFC1918), `169.254.0.0/16` (link-local — includes every cloud metadata endpoint), `0.0.0.0/8` ("this network", often reachable as loopback), `100.64.0.0/10` (CGNAT — where many container/service meshes live), `192.0.2.0/24`/`198.51.100.0/24`/`203.0.113.0/24` (documentation), `198.18.0.0/15` (benchmarking), `224.0.0.0/4` and `240.0.0.0/4` (multicast/reserved).
2. **IPv6 equivalents.** `::1/128` (loopback), `fc00::/7` (ULA private), `fe80::/10` (link-local), `::ffff:0:0/96` (IPv4-mapped — decode and apply the IPv4 rules), plus `2001:db8::/32` (documentation).
3. **Blocks are cheap, allowlists are cheaper.** For fetchers that only ever need to reach a known set of partners (webhooks outbound), an explicit destination allowlist at the egress layer beats any IP blocklist — the range list is the fallback for genuinely open fetchers like link previews.
4. **Normalize before comparing.** Decode alternate encodings before the range check: decimal (`http://2130706433/` = 127.0.0.1), octal/hex components, and mixed forms all evade string matching but collapse to the same packed integer the CIDR check sees. Compare packed 32/128-bit integers against the ranges, never strings.

## Redirect handling (per-hop re-validation)

1. **Disable automatic redirect following.** `redirect: 'manual'` in fetch options — the moment the runtime follows redirects for you, the guard only ever saw the first URL and every subsequent hop is unvalidated.
2. **Re-run the entire guard for each hop.** On a 3xx: parse the `Location` header, re-check scheme, re-resolve DNS, re-check ranges, re-pin — the full pipeline, no shortcuts, because the redirect target is exactly as attacker-controlled as the original URL.
3. **Cap the chain.** Limit total hops (3–5), response size, and total time; redirect loops and chains that bounce between hosts to burn the guard's resolve budget are themselves an attack (and a DoS vector).
4. **Rebinding defense is per-hop resolution plus pinning, not caching.** Resolve fresh at each hop and connect to what you resolved; do not cache earlier answers as "known good" — a hostname that was safe on hop one may be poisoned by hop three.

## Testing the guard

1. **Unit-test the encodings.** A table of hostile inputs — `127.0.0.1`, `2130706433`, `0177.0.0.1`, `0x7f000001`, `[::1]`, `::ffff:127.0.0.1`, `localtest.me` (rebinds to 127.0.0.1), metadata IPs — each must be rejected; every bypass class in the wild started as an untested encoding.
2. **Test rebinding explicitly.** Use a rebinding service (or a fixture DNS zone with alternating answers) and assert the request fails — resolve-then-connect must be observably pinned, not just code-reviewed.
3. **Test redirect chains.** A fixture that 302s from a safe host to `169.254.169.254` must be blocked; also test double redirects that sandwich the bad hop in the middle.
4. **Test both failure orders.** The multi-answer DNS case (one public record, one private record) and the IPv4-mapped-in-v6 case both regress silently if someone "simplifies" the range check later.

## Gotchas

1. **Validation and connection in different layers reopens the gap.** A guard that returns a sanitized URL string, which is then passed to a stock HTTP client, is rebinding-vulnerable again — the pin has to live in the dial path.
2. **Pinning is necessary but not sufficient.** An attacker whose rebinding host fronts attacker-controlled infrastructure can still pass checks (see the Security StackExchange analysis of DNS-pinning limits); layer egress firewall rules and network policy under the application guard.
3. **Blocklists rot; new reserved ranges appear.** Track IANA special-purpose registries and re-audit the range table periodically — this is defense in depth behind an allowlist wherever possible.
4. **Secondary fetchers are where regressions hide.** The guard must be the only sanctioned path to `fetch()` for external URLs; lint for direct `fetch(userInput)` at review time, because every new "quick preview" feature re-opens the hole.

## Related

- `security/outbound-url-policy-ssrf-and-dns-rebinding-resistance.md` — policy-level summary
- `security/server-side-request-forgery-ssrf.md` — earlier generic pattern
- `security/open-redirect-prevention.md`
- OWASP SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- Palo Alto Networks — What Is DNS Rebinding: https://www.paloaltonetworks.com/cyberpedia/what-is-dns-rebinding
- SSRF DNS rebinding write-up (pinning mechanics): https://aydinnyunus.github.io/2026/03/14/ssrf-dns-rebinding-vulnerability/
- DNS-pinning limits (Security StackExchange): https://security.stackexchange.com/questions/14038/does-dns-pinning-protect-against-all-dns-rebinding-attacks
- Python requests rebinding fix pattern: https://joshua.hu/solving-fixing-interesting-problems-python-dns-rebindind-requests
