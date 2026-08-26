---
title: "AI Prompt and Configuration Governance"
owner: "AI Governance Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# AI Prompt and Configuration Governance

## Purpose

Treat material prompts, system instructions, policy rules, retrieval settings, and safety configuration as governed behavior-changing artifacts.

## Requirements

Material configuration SHOULD be versioned or otherwise auditable, reviewed, tested, and linked to an owner.

Sensitive prompts or internal policy logic must not be exposed publicly merely for transparency if disclosure would materially weaken safety or security.

## Change

Configuration changes that alter behavior, permissions, data use, or evaluation assumptions follow [AI Change Management](AI_CHANGE_MANAGEMENT.md).

## Secrets

Prompts and configuration must not contain reusable credentials or other secrets.
