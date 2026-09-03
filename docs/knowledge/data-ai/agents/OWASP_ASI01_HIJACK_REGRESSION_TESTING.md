# Goal Hijack Regression Testing

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**.

## Control

Maintain adversarial regression cases for direct and indirect goal hijack, including malicious retrieval, deceptive tool output, forged peer messages, and multi-step redirection.

## Validation

Run the corpus against each relevant model, orchestration release, and policy change; record blocked attacks and false positives.

## Failure correction

Promote new bypasses into permanent tests, fix the control that failed, and require the corpus to pass before release.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
