---
title: "Dependency Ownership"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-23"
review-cycle: "90 days"
next-review: "2026-11-21"
---

# Dependency Ownership

## Purpose

Ensure material dependencies have clear accountability for adoption, maintenance, risk, and removal.

## Requirements

Material direct dependencies SHOULD have an owning team or role, intended purpose, update expectation, known criticality, and a path for replacement or removal.

Ownership includes responding to security advisories, upstream abandonment, licensing changes, breaking releases, and transitive-risk changes.

A dependency without a current owner should be treated as a maintainability and supply-chain risk.
