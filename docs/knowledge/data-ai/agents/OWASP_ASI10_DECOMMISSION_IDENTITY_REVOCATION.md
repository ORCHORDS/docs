# Agent Decommission Identity Revocation

## Purpose

Control profile for **OWASP ASI10: Rogue Agents**.

## Control

Tie agent decommissioning to revocation of workload identities, delegated credentials, peer trust, tool access, durable jobs, and discovery metadata.

## Validation

Decommission a test agent and attempt authentication, tool use, peer discovery, and task resumption; verify all intended capabilities are gone.

## Failure correction

Revoke residual authority immediately, remove stale discovery and jobs, and update the decommission checklist to cover the missed resource.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
