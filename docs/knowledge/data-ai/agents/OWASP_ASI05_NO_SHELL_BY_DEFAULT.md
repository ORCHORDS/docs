# No Shell by Default

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Do not expose general-purpose shell execution to agents unless the task class explicitly requires it and stronger isolation controls are present.

## Validation

Ask ordinary agents to execute commands through aliases, scripts, and indirect tool paths; verify shell capability is absent or denied.

## Failure correction

Remove broad execution tools, invalidate cached capabilities, and review tasks that invoked them unexpectedly.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/190/final
- https://csrc.nist.gov/pubs/sp/800/218/final
