# Trusted Intermediary Header Override Review

## Purpose

Verify that HTTP header fields supplied by trusted intermediary layers cannot be spoofed or overridden by end users before application authorization, identity, routing, logging, or security decisions consume them.

## Source basis

OWASP ASVS 5.0.0 requirement v5.0.0-4.1.3 requires headers set by trusted intermediary layers, such as load balancers, proxies, or backend-for-frontend services, to be protected from end-user override. Examples include X-Real-IP, X-Forwarded-* and identity-related headers.

## Inputs

- ingress, proxy, gateway, and application architecture;
- list of headers trusted by downstream components;
- edge and origin configuration;
- representative application routes and security decisions that consume those headers.

## Procedure

1. **Inventory trusted headers.** Identify every header whose value is accepted from an intermediary as identity, client address, scheme, host, role, routing, tenant, or security context.
2. **Map the trust boundary.** Record which component is authorized to create or rewrite each header and which downstream service consumes it.
3. **Send client-supplied copies.** From the untrusted side of the boundary, supply the same header names with attacker-controlled values and verify the trusted intermediary removes or overwrites them.
4. **Test alternate spellings and duplicates.** Check duplicate header instances, common legacy variants, case variations, and forwarding chains that could influence parsing.
5. **Test direct-origin reachability.** Where an origin should only receive traffic through the trusted intermediary, verify a client cannot bypass the intermediary and set trusted headers directly.
6. **Review forwarding chains.** Confirm client-controlled portions of X-Forwarded-For or equivalent chains are distinguished from values added by trusted infrastructure.
7. **Check authorization use.** Any header involved in identity, role, tenant, or privilege decisions must be bound to authenticated trusted infrastructure rather than merely present.
8. **Check host/scheme use.** Ensure forwarded host and scheme values cannot be spoofed to influence redirects, link generation, cookie security, origin checks, or access controls.
9. **Review logs and monitoring.** Confirm spoofed client values cannot overwrite the authoritative security context recorded for investigation.
10. **Record exceptions.** Document any intentionally client-set header that resembles a trusted header and ensure downstream code clearly separates the two namespaces.

## Evidence

Record header name, trusted setter, downstream consumer, attempted client value, observed value at the application boundary, direct-origin test result, and remediation status.

## Completion criteria

The review is complete when every security-relevant intermediary header has a defined trusted setter, end-user attempts cannot control the authoritative value, and direct paths cannot bypass the intended trust boundary.

## Sources

- OWASP ASVS 5.0.0, V4.1 Generic Web Service Security: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x13-V4-API-and-Web-Service.md
- OWASP REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html

## Scope note

Header names alone do not establish trust. The deployment path and authenticated infrastructure boundary determine whether a value can be relied upon.
