---
title: "Agent Error Recovery"
owner: "Documentation Maintainer"
status: "review"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Agent Error Recovery

## Purpose

Agent loops should handle tool and dependency failures without uncontrolled retries, silent corruption, or loss of useful failure context.

## Recovery pattern

A tool invocation SHOULD distinguish between transient failures, invalid requests, authorization failures, dependency failures, and permanent errors. Retry behavior MUST be bounded and SHOULD be limited to failures that are reasonably expected to succeed on a later attempt.

A generic flow is:

1. validate the request before invocation;
2. apply an operation-specific timeout;
3. classify the resulting success or failure;
4. retry only retryable failures using a bounded delay strategy;
5. preserve structured failure information for the caller;
6. stop after the configured attempt or resource budget is exhausted;
7. select an alternative approach only when doing so is safe and meaningful.

## Error information

Where an agent is expected to reason about recovery, return structured error information rather than an unclassified exception string. Useful fields can include:

- error category;
- retryable or non-retryable status;
- operation name;
- attempt number;
- safe diagnostic message;
- suggested next action when one is known.

Sensitive request data, credentials, internal paths, and raw upstream responses MUST NOT be exposed merely to help the model recover.

## Retry guidance

- Validation and authorization failures generally require changed input or permissions rather than repeated identical attempts.
- Operations with side effects SHOULD be idempotent or otherwise protected against duplicate execution before automatic retries are enabled.
- Retry delays and limits SHOULD be configurable for the dependency and workload instead of treated as universal constants.
- Repeated failures SHOULD be observable so unreliable tools or integrations can be investigated.

## Completion criteria

Recovery is successful when the agent either completes the requested operation safely or returns a bounded, understandable failure without continuing an uncontrolled loop.
