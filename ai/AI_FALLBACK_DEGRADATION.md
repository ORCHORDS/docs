---
title: "AI Fallback and Degradation"
owner: "AI Governance Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# AI Fallback and Degradation

## Purpose

Define safe behavior when AI quality, availability, monitoring, or provider assumptions degrade.

## Requirements

Material AI capabilities SHOULD define when to restrict, fall back, require human review, disable actions, or fail closed/open according to consequence. Degraded modes must not silently grant broader permissions or bypass validation.

Fallback behavior should be tested for dependency failure, rate limits, model/provider change, unavailable retrieval/context, monitoring failure, and repeated unsafe outputs.
