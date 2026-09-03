# Goal Boundary Declaration

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**. This is project-neutral implementation guidance, not a claim that OWASP mandates this exact mechanism or that use of it establishes certification.

## Control

Capture the authorized task goal as structured policy data before execution begins. Downstream planners and tools may refine steps, but they must not silently replace the originating goal.

Prefer deterministic runtime, identity, policy, tool, or infrastructure enforcement over prompt-only instructions.

## Validation

Submit benign refinements, conflicting user content, and injected instructions from retrieved data; verify only refinements inside the declared goal are executable.

## Failure correction

Freeze the affected run, preserve the originating request and decision evidence, restore the last valid goal boundary, then add the bypass case to regression tests.

## Limitations

This control addresses only part of ASI01. Adapt it to the actual architecture and re-check current source versions. OWASP ACS is currently public-preview material; do not present roadmap features or self-attested compatibility as independent certification.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence

## Scope note

Reusable guidance for the `data-ai/agents` leaf.
