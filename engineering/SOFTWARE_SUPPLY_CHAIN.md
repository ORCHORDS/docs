---
title: "Software Supply Chain Policy"
owner: "Security and Engineering Leads"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Software Supply Chain Policy

## Purpose

Reduce risk introduced by dependencies, build systems, automation, and
released artifacts.

## Dependency management

- Use supported dependencies from trustworthy sources.
- Record direct dependencies in machine-readable manifests where practical.
- Pin or lock versions when reproducibility and integrity benefit from it.
- Review security advisories and update vulnerable dependencies based on risk.
- Remove unused dependencies.
- Evaluate high-impact new dependencies for maintenance health, provenance,
  licensing, privilege, and transitive risk.

## Build integrity

Build workflows should be isolated from unnecessary credentials and privileges.
Release-critical automation should use immutable inputs where practical.

SLSA 1.2 is the current approved SLSA specification used as a reference for
source and build provenance maturity.

## SBOM and provenance

For distributed software or high-impact artifacts, generate an SBOM and
provenance when these materially improve vulnerability response, customer
assurance, or release integrity.

Do not claim a SLSA level unless the stated requirements are actually
satisfied and verifiable.

## Repository posture

The OpenSSF OSPS Baseline and Scorecard concepts may be used to evaluate
repository controls such as branch protection, token permissions, dependency
updates, security testing, and pinned automation.

## Third-party compromise

A suspected dependency or build-tool compromise is handled as a security
incident. Containment may include pausing releases, revoking credentials,
pinning/rolling back dependencies, rebuilding from trusted source, and
notifying affected parties.
