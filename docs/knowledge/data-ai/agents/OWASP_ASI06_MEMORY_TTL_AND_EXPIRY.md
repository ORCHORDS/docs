# Memory TTL and Expiry

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Assign expiration or review policy to memory that should not persist indefinitely, especially volatile preferences, temporary authority, and external facts.

## Validation

Advance or simulate expiry and verify stale entries stop influencing retrieval or are clearly marked for review.

## Failure correction

Expire stale data, invalidate derived caches, and correct defaults that created unbounded retention.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
