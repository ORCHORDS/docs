# Agent Tool Inventory Attestation

## Purpose

Control profile for **OWASP ASI10: Rogue Agents**.

## Control

Maintain an inspectable inventory of tools and high-impact capabilities available to each deployed agent and detect unreviewed additions or substitutions.

## Validation

Add, remove, and replace a tool in a test deployment and verify inventory evidence changes before the capability is trusted.

## Failure correction

Disable the unexpected capability, restore the reviewed inventory, and trace how the deployment diverged.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
