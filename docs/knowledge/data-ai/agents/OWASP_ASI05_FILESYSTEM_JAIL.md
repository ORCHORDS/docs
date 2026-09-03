# Filesystem Jail for Agent Execution

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Expose only task-required filesystem paths to code-executing agents and keep sensitive host or control-plane data outside the writable view.

## Validation

Attempt reads and writes above, beside, and through links around the allowed workspace; verify access is contained.

## Failure correction

Stop the execution environment, restore affected files, and tighten mounts, path resolution, or link handling.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/190/final
- https://csrc.nist.gov/pubs/sp/800/218/final
