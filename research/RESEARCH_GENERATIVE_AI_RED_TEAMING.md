---
title: "Generative AI Red Teaming in Research"
owner: "Research Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Generative AI Red Teaming in Research

Source: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf

NIST AI 600-1 recommends adversarial role-playing, generative-AI red teaming, or chaos testing as ways to identify anomalous or unforeseen failure modes.

## Governance

- Define the research question and allowed test boundary before adversarial testing begins.
- Separate model evaluation from attempts to induce prohibited real-world harm.
- Record prompts/scenarios, model/version, configuration, observed failures, and mitigation decisions needed for reproducibility.
- Treat red-team success as evidence of a failure mode, not evidence that every deployment is vulnerable in the same way.
- Protect sensitive test data and do not publish exploit-enabling detail merely to demonstrate that testing occurred.

## Evidence

Findings should be reproducible where feasible, severity-ranked, linked to an owner, and re-tested after mitigation.