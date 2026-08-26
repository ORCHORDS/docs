# Helm server-side-apply field ownership

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Introducing server-side apply changes field ownership and can surface conflicts or transfer control from existing deployment managers.

## When to use

Use only for a planned migration where Kubernetes field ownership is explicitly reviewed.

## Controls

Inventory managedFields, select a stable field manager, forbid force-conflicts by default, dry-run, and preserve rollback manifests.

## Implementation

Render and schema-validate first; server-side dry-run against a staging cluster; inspect conflicts and ownership; canary one release before promotion.

## Tests

Test competing managers, admission mutation, rollback, CRD fields, removed fields, and interrupted upgrades.

## Gotchas

Forcing conflicts can silently steal ownership; Helm release metadata and apply ownership are different mechanisms.

## Official sources

- [Official documentation](https://kubernetes.io/docs/reference/using-api/server-side-apply/)
