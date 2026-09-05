# Execution Resource Limits

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Bound CPU, memory, process count, disk, execution time, and output volume for agent-controlled code so accidental or malicious execution cannot exhaust the host.

## Validation

Trigger each configured limit with a controlled workload and verify the environment terminates or throttles predictably.

## Failure correction

Kill the runaway workload, reclaim resources, and adjust limits or isolation if collateral impact occurred.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/190/final
- https://csrc.nist.gov/pubs/sp/800/218/final
