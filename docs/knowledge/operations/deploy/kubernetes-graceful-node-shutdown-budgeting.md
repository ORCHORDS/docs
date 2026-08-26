# Kubernetes graceful node-shutdown budgeting

**Issue:** Host shutdown can terminate Pods abruptly when kubelet and operating-system shutdown budgets are not coordinated.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Kubernetes graceful node shutdown lets kubelet detect supported system shutdown and terminate Pods within configured `shutdownGracePeriod` budgets. Critical and regular Pods can have separate allocation.

Coordinate node-level budgets with Pod `terminationGracePeriodSeconds`, preStop work, load-balancer draining, disruption controls, and the host service manager. A budget that exceeds the platform's actual shutdown window provides false assurance.

## Controls

- Measure real application drain time.
- Reserve time for critical node services.
- Make termination handlers idempotent.
- Keep forced-power-loss recovery independently safe.
- Monitor node shutdown and Pod termination events.
- Test autoscaler and maintenance workflows.

## Verification

1. Perform a controlled host shutdown.
2. Confirm readiness drains before termination.
3. Measure regular and critical Pod budgets.
4. Test a Pod that exceeds its grace period.
5. Validate recovery after ungraceful power loss.

## Sources

- [Kubernetes: Graceful node shutdown](https://kubernetes.io/docs/concepts/cluster-administration/node-shutdown/)
- [Kubernetes: Pod termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination)
