---
title: "Experimentation Governance"
owner: "Product Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Experimentation Governance

## Purpose

Govern product experiments so learning does not create disproportionate user, privacy, accessibility, security, or data-integrity risk.

## Requirements

Material experiments SHOULD define hypothesis, target population, decision metric, duration or stopping rule, user-risk review, data handling, rollback, and owner.

## Guardrails

Experiments must not silently weaken required security, privacy, or accessibility controls unless an explicit approved test environment and exception process applies.

## Integrity

Avoid changing success metrics after results are known without clearly documenting the change. Negative or inconclusive results are valid evidence.

See [Experiment Review SOP](../sop/EXPERIMENT_REVIEW_SOP.md).
