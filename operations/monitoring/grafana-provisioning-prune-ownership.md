# Grafana provisioning prune ownership

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Provisioning with prune can delete resources no longer present in configuration, including resources another workflow expects to own.

## When to use

Use for declarative data-source or dashboard ownership with a reviewed deletion lifecycle.

## Controls

Give each provider exclusive ownership, version configuration, back up recoverable state, and require deletion review.

## Implementation

Inventory current ownership, dry-run through an isolated Grafana instance, enable prune for one provider, reconcile, and verify only absent managed resources are removed.

## Tests

Test rename, provider removal, partial mounts, startup failure, rollback, manually edited resources, and concurrent replicas.

## Gotchas

Editable UI state can drift from files; prune is destructive and filesystem ordering is not an approval mechanism.

## Official sources

- [Official documentation](https://grafana.com/docs/grafana/latest/administration/provisioning/)
