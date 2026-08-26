# Configuration drift reconciliation proof

**Issue:** A controller reports successful reconciliation while production remains different from reviewed desired state.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Lesson

Reconciliation is proven by observed state and behavior, not by a successful apply command.

## Controls

Version desired state; resolve generated defaults; identify authoritative fields; continuously compare normalized desired and observed state; classify benign, emergency, provider, and malicious drift; remediate through the source of truth; time-bound emergency changes; preserve actor and reason.

## Verification

Change a safe canary field out of band and prove detection, attribution, reconciliation, and alert closure. Validate behavior after convergence. Test unavailable APIs and partial applies.

## Gotchas

Naive diffs amplify ordering/default noise. Automatic reconciliation can undo incident containment. A green controller may lack read permissions or watch the wrong scope.

## Sources

- [NIST SP 800-218 SSDF](https://csrc.nist.gov/pubs/sp/800/218/final)
- [NIST CSF 2.0](https://www.nist.gov/publications/nist-cybersecurity-framework-csf-20)
