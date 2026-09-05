---
title: "Agent Human Handoff Procedure"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Human Handoff Procedure

## Scope

Defines how ORCHORDS agents hand off a task to a human reviewer or operator when the agent cannot safely proceed, so that the handoff is timely, complete, and accountable.

## Identifier table

| Field | Value |
|---|---|
| Topic | Procedure for handing off agent tasks to humans |
| Inputs | Handoff reason, context packet, task identifier, contact routing |
| Outputs | Routed handoff, context packet, audit record, handoff SLA |
| Audience | AI Platform, Service Owners, Operations |
| Trigger | Confidence threshold breach, policy block, escalation rule, or operator request |
| Companion | AGENT_HUMAN_HANDOFF_CONTEXT_PACKET.md, AGENT_HUMAN_HANDOFF_AUTHENTICATION.md |

## Plan

1. Define handoff triggers: confidence below threshold, policy block, escalation rule fired, operator-initiated, or sustained error.
2. Build the context packet: task identifier, conversation history, retrieved evidence, last model response, tool calls, and the handoff reason.
3. Route the packet to the appropriate queue based on reason, severity, and tenant; respect any on-call schedule.
4. Hold the agent task open until the human acknowledges; record the queue dwell time as a tracked metric.
5. Record the handoff event in the audit trail with timestamp, reason, and routing decision.
6. Notify the requester that the task is queued for human review; do not invent interim answers.
7. When the human responds, integrate the response back into the agent loop and resume; record the resumption event.

## Inputs

- Handoff reason and severity
- Context packet fields
- Routing rules and on-call schedule

## ORCHORDS Profile

| Trigger | Queue |
|---|---|
| Confidence below threshold | General reviewer queue |
| Policy block | Trust and Safety queue |
| Escalation rule fired | Domain expert queue |
| Operator request | Operator queue |
| Sustained error | Reliability queue |

## Implementation Notes

- Never invent an interim answer while a task is queued for human review; respond with the documented hold message.
- Treat the context packet as a privacy-sensitive artifact; apply the data classification redaction policy.

## Companion Documents

- AGENT_HUMAN_HANDOFF_CONTEXT_PACKET.md
- AGENT_HUMAN_HANDOFF_AUTHENTICATION.md
- AGENT_TOOL_USE_AUDIT_TRAIL.md
