---
title: "Open Source and Dependency Policy"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Open Source and Dependency Policy

## Purpose

Govern third-party code and packages as part of the software supply chain.

## Requirements

Dependencies should have a defined purpose, acceptable license, maintained
source, reasonable security posture, and compatible release/support model.

Before adopting a material dependency, consider:

- provenance and authoritative source;
- maintainer and project health;
- release cadence and update path;
- known vulnerabilities and security reporting;
- transitive dependencies;
- license obligations;
- build/install behavior and privileged hooks;
- replacement cost and abandonment risk.

## Version control

Prefer reproducible dependency declarations and lockfiles where supported.
Updates are reviewed and tested according to risk. Automated dependency changes
remain subject to normal review and verification.

## Removal

Unused, abandoned, compromised, or unjustifiably risky dependencies should be
removed or replaced within a risk-appropriate timeframe.

## Supply-chain relationship

See [Software Supply Chain](./SOFTWARE_SUPPLY_CHAIN.md) and
[Third-party Risk](../third-party/THIRD_PARTY_RISK_MANAGEMENT.md).
