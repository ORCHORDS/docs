# Sandboxed Agent Code Execution

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Run agent-generated or agent-selected code inside an isolation boundary with explicit filesystem, process, network, and credential limits.

## Validation

Attempt unauthorized file access, network egress, and process spawning; verify the sandbox enforces configured boundaries.

## Failure correction

Terminate the sandbox, preserve forensic evidence, patch the isolation gap, and rotate any exposed credentials.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/190/final
- https://csrc.nist.gov/pubs/sp/800/218/final
