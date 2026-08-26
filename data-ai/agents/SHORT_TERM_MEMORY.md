---
title: "Agent Short-Term Memory"
owner: "Documentation Maintainer"
status: "review"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Agent Short-Term Memory

## Purpose

Short-term memory manages the task state and conversation context required during an agent run without assuming that every prior message must remain in active context.

## Context management

A context-management policy SHOULD account for the model's supported input limits, required instructions, tool protocol, current task state, and the cost of retaining older information. Fixed token limits SHOULD NOT be treated as portable across models or providers.

When reducing context, preserve information needed for correctness, including:

- active requirements and constraints;
- unresolved decisions and dependencies;
- safety and permission boundaries;
- state required to interpret later tool results;
- paired tool calls and results where the protocol requires them;
- provenance needed to distinguish observed facts from generated summaries.

## Reduction strategies

Depending on the application, older context MAY be handled by:

- removing information that is no longer relevant;
- summarizing older turns while retaining important constraints;
- storing structured task state separately from conversational prose;
- retrieving older material only when later steps require it.

Summaries SHOULD preserve uncertainty and MUST NOT silently convert assumptions into facts.

## Token accounting

If token budgets are enforced, accounting SHOULD use a tokenizer or counting method appropriate to the actual model interface. The system SHOULD reserve capacity for required output and tool interactions rather than filling the entire available context with history.

## Failure modes

Watch for loss of instructions, broken tool-call/result pairing, stale summaries, repeated compression that changes meaning, and context growth that causes truncation or unexpected request rejection.
