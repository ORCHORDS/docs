# Code Generation and Execution Boundary

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Separate generating code from executing it. Code output should cross an explicit review, policy, or sandbox boundary before it can create side effects.

## Validation

Generate code that includes hidden commands, dependency installs, and external calls; verify generation alone cannot execute it.

## Failure correction

Cancel execution, inspect the generated artifact, repair the boundary, and require re-approval after modifications.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/190/final
- https://csrc.nist.gov/pubs/sp/800/218/final
