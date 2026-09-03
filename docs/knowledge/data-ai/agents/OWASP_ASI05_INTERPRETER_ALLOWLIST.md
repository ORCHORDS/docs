# Interpreter and Runtime Allowlist

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Permit only reviewed interpreters, compilers, package managers, and execution runtimes needed for the task rather than inheriting every host capability.

## Validation

Invoke unapproved runtimes directly and through wrapper scripts; verify the execution broker denies them.

## Failure correction

Remove the runtime from the image or policy path, rebuild from a trusted base, and add the invocation to regression tests.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/190/final
- https://csrc.nist.gov/pubs/sp/800/218/final
