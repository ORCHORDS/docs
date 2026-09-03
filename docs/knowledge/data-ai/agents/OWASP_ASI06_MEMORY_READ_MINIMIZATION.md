# Memory Read Minimization

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Retrieve the minimum memory needed for the current task and authorization context instead of exposing broad conversation or organizational history by default.

## Validation

Compare narrow and broad queries for the same task and verify sensitive unrelated memories are excluded before model context assembly.

## Failure correction

Tighten retrieval filters and authorization, purge over-broad cached context, and review traces for unnecessary exposure.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
