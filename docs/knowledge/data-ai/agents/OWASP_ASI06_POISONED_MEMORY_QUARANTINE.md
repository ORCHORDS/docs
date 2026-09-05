# Poisoned Memory Quarantine

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Provide a quarantine state that removes suspected memory from retrieval without immediately destroying evidence needed for investigation.

## Validation

Flag a test record and verify it disappears from normal retrieval while remaining available to authorized reviewers.

## Failure correction

Quarantine correlated records, identify the poisoning source, correct ingestion controls, and selectively restore only verified content.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
