---
title: "Human Approval Checkpoints for Agents"
owner: "Documentation Maintainer"
status: "review"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Human Approval Checkpoints for Agents

## Purpose

Agent workflows that can cause material, difficult-to-reverse, privileged, financial, security-sensitive, or externally visible effects SHOULD use explicit approval controls appropriate to the risk.

## Approval design

Approval triggers SHOULD be defined by application policy or workflow configuration rather than left solely to the agent's own judgment. Examples can include:

- destructive or irreversible operations;
- privilege or access changes;
- publication or external communication;
- financial commitments or transfers;
- use of high-impact credentials;
- actions that cross an established trust boundary.

## Approval record

An approval request SHOULD present enough information for an informed decision, including the intended action, affected scope, expected effect, and relevant risk. It MUST NOT expose secrets or unnecessary sensitive data.

A decision record MAY include:

- request identifier;
- action category;
- requester or workflow identity;
- reviewer identity where appropriate;
- decision and timestamp;
- expiration or timeout state;
- safe reason or comment;
- evidence needed for audit or troubleshooting.

## Fail-safe behavior

- Approval requests SHOULD have an explicit lifetime rather than block indefinitely.
- Expired or unavailable approval SHOULD resolve to a documented safe state.
- A rejected action MUST NOT be silently transformed into an equivalent privileged action.
- Repeated approval prompts SHOULD be bounded to prevent pressure loops or accidental approval fatigue.
- Approval state SHOULD be bound to the specific proposed action so later changes require re-evaluation where material.

## Separation of responsibilities

For higher-risk workflows, the actor requesting approval and the mechanism recording approval SHOULD be sufficiently separated to prevent the agent from approving its own action or rewriting the decision record.
