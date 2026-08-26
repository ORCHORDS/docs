---
title: "Identity and Authentication Policy"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Identity and Authentication Policy

## Purpose

Define identity and authentication requirements without publishing account
inventories or implementation details.

## Requirements

Access to company systems MUST be attributable to an authorized identity.
Authentication strength should increase with privilege, data sensitivity, and
impact.

Controls SHOULD include, where supported and proportionate:

- strong multi-factor authentication for privileged or high-impact access;
- phishing-resistant methods for the most sensitive administrative access;
- secure recovery processes resistant to simple impersonation;
- rate limiting or equivalent protections against automated guessing;
- session expiration and revocation appropriate to risk;
- re-authentication for sensitive actions;
- prompt disabling of identities that no longer require access.

## Service identities

Non-human identities must have a named owner, limited permissions, a defined
purpose, and lifecycle review. Long-lived static credentials should be avoided
where stronger alternatives exist.

## Evidence

Access and authentication claims require current configuration or review
evidence; policy wording alone does not demonstrate implementation.
