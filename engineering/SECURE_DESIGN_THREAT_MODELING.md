---
title: "Secure Design and Threat Modeling"
owner: "Engineering and Security Leads"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Secure Design and Threat Modeling

## Purpose

Require security and privacy reasoning early enough to change design, not only
after implementation.

## Triggers

Threat modeling is expected for new trust boundaries, authentication or
authorization changes, sensitive-data flows, internet exposure, privileged
operations, external integrations, high-impact automation, AI tool use, and
other material changes in attack surface.

## Method

A threat model should identify:

1. assets and security/privacy objectives;
2. actors and trust boundaries;
3. data and control flows;
4. plausible misuse and abuse cases;
5. dependencies and supplier assumptions;
6. required controls;
7. residual risk and unresolved assumptions;
8. verification and monitoring needs.

Teams may use STRIDE, attack trees, misuse cases, data-flow analysis, or another
method suited to the system. The method is less important than complete,
reviewable reasoning.

## Outputs

Material findings become tracked requirements, tests, design changes, or
explicit risk decisions. Threat models are updated after material architecture,
trust, or exposure changes.
