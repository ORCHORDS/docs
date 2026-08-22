---
title: "Service Reliability Objectives"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Service Reliability Objectives

## Purpose

Define how reliability objectives are selected and used without publishing
private production measurements.

## Principles

Reliability objectives should reflect user-visible outcomes and business
impact. Useful measures may include availability, successful request rate,
latency, data freshness, job completion, or recovery performance.

## Objectives

An objective SHOULD specify:

- measured outcome;
- population or scope;
- measurement window;
- target;
- exclusions that are genuinely necessary;
- owner;
- action when the objective is missed.

## Use

Objectives are decision tools, not marketing guarantees. They may guide
capacity planning, change risk, incident priority, and investment.

Public statements must not convert an internal reliability objective into a
service guarantee unless that commitment is explicitly approved.
