# DNSSEC negative trust-anchor expiry

**Issue:** A DNSSEC Negative Trust Anchor (NTA) temporarily disables validation for a failing domain so users can reach it despite a DNSSEC operational error. Leaving that exception in place after the zone is repaired converts an availability workaround into a persistent downgrade that accepts data without the expected chain of trust.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use an NTA only after confirming a DNSSEC validation failure, its affected name and scope, the operational owner, and the risk tradeoff between outage and validation bypass.
- Require two-person approval or an emergency record with incident ID, evidence, resolver fleet, exact domain, start time, maximum lifetime, and accountable owner.
- Scope the anchor as narrowly as the resolver supports; do not disable DNSSEC globally or at an unnecessarily high ancestor.
- Set automatic expiry. RFC 7646 says the lifetime should not exceed one week.
- Periodically retry validation while the NTA is active and remove it as soon as all relevant authoritative service validates successfully.
- Disclose the temporary downgrade to affected operators and applications where appropriate.
- Propagate addition and removal consistently across resolver instances, views, regions, and failover systems.
- Monitor NTA count, age, queries affected, validation result, and overdue remediation.

## Implementation and tests

Automate a state machine from observed SERVFAIL and DNSSEC evidence through approval, time-bounded installation, periodic probes, early removal, hard expiry, and post-removal validation. Query all discoverable authoritative servers where possible because anycast or load balancing can hide an inconsistent instance.

Test a broken signature, expired signature, DS mismatch, partial authoritative repair, unavailable authority, resolver restart, configuration rollback, clock error, fleet partition, and the hard maximum lifetime. Assert the NTA disappears automatically even when monitoring or the incident system fails.

## Gotchas

An NTA is local resolver policy, not a repair to the authoritative zone. Cached answers and negative data can affect observations around add or removal. Successful insecure resolution during the exception does not prove authenticity.

RFC 7646 is Informational operational guidance. Resolver syntax and early-removal behavior vary; verify the deployed implementation and organizational policy.

## Official sources

- [RFC 7646: Definition and Use of DNSSEC Negative Trust Anchors](https://www.rfc-editor.org/rfc/rfc7646.html)
- [RFC Editor: RFC 7646 status](https://www.rfc-editor.org/info/rfc7646/)
