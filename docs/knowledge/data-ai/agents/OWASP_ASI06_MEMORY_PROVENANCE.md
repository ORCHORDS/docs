# Agent Memory Provenance

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Store provenance with durable memory entries, including source, writer identity, task context, timestamp, and transformation lineage where practical.

## Validation

Insert equivalent memories from trusted and untrusted sources and verify provenance remains available after retrieval and summarization.

## Failure correction

Quarantine entries with missing or false provenance, repair the write path, and rebuild derived memories when necessary.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
