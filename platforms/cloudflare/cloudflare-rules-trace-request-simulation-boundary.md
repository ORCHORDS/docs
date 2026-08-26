# Cloudflare Rules Trace request-simulation boundary

**Issue:** A successful Cloudflare Trace is treated as proof of what happened to a production request even though Trace simulates a request, omits unsupported products, and does not show some automatic rule bypasses.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Decision

Use Trace to test a proposed HTTP/S request against current Cloudflare configuration and inspect rule evaluation order. Use production logs, Log Explorer, and origin evidence to establish what actually happened. Do not substitute one evidence type for the other.

## Controls

- Record the account, zone, hostname, method, URL, headers, cookies, body, source location, and configuration revision used for every trace.
- Run positive, negative, and boundary cases for each rule expression.
- Compare matched steps, actions, and evaluation order with the intended policy.
- Repeat the case with a real synthetic request when a safe test endpoint exists, and correlate its Ray ID with production logs.
- Maintain a coverage exception for products Trace does not expose, including Spectrum, Data Localization Suite hostnames, legacy rules, Load Balancing, IP Access rules, legacy rate limiting and WAF rules, and content security rules.
- Treat absence from trace output as unknown when an automatic operational bypass could apply.
- Limit API credentials to `Allow Request Tracer Read`; prefer scoped API tokens over a Global API Key.

## Verification

For each high-risk ruleset, preserve the trace inputs and result, then issue an equivalent controlled request and compare the observed action in logs. Include a deliberately matching request, a near miss, a non-proxied hostname case, and an unsupported-feature case. Fail rollout when simulated and observed behavior diverge without an approved explanation.

## Gotchas

Trace is Beta and available only to Administrator or Super Administrator roles. It can return the configuration that would apply even when the tested hostname is not proxied. Disabled product rules are not evaluated. Automatic bypasses used for operational reasons, such as certificate-validation paths, do not appear in trace output.

## Official sources

- [Cloudflare Trace overview](https://developers.cloudflare.com/rules/trace-request/)
- [Cloudflare Trace limitations](https://developers.cloudflare.com/rules/trace-request/limitations/)
- [Cloudflare Rules Trace API](https://developers.cloudflare.com/api/resources/request_tracers/subresources/traces/methods/create/)
