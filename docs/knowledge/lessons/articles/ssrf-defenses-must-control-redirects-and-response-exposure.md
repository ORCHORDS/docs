# SSRF Defenses Must Control Redirects and Response Exposure

**Issue:** Initial URL validation succeeds, but the HTTP client automatically follows redirects or returns the fetched internal response directly to the caller.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API7:2023 recommends disabling HTTP redirections for SSRF-prone fetchers and avoiding raw response forwarding to clients. Validating only the first URL can be undermined if a redirect changes the actual destination, while reflecting fetched content can turn an SSRF primitive into direct information disclosure.

## Engineering rule

- Disable automatic redirects unless the business requirement explicitly needs them.
- If redirects are required, re-validate every destination before following it.
- Apply the same destination, scheme, port, and network restrictions after each redirect.
- Do not expose arbitrary upstream response bodies, headers, or timing details to the caller.
- Bound fetch time and response size so rejected or hostile destinations cannot consume unlimited resources.

## Verification

- Serve a safe initial URL that redirects to a disallowed destination and confirm the client refuses the transition.
- Verify blocked internal-response content never reaches the external caller.
- Test redirect chains rather than only one-hop redirects where the client supports them.

## Official source

- OWASP API7:2023 Server Side Request Forgery: https://owasp.org/API-Security/editions/2023/en/0xa7-server-side-request-forgery/
