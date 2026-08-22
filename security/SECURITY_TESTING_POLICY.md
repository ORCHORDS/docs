---
title: "Security Testing Policy"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Security Testing Policy

## Purpose

Define risk-based security verification across software, configuration, and
operational controls.

## Test selection

Testing depth should reflect exposure and impact. Appropriate methods MAY
include:

- code and configuration review;
- static analysis;
- dependency and secret scanning;
- dynamic application testing;
- abuse-case or adversarial testing;
- infrastructure configuration assessment;
- penetration testing by qualified personnel;
- recovery and control-failure exercises.

No single tool or test establishes that a system is secure.

## Rules

Testing MUST be authorized, scoped, and conducted to avoid unnecessary harm.
Production-impacting techniques require explicit approval and safeguards.

Findings must be triaged by exploitability, exposure, business impact, data
impact, and compensating controls rather than tool severity alone.

## Retest

Material remediation should be verified. Closure based only on a ticket status
is insufficient where technical retest is practical.
