---
title: "Agent-Assist Disclosure"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Agent-Assist Disclosure

## Purpose

Define when and how customer-support personnel must disclose that an AI-assisted tool (an "agent-assist" copilot, suggested-response model, summarizer, or similar automated aid) is participating in the support interaction, so that customers are not misled about who they are talking to and so that audit, accessibility, and privacy commitments remain defensible.

## Scope

This article covers live and asynchronous support channels — chat, messaging, email, voice with real-time transcription, and ticket workflows — whenever an AI model contributes generated text, suggested actions, summaries, or code that is shown to a customer or used to determine an action taken on a customer's behalf. It does not govern internal agent-training material, off-channel analytics that do not influence the customer-visible response, or backend model evaluation. The scope is further limited to public-facing disclosure obligations; it does not dictate internal logging, model evaluation, or vendor-selection criteria, which sit with security and platform owners.

## Definitions

An "agent-assist" is any model-driven capability that proposes or composes customer-visible language, suggests the next action, summarizes prior case context, or auto-classifies a case. A "handoff" is any transition between automated and human contribution within a single interaction. A "meaningful" contribution is one that materially shapes the customer-visible reply, classification, or resolution, as distinct from spell-check, translation plumbing, or rendering tooling that does not change semantics.

## Requirements

Support tooling MUST make the use of agent-assist capabilities visible to the operating agent in real time, and the operating agent MUST be able to disclose the use of agent-assist to the customer on request, in the customer's preferred accessible format, without delay. Channels that rely substantially on automated drafting (for example, where the first response a customer receives is generated in whole or in part by a model) MUST include a clear, plain-language disclosure at the start of the interaction indicating that automated assistance is in use and that a human can be reached. Channels in which the human agent authors the final reply MAY rely on on-request disclosure rather than standing notice, provided the agent can satisfy that request from within the tool.

The disclosure MUST NOT misrepresent the capability. The agent MUST NOT state or imply that the model is a person, that the model holds account authority, or that the model's output has been independently verified when it has not. If the customer asks the model a question directly (for example, in a chat where the model is the named participant), the response MUST clearly identify the responder as an automated system and provide a path to a human.

The disclosure threshold SHOULD be reviewed against accessibility guidance. Customers who use assistive technology, who interact in writing because voice is unavailable, or who have explicitly requested human-only handling MUST receive equivalent disclosure through the channel they are using. The agent MUST NOT bypass disclosure to expedite case closure.

## Customer opt-out

Customers MUST be able to opt out of agent-assist drafting for the remainder of an active interaction and, where the channel supports it, for future interactions on their account. Opt-out MUST be honored promptly, and the channel MUST fall back to human-authored handling without degrading the case priority. Opt-out preferences MUST be recorded in the case record with a timestamp and the agent or system that applied them. Repeated opt-outs by the same account SHOULD be surfaced in quality review to detect over-reliance on automation in contravention of stated customer preference.

## Audit

Every agent-assist interaction MUST be logged with at least the model or capability identifier, the prompt and response as shown to the agent (or a faithful summary if the underlying text is too large for the audit log), the customer-visible reply, and whether disclosure was rendered, requested, or declined. Audit logs MUST be retained per the records-retention schedule and MUST be reviewable by the support-quality, privacy, and compliance functions without redaction of audit metadata. When a complaint, regulator request, or accessibility incident implicates agent-assist output, the relevant log entries MUST be retrievable by case identifier, customer identifier, time window, or model identifier within the timelines set by the receiving function.

## Controls

Periodic sampling of agent-assist cases MUST verify that disclosure language is present where required, that opt-out requests were honored within the documented window, and that the customer-visible reply does not contradict the disclosure (for example, by claiming an unverifiable independent verification). Findings MUST feed the quality program and the model-risk review. Material failures MUST trigger retraining of the agent, adjustment of the tool, or escalation to the privacy and security functions.

## Canonical sources

- European Data Protection Board, *Guidelines 05/2020 on consent under Regulation 2016/679*, https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-052020-consent-under-regulation-2016679_en
- NIST AI Risk Management Framework (AI RMF 1.0), https://www.nist.gov/itl/ai-risk-management-framework
- ISO/IEC 42001:2023, Information technology — Artificial intelligence — Management system, https://www.iso.org/standard/81230.html
- Web Content Accessibility Guidelines (WCAG) 2.2, https://www.w3.org/TR/WCAG22/
