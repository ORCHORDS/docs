# Outbound URL policy: SSRF and DNS-rebinding resistance

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)

## Problem

A feature that fetches a caller-supplied URL can be turned into a network pivot toward internal services. Validating only the original hostname is insufficient when DNS answers change between validation and connection.

## Practice

- Prefer a fixed allowlist of approved origins and routes over accepting arbitrary URLs.
- Parse with a standards-compliant URL parser; require HTTPS where the use case allows it and reject credentials, ambiguous encodings, and unsupported schemes.
- Resolve the hostname, reject loopback, link-local, private, multicast, and otherwise reserved destinations according to policy, then connect using the validated address or revalidate immediately before connection.
- Disable redirects by default. If redirects are required, validate every hop with the same policy and limit count, size, and time.
- Block access to cloud metadata and control-plane endpoints at the network layer as a defense in depth.
- Use a dedicated egress proxy or network policy with a deny-by-default destination policy for high-risk fetchers.

## Verification

1. Attempt loopback, private-address, link-local, encoded-address, and cloud-metadata targets.
2. Attempt a hostname whose answer changes from a public address to a private address; the request must fail.
3. Attempt redirect chains that end at a prohibited destination; each must be rejected.
4. Confirm the egress layer blocks a bypass even if application validation regresses.

## Failure modes

- Regex-only URL checks misunderstand parsers and alternate address representations.
- Following redirects without revalidation bypasses the initial policy.
- Application-only controls leave metadata services reachable after one missed code path.

## Related

- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
