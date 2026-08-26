---
title: "Security Requirements Engineering"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Security Requirements Engineering

## Purpose

Make security and privacy requirements explicit before implementation rather than inferred during final review.

## Requirements

Material changes SHOULD identify relevant authentication, authorization, confidentiality, integrity, availability, privacy, abuse-resistance, auditability, recovery, and supplier requirements before build completion.

Requirements must be testable where practical and connected to acceptance evidence.

## Sources

Requirements may come from threat models, legal or contractual obligations, policy, prior incidents, application-security standards, user harm analysis, or architecture constraints.

## Changes

If implementation materially changes a trust boundary or risk assumption, revisit the requirements rather than treating the original specification as fixed.
