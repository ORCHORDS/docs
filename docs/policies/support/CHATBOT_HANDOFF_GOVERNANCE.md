---
title: "Chatbot Handoff Governance"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Chatbot Handoff Governance

## Purpose

Govern how a customer interaction is passed between an automated assistant and a human agent, and vice versa, so that the customer does not lose context, the case does not lose audit trail, and the customer retains a meaningful path to a person at any point.

## Scope

This article covers automated assistant flows deployed on chat, messaging, in-app help, voice self-service with human escalation, and similar channels, including scenarios in which an AI model composes suggested actions for a human agent. It covers hand-offs in both directions: from automation to a human agent, from a human agent back to automation, and between automated assistants of different capability. It does not govern internal routing between human queues or between specialists, which sit with the existing handoff-governance rules.

## Requirements

This article sets the following obligations for the covered support activity. MUST/SHOULD/MAY statements throughout the body of this article are part of these requirements.


## Triggers for handoff to a human

An automated assistant MUST transfer the customer to a human agent, or offer an immediate path to one, when any of the following occurs:

- the customer explicitly asks for a human, a person, an agent, a supervisor, or to "speak to someone";
- the customer expresses frustration, distress, safety concern, or urgency that the assistant cannot resolve from approved content;
- the case requires an action that the assistant is not authorized to perform, including sensitive account actions, identity verification beyond what the bot is approved to attempt, refunds or credits above the assistant's authority, or actions requiring dual control;
- the assistant has reached a defined retry limit or a defined confidence threshold below which further automated effort would be ineffective;
- the customer identifies as needing an accommodation, requests an alternative channel for accessibility reasons, or asks for a language interpreter;
- the conversation enters a category that is on the automated escalation list (privacy rights, security concerns, abuse, legal demand, regulator engagement, suspected compromise, fraud, or safety).

The handoff MUST be initiated promptly, MUST not require the customer to repeat the question, and MUST preserve the assistant's understanding of context to the maximum extent permitted by data-handling rules.

## Triggers for handoff back to automation

A human agent MAY route the conversation back to automation only when the remaining work is within the automation's approved scope, the customer has not asked for human-only handling, the routing does not strand the customer at a step that requires unavailable context, and the handoff is logged. Routing back MUST NOT be used to evade service-level obligations or to push a dissatisfied customer away from a person.

## Required context passed in the handoff

At a minimum, the handoff payload SHOULD include:

- a stable case or conversation identifier;
- the customer's stated question and the most recent user message in the original language;
- a summary of the steps the assistant has already taken and the content it has surfaced;
- the reason for handoff, drawn from an approved taxonomy;
- any verification state, with the method used and its scope (for example, "low-risk verification completed for general help");
- any accessibility, language, or accommodation flags the customer has set;
- references to artifacts (logs, attachments, error identifiers) that the human will need.

The handoff MUST NOT include secrets, passwords, full payment primary account numbers, or recovery phrases. It SHOULD include only the minimum personal data the receiving human needs to continue the interaction.

## Frustration and safety signals

The automated assistant MUST detect, at minimum, repeated identical requests, profanity, expressions of distress, mentions of harm, requests to cancel or delete account data, and explicit statements of dissatisfaction. When any of these are detected, the assistant MUST prioritize transfer to a human over continued automated resolution, even if the assistant believes it can satisfy the request, unless the customer has explicitly and recently asked the assistant to continue.

## Audit

Every handoff event — including the direction, the trigger, the timestamp, the actor (human, bot, or system), the receiving queue, and the context payload identifier — MUST be recorded in the case record. The recording MUST be sufficient for an after-action reviewer to reconstruct the journey of the conversation and to confirm that the trigger criteria were met. Hand-off patterns MUST be reviewed periodically for evidence of bots refusing to transfer when required, for evidence of premature transfers that would erode customer trust, and for evidence of patterns correlated with complaints.

## Customer experience

The customer MUST be told, in plain language and at the moment of transfer, that they are being connected to a human, what kind of human (frontline agent, specialist, supervisor), the expected wait, and what will happen if no human is available (for example, callback, ticket creation, or message follow-up). The customer MUST NOT be told that the transfer is a self-service step, an automated summary, or anything that misrepresents the change in responder.

## Canonical sources

- ISO 9241-210:2019, Ergonomics of human-system interaction — Human-centred design, https://www.iso.org/standard/77520.html
- Web Content Accessibility Guidelines (WCAG) 2.2, https://www.w3.org/TR/WCAG22/
- European Accessibility Act (Directive (EU) 2019/882), https://eur-lex.europa.eu/eli/dir/2019/882/oj
- NIST SP 800-53 Rev. 5, *SI-4 System Monitoring* and *SC-18 Mobile Code*, https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final
