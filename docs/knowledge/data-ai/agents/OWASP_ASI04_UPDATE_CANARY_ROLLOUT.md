# Agent Component Update Canary Rollout

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Roll out high-impact model, tool, policy, and orchestration updates to a constrained canary population before fleet-wide adoption.

## Validation

Inject a deliberately incompatible canary update and verify automated promotion stops on defined health or security signals.

## Failure correction

Halt promotion, roll back to the last verified artifact, and add the failure signature to release gates.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://csrc.nist.gov/pubs/sp/800/218/final
