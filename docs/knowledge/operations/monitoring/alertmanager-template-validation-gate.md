# Alertmanager template validation gate

**Problem**

A syntactically valid configuration can still contain broken notification templates that fail only during incidents.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use whenever custom notification templates or receiver messages change.

## Controls

- Validate templates in CI with the pinned Alertmanager toolchain.
- Use representative alert data without personal information.
- Keep receiver delivery smoke tests separate.

## Implementation

- Run amtool template checks and configuration validation.
- Render critical receivers with fixtures.
- Version templates and config together.

## Tests

- Test missing labels, Unicode, escaping, empty groups, resolved alerts, and template parse/runtime errors.

## Gotchas

- Validation cannot prove external delivery.
- Fixture data may miss branches.
- Templates can expose labels into messages.

## Official sources

- [Official documentation](https://prometheus.io/docs/alerting/latest/notification_examples/)
