---
title: "Session Security Governance"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-23"
review-cycle: "90 days"
next-review: "2026-11-21"
---

# Session Security Governance

## Purpose

Protect authenticated sessions from unauthorized reuse, excessive lifetime, and weak recovery or revocation behavior.

## Requirements

Material authentication sessions SHOULD define issuance conditions, lifetime, inactivity behavior, re-authentication triggers, revocation capability, device or context changes where relevant, and logging appropriate to risk.

High-impact actions may require stronger or fresher authentication than ordinary navigation.

Session identifiers and equivalent secrets must not be exposed through public logs, URLs, or documentation.
