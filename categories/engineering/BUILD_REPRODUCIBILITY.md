---
title: "Build Reproducibility and Determinism"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Build Reproducibility and Determinism

## Purpose

Increase confidence that released artifacts can be traced to intended source and build inputs.

## Requirements

Release-critical builds SHOULD minimize undeclared inputs, pin or record material tool/dependency versions, preserve build metadata and provenance where justified by risk, isolate unnecessary credentials, and make build steps reviewable.

Exact byte-for-byte reproducibility may not be practical for every artifact. Where full reproducibility is not achieved, document the remaining nondeterministic inputs and use integrity controls that still support traceability and investigation.

This policy complements [Software Supply Chain](SOFTWARE_SUPPLY_CHAIN.md).
