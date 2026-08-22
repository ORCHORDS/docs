---
title: "Customer Identity Verification"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Customer Identity Verification

## Purpose

Prevent support channels from becoming an account-takeover or data-disclosure bypass.

## Principles

Verification strength MUST match the sensitivity of the requested action. Reading general help content needs little or no verification; changing security settings, recovery methods, payment details, or disclosing sensitive account data requires substantially stronger proof.

## Safe verification

Prefer existing authenticated sessions, established recovery channels, possession-based factors, or other approved mechanisms. Avoid knowledge questions based on easily discoverable personal information.

Support staff must not ask users to provide passwords, recovery phrases, full private keys, or reusable authentication codes intended for login.

## Exceptions

If normal verification fails, use a documented recovery/escalation process rather than improvising weaker checks.

See [Support Identity Verification SOP](../sop/SUPPORT_IDENTITY_VERIFICATION_SOP.md).
