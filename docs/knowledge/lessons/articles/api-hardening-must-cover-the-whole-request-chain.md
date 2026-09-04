# API Hardening Must Cover the Whole Request Chain

**Issue:** The application server is hardened, but proxies, load balancers, gateways, cloud permissions, CORS, TLS, or enabled HTTP methods differ across environments and create an exploitable configuration gap.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API8:2023 treats security misconfiguration as a stack-wide risk. A secure application configuration is insufficient when another component in the HTTP chain interprets requests differently or exposes a weaker transport, method, header, permission, or service configuration.

## Engineering rule

- Maintain a repeatable hardening baseline for every layer that receives, forwards, terminates, or authorizes API traffic.
- Disable unnecessary methods, services, features, and legacy options.
- Enforce TLS for client, upstream, and downstream API communication where applicable.
- Review CORS and security headers for browser-consumed APIs.
- Test request parsing consistently across gateways, proxies, and application servers.

## Verification

- Compare deployed configuration against the hardening baseline in every environment.
- Send ambiguous or unexpected method/content-type requests through the full request chain and compare interpretation at each layer.
- Verify infrastructure defaults do not silently re-enable disabled behavior after upgrades or redeployments.

## Official source

- OWASP API8:2023 Security Misconfiguration: https://owasp.org/API-Security/editions/2023/en/0xa8-security-misconfiguration/
