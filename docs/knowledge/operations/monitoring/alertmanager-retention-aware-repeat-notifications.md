# Alertmanager retention-aware repeat notification policy

**Issue**

Alertmanager remembers notification delivery state in its notification log. A route whose `repeat_interval` exceeds Alertmanager's `--data.retention` does not wait for the configured interval: the notification is repeated when retained state expires. An unnoticed mismatch can therefore page more often than the route suggests, especially after changing retention to control disk use.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Treat `repeat_interval`, `group_interval`, and `--data.retention` as one reviewed policy. Require `repeat_interval <= data.retention` for every paging route unless the earlier resend is explicitly intended.
- Make each `repeat_interval` an exact multiple of its inherited `group_interval`; Alertmanager otherwise checks on group ticks and rounds effective timing upward.
- Inventory inherited values across the complete route tree rather than reviewing only leaf snippets.
- Pin the retention flag in deployment configuration and include it in configuration-change review; do not rely on an image default.
- Keep highly urgent and low-urgency routes separate so retention tuning for storage does not silently redefine escalation cadence.
- In an HA cluster, keep peer versions and retention policy aligned and monitor peer health. Do not assume clustering repairs a policy mismatch.
- Size retention storage from measured notification-log and silence growth with headroom; a full volume or lost state can also change resend behavior.

## Verification

1. Render the effective Alertmanager command line and route configuration in CI.
2. Parse every route after inheritance and fail when a non-exempt `repeat_interval` is greater than `--data.retention` or is not divisible by `group_interval`.
3. In a disposable instance, fire a stable alert, record the first delivery, and confirm no unchanged delivery occurs before the approved repeat boundary.
4. Run a shortened-retention test and confirm the expected retention-driven resend; this proves the operational model rather than only syntax.
5. Restart one HA peer at a time and verify peer health, notification count, and receiver timestamps remain within the duplicate-delivery budget.
6. Alert on unexpected notification-rate increases, disk pressure, peer failures, and configuration reload failures.

## Gotchas

- `group_interval` is also the notification pipeline context timeout; making it very short can cancel slow receiver sends.
- A notification can be sent before `repeat_interval` when group membership changes or firing alerts resolve.
- Muting controls delivery, not the rest of route processing or stored alert state.
- Retention is not merely housekeeping: when it is shorter than `repeat_interval`, it becomes the effective maximum quiet period.
- A successful configuration reload proves validity, not that inherited timing values satisfy the organization's paging policy.

## Official sources

- [Alertmanager configuration: route timing and retention interaction](https://prometheus.io/docs/alerting/latest/configuration/)
- [Prometheus Alertmanager operational flags](https://github.com/prometheus/alertmanager)
