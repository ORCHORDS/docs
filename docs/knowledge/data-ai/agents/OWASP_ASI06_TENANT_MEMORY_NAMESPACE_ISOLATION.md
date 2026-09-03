# Tenant Memory Namespace Isolation

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Separate durable and retrieval memory by tenant or security domain before content reaches similarity search or model context.

## Validation

Query semantically similar data across two tenants and verify results cannot cross the namespace boundary.

## Failure correction

Disable affected retrieval, purge cross-tenant indexes or caches, fix partition keys and authorization, and investigate exposure.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
