# Prometheus keep_firing_for alert-resolution stability

**Issue:** Brief query gaps or metric interruptions can resolve and immediately re-fire an alert, producing noisy notifications and misleading incident timelines.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Prometheus alerting rules can use `keep_firing_for` to keep an already firing alert active for a bounded period after its expression last matched. This can absorb short false-resolution gaps. It differs from `for`, which delays the transition from pending to firing.

Use it only where a short missing or recovering signal should not declare resolution. It must not conceal a genuinely recovered condition longer than the operational objective, and it does not repair unreliable telemetry.

## Operational controls

- Set the duration from scrape interval, evaluation interval, expected gaps, and notification timing.
- Fix chronic missing data instead of extending the hold indefinitely.
- Distinguish absence from healthy values in the alert expression.
- Document expected user-visible resolution delay.
- Review interaction with Alertmanager grouping, repeat intervals, inhibition, and resolved notifications.
- Unit-test rules and observe state transitions during rollout.

## Verification

1. Make the condition fire and then clear for less than the hold duration.
2. Confirm the alert remains firing without a false resolved notification.
3. Clear it longer than the duration and confirm resolution.
4. Introduce missing series and verify the expression's intended semantics.
5. Run `promtool test rules` for pending, firing, held, and resolved states.

## Sources

- [Prometheus: Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus: Unit testing rules](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
- [Alertmanager: Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
