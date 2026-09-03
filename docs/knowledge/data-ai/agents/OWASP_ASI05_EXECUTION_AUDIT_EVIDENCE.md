# Agent Execution Audit Evidence

## Purpose

Control profile for **OWASP ASI05: Unexpected Code Execution (RCE)**.

## Control

Record code artifact identity, runtime image, executing principal, task, policy decision, start/end status, and bounded outputs for privileged agent execution.

## Validation

Sample successful, denied, timed-out, and crashed executions and verify evidence supports reconstruction without storing unnecessary secrets.

## Failure correction

Repair missing telemetry at the execution broker, preserve substitute evidence, and retest all terminal states.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://csrc.nist.gov/pubs/sp/800/190/final
- https://genai.owasp.org/resource/agent-control-standard-acs/
