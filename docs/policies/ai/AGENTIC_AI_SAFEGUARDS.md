---
title: "Agentic AI Safeguards"
owner: "AI Governance Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Agentic AI Safeguards

## Purpose

Define safeguards for AI systems that can select actions, call tools, modify resources, communicate externally, or initiate workflows.

## Requirements

Agentic systems SHOULD use least privilege, explicit tool allowlists, bounded execution, safe defaults, transaction or action limits, human confirmation for high-impact steps, auditability, and an immediate disable path.

Untrusted model output must not directly authorize privileged action. Authorization must be enforced by trusted controls outside the model decision alone.

## High-impact actions

Financial transfers, credential changes, destructive data actions, public communications, legal commitments, and privileged system changes require stronger controls and usually human approval.

## Testing

Evaluate chaining failures, repeated retries, hidden state, external-content injection, tool errors, and unsafe recovery behavior.
