# VEX not-affected assertion evidence

**Issue:** A VEX `not_affected` statement can suppress remediation without evidence that the vulnerable code is absent, unreachable, or protected.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Bind each statement to product/component identifiers, versions, vulnerability ID, status, justification, impact statement, author, timestamp, and evidence. Use CISA-recommended status justifications consistently. Require technical ownership and independent review for customer-distributed statements. Reassess when code, dependencies, build flags, reachability, or vulnerability facts change. Publish corrections instead of silently replacing history.

## Verification

Reproduce component inventory and call-path/build evidence; test the claimed mitigation; validate VEX syntax in each distributed format; verify consumers match the exact product version.

## Gotchas

“Component present” does not automatically mean affected, and “not affected” is not permanent. A missing exploit is not evidence. VEX complements an SBOM; it does not replace one.

## Sources

- [CISA SBOM Resources Library: VEX minimum elements and justifications](https://www.cisa.gov/topics/cyber-threats-and-advisories/sbom/sbomresourceslibrary)
