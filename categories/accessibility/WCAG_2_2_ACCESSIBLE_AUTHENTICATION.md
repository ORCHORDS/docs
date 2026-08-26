---
title: "WCAG 2.2 Accessible Authentication"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WCAG 2.2 Accessible Authentication

WCAG 2.2 Success Criterion 3.3.8, Accessible Authentication (Minimum), is Level AA. It limits reliance on cognitive-function tests during authentication unless an allowed alternative or assisting mechanism is available.

## Governance requirements

- Do not block password-manager use in login flows.
- Do not disable copy and paste for passwords or one-time codes merely as a security convention.
- When a login step requires recall, transcription, or puzzle solving, assess whether an alternative method or assisting mechanism satisfies WCAG 2.2 requirements.
- Test authentication flows with assistive technology and common password-manager behavior before making accessibility claims.
- Treat visual object-recognition challenges as an exception pathway, not a preferred accessibility pattern.

## Review checklist

1. Can users rely on password managers where passwords are used?
2. Can users paste credentials and verification codes where appropriate?
3. Does any authentication step require memorization, transcription, calculation, or puzzle solving?
4. If so, is an allowed alternative or mechanism available?
5. Are fallback and recovery flows held to the same accessibility standard as the primary login path?

## Claims boundary

Documenting this control does not prove WCAG conformance. Conformance claims require evidence across the applicable success criteria and tested user journeys.

## Primary sources

- W3C WCAG 2.2 — https://www.w3.org/TR/wcag/
- W3C Understanding SC 3.3.8 — https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html
