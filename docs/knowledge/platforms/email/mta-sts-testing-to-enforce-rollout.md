# MTA-STS Testing-to-Enforce Rollout

**Issue:** Publishing an incorrect enforcing MTA-STS policy can block legitimate inbound mail, while remaining in testing mode provides no mandatory protection.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Serve the policy over valid HTTPS at the standardized host/path and publish the discovery TXT record with a monotonically changed policy ID. Begin with `mode: testing`, exact current MX patterns, and a short but operationally useful `max_age`. Publish TLS-RPT and observe every legitimate sender/MX path.

Fix certificate chains, hostname coverage, routing, and stale MX records before switching to `enforce`. Increase max age gradually after stable reporting. Automate tests that every advertised MX matches the policy and presents a valid certificate before DNS or mail-routing changes merge.

For rollback, remember cached policies remain active until expiry. RFC 8461 describes publishing `mode:none` with a short max age and changing the TXT ID; do not simply delete endpoints.

## Verification

Test policy fetch, content type, TLS certificate, redirects, TXT lookup, all MX patterns, backup MX, IPv4/IPv6, certificate rotation, CDN outage, testing failure reports, enforcement rejection, and cached old policy. Run the preflight from external resolvers/networks.

## Gotchas

Testing mode reports but does not require delivery failure. Sender adoption varies. Long max age improves downgrade resistance but increases recovery time from mistakes. MTA-STS protects transport policy, not message authenticity.

## Sources

- [RFC 8461: MTA-STS](https://www.rfc-editor.org/rfc/rfc8461.html)
- [RFC 8460: SMTP TLS Reporting](https://www.rfc-editor.org/rfc/rfc8460.html)
