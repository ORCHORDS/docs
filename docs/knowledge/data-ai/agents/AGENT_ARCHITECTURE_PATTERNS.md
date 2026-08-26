---
title: "Agent Architecture Patterns"
owner: "Documentation Maintainer"
status: "review"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Agent Architecture Patterns

## Purpose

This document summarizes reusable architectural patterns for tool-using language-model agents. The appropriate pattern depends on task complexity, latency, reliability requirements, available tools, and the cost of additional model calls.

## Common patterns

| Pattern | Description | Useful when |
| --- | --- | --- |
| ReAct-style loop | Interleave reasoning, actions, observations, and subsequent decisions. | The task requires iterative interaction with tools or an environment. |
| Plan and execute | Separate higher-level decomposition from task execution. | The task has multiple dependent steps that benefit from explicit sequencing. |
| Reflection or critique | Evaluate an intermediate or final result and decide whether another attempt is justified. | Additional review can materially improve correctness or completeness. |
| Multi-agent orchestration | Route work to multiple specialized workers or roles. | The task contains separable responsibilities that justify coordination overhead. |

## Common components

An agent architecture MAY contain:

- working context for short-lived task state;
- persistent memory where long-lived state is genuinely required;
- tools with explicit inputs, outputs, permissions, timeouts, and failure behavior;
- a planner or router for decomposition and dispatch;
- an executor for tool use or task completion;
- validation or observation logic for checking outputs and controlling loops.

## Reliability considerations

- Every iterative loop SHOULD have an explicit stopping condition and bounded resource budget.
- Complex plans SHOULD preserve enough state to resume or fail safely after partial execution.
- Tool permissions SHOULD follow least-privilege principles.
- Tool outputs SHOULD be validated before they are used as authoritative input to later steps.
- Observability SHOULD be designed early enough to diagnose loops, tool failures, and unexpected routing decisions.

## Selection guidance

Prefer the simplest architecture that satisfies the task. Additional planners, critics, memory systems, or workers increase operational complexity and SHOULD be added only when evaluation demonstrates a useful improvement.
