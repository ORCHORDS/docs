# SSRF Defense for Agents That Fetch URLs

## Scope

Agents may browse links, import documents, inspect webhooks, or pass URLs to tools. This creates server-side request forgery (SSRF) risk: untrusted input can cause the service to reach internal control planes, cloud metadata endpoints, loopback services, or attacker-controlled redirect chains. The OWASP SSRF Prevention Cheat Sheet distinguishes cases where destinations can be allowlisted from cases requiring access to arbitrary external targets.

This article addresses the network-fetch boundary. Content prompt injection is a separate problem: a response can be network-safe yet contain hostile instructions. Conversely, content filtering cannot make an unsafe destination acceptable.

## Implementation workflow

Inventory every component that dereferences a URL, including browser tools, image loaders, document converters, webhook validators, preview generators, and model-provider features. Record who supplies the URL, supported schemes, redirect behavior, DNS resolver, proxy path, network identity, and reachable address ranges. Centralize fetching behind one hardened service rather than reproducing partial checks.

When destinations are known, maintain an allowlist of canonical schemes, hosts, ports, and path constraints. Resolve service identities through configuration rather than user input. When arbitrary internet access is required, parse with a standards-tested URL library, permit only needed schemes such as HTTPS, reject embedded credentials and ambiguous forms, and resolve the hostname through a controlled resolver.

Validate every resolved address against forbidden ranges before connecting. Cover IPv4, IPv6, loopback, link-local, private, multicast, unspecified, and environment-specific infrastructure networks. Pin the connection to an approved resolved address while preserving the validated hostname for TLS verification. Revalidate every redirect target and enforce a small redirect limit. Avoid automatic protocol switching.

## Controls

Enforce network egress policy independently of application validation. The fetcher should have no route to metadata services, cluster APIs, databases, or administrative networks. Use a proxy or firewall with destination policy and DNS logging. Require TLS verification; do not accept invalid certificates merely because content is “only for the model.”

Cap response bytes, decompressed bytes, redirects, connection time, total time, and concurrent fetches. Restrict methods to those required and strip caller-supplied hop-by-hop, authentication, forwarding, and cloud metadata headers. Do not forward user cookies or internal credentials. Validate content type and magic bytes before handing data to parsers, and isolate parsers for risky formats.

Defend against DNS rebinding by validating all returned addresses, connecting to the validated result, and avoiding a second uncontrolled resolution. Compare normalized hostnames carefully, including internationalized names and trailing dots. Prefer exact allowlist matches over substring or suffix mistakes.

## Validation evidence

Build automated cases for decimal, hexadecimal, octal, mixed, and IPv4-in-IPv6 address forms supported by relevant parsers; loopback and private ranges; user-info confusion; fragments; malformed ports; DNS names returning mixed public and private addresses; redirects to forbidden targets; excessive redirects; and DNS rebinding simulations. Include cloud and platform-specific reserved endpoints from the deployment threat model without contacting production metadata services.

Evidence should include the fetch inventory, egress rules, resolver configuration, URL parser version, forbidden-range tests, redirect captures, timeout and size-limit tests, and logs proving blocked attempts. Verify from the actual runtime network namespace, because a unit test cannot establish route isolation. Use controlled canary services to prove external retrieval still works without internal reachability.

## Failure handling

Reject invalid or forbidden destinations before connecting. Return a stable application error that does not disclose internal addresses, DNS answers, or firewall topology. Stop on redirect validation failure; never return the last internal response body. Rate-limit repeated denied requests and alert on patterns targeting metadata or control-plane ranges.

If an internal fetch occurs, disable the fetch capability or tighten egress immediately, preserve destination and request metadata without spreading response secrets, rotate credentials potentially exposed by the endpoint, and inspect subsequent tool actions. Fix both application validation and network policy, then add the exact path and equivalent encodings to regression tests.

## Canonical sources

- OWASP SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- IETF RFC 3986, URI Generic Syntax: https://www.rfc-editor.org/rfc/rfc3986
- IETF RFC 6890, Special-Purpose IP Address Registries: https://www.rfc-editor.org/rfc/rfc6890
