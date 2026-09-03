# Embedding Index Provenance

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Track which source corpus, embedding model, chunking policy, and index build produced a retrieval index used by agents.

## Validation

Change one build input and verify the resulting index has a distinct, inspectable lineage rather than silently replacing prior state.

## Failure correction

Stop using the untraceable index, rebuild from known inputs, and document the verified build identity.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
