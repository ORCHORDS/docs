# VEX status lifecycle and consumer verification

**Issue:** An SBOM scanner reports a vulnerable component, but teams either suppress the alert without evidence or treat every component match as immediately exploitable.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A vulnerability affects a component named in an SBOM. The product team says the vulnerability is not reachable, fixed downstream, or not present in the shipped build, while operations has no machine-readable, time-bounded evidence to decide whether to defer remediation.

## Root cause

An SBOM identifies composition; it does not by itself establish whether a specific vulnerability affects a particular product version. Vulnerability Exploitability eXchange (VEX) information lets a producer express a product-specific status, but a status assertion is only useful when the consumer can bind it to the exact product, component, vulnerability, evidence, and revision.

**Sources:**

- [CISA SBOM resources library — VEX materials](https://www.cisa.gov/topics/cyber-threats-and-advisories/sbom/sbomresourceslibrary)
- [CISA Known Exploited Vulnerabilities catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)

## Fix

Operate VEX as an evidence-backed lifecycle, not as a permanent exception list:

- create a record for the exact product name/version, component identity, vulnerability identifier, status, status justification, author, timestamp, and review/expiry date;
- use a precise status: affected, not affected, fixed, or under investigation; do not use ambiguous free text as a substitute;
- attach the smallest reproducible evidence that supports the assertion, such as build provenance, feature configuration, reachability analysis, patched component version, or test result;
- sign or otherwise integrity-protect published VEX material and distribute it alongside the SBOM or release metadata;
- require a second review for `not affected` claims and automatically reopen them when the product version, component version, deployment configuration, or vulnerability analysis changes;
- prioritize active exploitation independently: a KEV match requires explicit risk-owner review even when a preliminary VEX claim exists;
- make consumers fail closed on identity mismatch, stale metadata, unknown status, missing justification, or an unverifiable issuer.

## Verification

- **Binding:** the VEX record references the exact released artifact and component identity, not only a project name.
- **Evidence:** a reviewer can reproduce the stated affected/not-affected conclusion from retained evidence.
- **Freshness:** an expired or superseded VEX assertion cannot silently suppress a new scan result.
- **Integrity:** changing the VEX document or substituting it for another product is detected.
- **Consumer behavior:** unknown, malformed, and identity-mismatched VEX records remain visible for remediation.
- **Operations:** a KEV-listed vulnerability produces an owned decision and due date rather than an unattended suppression.

## Gotchas

- “Not affected” is not the same as “no exploit has been observed.” State the technical justification.
- A VEX statement does not replace patching when the product is affected; it communicates analysis and status.
- Component names are often ambiguous. Prefer stable package/component identifiers and release-bound provenance.
- Do not publish internal topology, exploit steps, credentials, or customer data as VEX evidence.

## Related

- `security/sbom-vulnerability-scanning.md`
- `issues/sbom-supply-chain-2026.md`
- `security/exploit-prioritized-vulnerability-triage.md`
- `github/artifact-attestations.md`
