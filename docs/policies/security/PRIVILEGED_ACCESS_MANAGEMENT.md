---
title: "Privileged Access Management"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Privileged Access Management

## Purpose

Control access capable of materially changing security, data, production behavior, financial records, or administrative configuration.

## Requirements

Privileged access MUST be attributable to an authorized identity, limited to the minimum necessary scope, strongly authenticated, and reviewed more frequently than ordinary access.

Where practical, prefer temporary or just-in-time elevation over permanent standing privilege. Shared administrative identities should be avoided; unavoidable shared access requires compensating accountability controls.

## High-risk actions

Sensitive actions SHOULD have additional safeguards such as independent approval, re-authentication, logging, or separation of duties proportional to impact.

## Lifecycle

Privileges must be removed promptly when duties change or the access purpose ends. Emergency access requires retrospective review.

See [Privileged Access SOP](../sop/PRIVILEGED_ACCESS_SOP.md).
