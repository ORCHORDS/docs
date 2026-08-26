# Gmail Postmaster spam-rate monitoring

**Date:** 2026-08-26
**Status:** documented
**Sources:**
- https://support.google.com/mail/answer/81126
- https://support.google.com/mail/answer/14229414

## Context

Google's sender guidance tells senders to monitor user-reported spam rates in Postmaster Tools. Current guidance recommends staying below 0.1% and avoiding 0.3% or higher; the FAQ says rates at or above 0.3% can make bulk senders ineligible for mitigation.

## Pattern

- Monitor spam rate daily for domains used for subscription traffic.
- Alert before the 0.3% ceiling; treat 0.1% as an operational warning threshold rather than a success target.
- Correlate spikes with campaign, list source, sender identity, and subscription flow.
- Pause or reduce problematic traffic while investigating instead of trying to out-send a reputation problem.
- Review opt-in, list hygiene, unsubscribe latency, and content expectations.

## Verification

Document the monitoring owner, dashboard location, warning threshold, escalation path, and evidence retained for corrective actions.

## Important distinction

A low Postmaster spam rate does not by itself prove legal compliance, good list quality, or guaranteed inbox placement. It is one delivery/reputation signal among several.
