---
title: "AI Output Validation"
owner: "AI Governance Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# AI Output Validation

## Purpose

Prevent plausible-looking AI output from being treated as trusted evidence or authorization without appropriate validation.

## Requirements

Validation strength SHOULD increase with consequence. High-impact outputs may require source checks, deterministic validation, independent rules, human review, bounded actions, or confirmation through an authoritative system.

Model confidence, fluency, or repeated agreement from the same model family is not sufficient independent validation.

Untrusted model output must not directly grant privilege, approve financial action, or authorize destructive changes.
