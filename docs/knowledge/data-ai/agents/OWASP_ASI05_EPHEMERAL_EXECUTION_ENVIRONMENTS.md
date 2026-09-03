# Ephemeral Execution Environments

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Prefer disposable execution environments rebuilt from a trusted image and destroyed after the task, minimizing persistence of attacker-controlled state.

## Validation

Write persistence artifacts and start a new task environment; verify previous task state is absent unless explicitly persisted through an approved channel.

## Failure correction

Destroy the contaminated environment, rebuild from the trusted image, and investigate any state that escaped the lifecycle boundary.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/190/final
- https://csrc.nist.gov/pubs/sp/800/218/final
