# Execution Network Egress Deny by Default

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Deny outbound network access from code-execution environments unless a task explicitly requires approved destinations.

## Validation

Attempt DNS, direct-IP, redirect, and alternate-protocol egress from generated code; verify unapproved traffic is blocked.

## Failure correction

Quarantine the environment, inspect outbound logs, rotate exposed secrets if necessary, and reduce the allowlist.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/190/final
- https://csrc.nist.gov/pubs/sp/800/218/final
