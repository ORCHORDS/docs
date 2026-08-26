# OpenTelemetry tail-sampling policy validation

**Issue:** Tail sampling can preserve valuable error traces, but insufficient collector capacity or policy mistakes can silently discard evidence after buffering entire traces.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Run tail sampling in a stateful collector tier with consistent trace routing. Size `decision_wait`, expected new traces, and trace buffers from measured traffic; define ordered, testable policies for errors, latency, attributes, and probabilistic remainder. Monitor dropped spans, late spans, decision latency, memory, and policy outcomes. Remove or hash sensitive attributes before policy evaluation where retention itself is regulated.

## Verification

Replay labeled traces covering every policy, traces arriving before and after the decision window, and overload beyond capacity. Verify complete-trace export rates, deterministic routing, failover behavior, and that collector restarts have an explicitly accepted loss model.

## Gotchas

- Confirm behavior against the exact deployed version; feature state and defaults can change.
- Preserve logs and artifacts needed to reproduce failures without recording secrets or personal data.
- Roll out behind a reversible change and define the rollback trigger before production use.

## Official source

- [Primary documentation](https://opentelemetry.io/docs/platforms/kubernetes/collector/components/#tail-sampling-processor)
