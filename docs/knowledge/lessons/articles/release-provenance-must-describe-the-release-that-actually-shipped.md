# Release Provenance Must Describe the Release That Actually Shipped

**Issue:** A product has a component inventory or SBOM, but it is generated infrequently or detached from the exact release artifact, so responders cannot trust it to describe what customers actually received.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SSDF v1.1 task PS.3.2 adds collecting and sharing provenance data for components of software releases. Provenance is useful only when it remains associated with the release it describes and is refreshed when components change.

## Engineering rule

- Associate provenance/component data with a specific release or artifact, not only a product family.
- Regenerate or update provenance when release components change.
- Protect provenance integrity according to the release-evidence model.
- Make provenance available to internal vulnerability-response and operations teams that need it.
- Define how acquirers/customers receive provenance when external sharing is part of product policy.
- Preserve provenance long enough to support investigation of supported releases.

## Verification

- Select a shipped release and reconcile its provenance record against resolved dependencies/build inputs.
- Change a component in a test release and confirm the provenance evidence changes with it.
- Verify responders can retrieve the provenance for a specific supported release without reconstructing it from memory.

## Official sources

- NIST SP 800-218, Secure Software Development Framework (SSDF) Version 1.1: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SSDF project page — v1.1 addition PS.3.2: https://csrc.nist.gov/projects/ssdf
