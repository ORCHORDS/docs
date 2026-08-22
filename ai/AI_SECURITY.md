---
title: "AI Security"
owner: "AI Governance Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# AI Security

## Purpose

Apply security engineering to AI-specific attack and failure modes.

## Risk areas

Depending on architecture and use, assess prompt or instruction injection, unsafe tool use, excessive agent permissions, sensitive context disclosure, model or data poisoning, insecure retrieval, output-to-command injection, denial of service, supply-chain risk, and abuse of generated content.

## Requirements

AI components should follow least privilege, input/output trust-boundary controls, secrets management, dependency governance, monitoring, and incident response.

Untrusted model output MUST be treated as untrusted input before it can trigger privileged or security-sensitive actions.

## Testing

Evaluation should include adversarial and misuse cases relevant to the actual integration, not only model-quality benchmarks.
