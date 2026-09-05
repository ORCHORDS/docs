# Command Canonicalization Before Policy

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Normalize command structure and execution targets before applying policy so quoting, encoding, wrappers, or path aliases do not bypass restrictions.

## Validation

Test equivalent commands expressed through alternate quoting, paths, environment expansion, and wrappers; verify policy reaches the same decision.

## Failure correction

Block the bypass representation, canonicalize earlier in the pipeline, and add equivalent forms to tests.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/218/final
- https://genai.owasp.org/resource/agent-control-standard-acs/
