# Unsupported Internet-Facing Technology Needs an Exit Plan

**Issue:** An end-of-life or unsupported internet-facing product remains in service indefinitely behind compensating controls because replacement has no owner or deadline.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's Internet Exposure Reduction Guidance recommends keeping exposed systems current on security patches and replacing software or devices that no longer receive security support. Once support ends, permanent public exposure creates a growing maintenance problem that cannot be solved by waiting for future vendor fixes that will not arrive.

## Engineering rule

- Verify support status from an authoritative supplier or lifecycle source.
- Remove unnecessary public exposure immediately when an unsupported asset is discovered.
- Give any unsupported asset that must temporarily remain exposed a named replacement or upgrade owner and target date.
- Use compensating controls as time-bounded risk reduction, not as an indefinite substitute for supported technology.
- Reassess public exposure, patch state, and replacement progress together.

## Verification

- Sample internet-facing assets and verify both patch state and supplier support status.
- Confirm every unsupported exposed asset has a documented remove, replace, or upgrade decision.
- Check that temporary exceptions expire or return for review rather than silently becoming permanent.

## Official source

- CISA, Internet Exposure Reduction Guidance, published June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
