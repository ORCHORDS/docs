---
title: "Toolchain Lifecycle Governance"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-23"
review-cycle: "90 days"
next-review: "2026-11-21"
---

# Toolchain Lifecycle Governance

## Purpose

Keep release-critical compilers, runtimes, package managers, build tools, and automation dependencies supportable and reviewable.

## Requirements

Material toolchains SHOULD have an accountable owner, supported-version strategy, upgrade triggers, compatibility expectations, and retirement plan for obsolete versions.

Toolchain upgrades should be tested for build, test, packaging, security, and reproducibility effects before broad adoption.

Unsupported tools should not remain release-critical by default merely because migration is inconvenient.
