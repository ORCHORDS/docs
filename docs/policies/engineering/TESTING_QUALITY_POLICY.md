---
title: "Testing and Quality Policy"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Testing and Quality Policy

## Purpose

Define risk-based verification expectations without prescribing a particular
language, framework, or product architecture.

## Test strategy

Use the smallest reliable test that can detect the failure:

- unit tests for local logic;
- integration tests for boundaries and dependencies;
- contract tests for interfaces;
- end-to-end tests for critical user journeys;
- security tests for abuse cases and security requirements;
- performance or resilience tests where failure would materially affect users;
- accessibility tests for public user interfaces.

## Risk-based depth

Testing depth increases with:

- blast radius;
- irreversibility;
- data sensitivity;
- privilege;
- concurrency;
- migration complexity;
- external dependency changes;
- historical defect rate.

## Flaky tests

Flaky tests are defects. Repeatedly retrying a flaky test without ownership
hides risk. Quarantine only when necessary, with an owner and expiry.

## Production defects

Material defects should produce a regression test or an explicit reason why a
test is not practical.

## Quality signals

Track trends such as escaped defects, rollback rate, change failure rate, test
reliability, mean time to restore, vulnerability aging, and recurring incident
causes. Metrics should drive learning rather than individual performance
ranking.
