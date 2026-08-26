# Control evidence freshness and invalidation

**Issue:** Evidence remains marked current after the code, configuration, owner, environment, or external requirement it proved has changed.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Lesson

Evidence freshness is event-driven as well as time-driven. A recent screenshot can be weak; older reproducible evidence may remain strong only if its subject and assumptions are unchanged.

## Evidence contract

Record claim, scope, subject identity/version, collection method, collector, timestamp, source, digest, environment, dependencies, validity window, invalidation events, confidentiality, and reviewer.

## Invalidation triggers

- code/configuration/build or infrastructure change;
- identity, ownership, or privilege change;
- tool/rule/framework version change;
- new threat or vulnerability information;
- evidence-source failure;
- exception or certificate expiry;
- system boundary, data classification, vendor, or jurisdiction change.

## Controls

Generate evidence from automated read-only checks where practical. Link each artifact to a control claim and immutable subject. Recollect after triggers, not just before audits. Alert on expired evidence and block claims that have no current support.

## Verification

Change a canary control and confirm dependent evidence becomes stale. Reproduce a sample from instructions. Verify digests, timestamps, source authorization, and that sensitive evidence access is logged.

## Gotchas

Continuous collection can continuously preserve the wrong signal. A dashboard screenshot is not source data. Replacing old evidence must not destroy historical assessment records. Fresh evidence cannot rescue an incorrectly scoped claim.

## Sources

- [NIST SP 800-171Ar3 assessment procedures](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/800-171Ar3/NIST.SP.800-171Ar3.html)
- [NIST SP 800-218 SSDF](https://csrc.nist.gov/pubs/sp/800/218/final)
