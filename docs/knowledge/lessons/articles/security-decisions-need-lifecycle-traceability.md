# Security Decisions Need Lifecycle Traceability

**Issue:** Security requirements, threat-model findings, risk acceptances, and design exceptions are discussed during development but disappear into meeting notes or individual memory once the release ships.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SSDF v1.1 task PW.1.2 calls for tracking and maintaining software security requirements, risks, and design decisions. A decision that cannot be traced later cannot be reliably maintained, verified, reconsidered, or explained after the system or threat context changes.

## Engineering rule

- Record applicable security requirements in a maintained system with accountable ownership.
- Link material security risks to an explicit disposition or mitigation.
- Preserve rationale for security-relevant design decisions and approved exceptions.
- Link requirements and risk responses to implementation or verification evidence where required by the SDLC.
- Revisit accepted risks and exceptions when architecture, threats, dependencies, or business context materially change.
- Keep decision records accessible for maintenance, incident response, audits, and future redesign.

## Verification

- Sample one security requirement and trace it through risk/design decision, implementation or mitigation, and verification evidence.
- Sample an approved exception and confirm its rationale, owner, and current review state are still available.
- Change a relevant assumption in a test scenario and confirm the affected security decision is discoverable for re-evaluation.

## Official sources

- NIST SP 800-218, Secure Software Development Framework (SSDF) Version 1.1: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SSDF project page — v1.1 addition PW.1.2: https://csrc.nist.gov/projects/ssdf
