# kernel-live-patching

**Issue:** Kernel CVEs arrive on a monthly cadence, but rebooting a fleet of production servers — databases, message brokers, long-running stateful workloads — is scheduled, negotiated, and often deferred for months, leaving servers running known-vulnerable kernels because the reboot window never comes. Kernel live patching (Canonical Livepatch, Oracle Ksplice, SUSE Live Patching, Red Hat kpatch, TuxCare KernelCare) applies security fixes to a running kernel without a reboot, closing the emergency-CVE gap immediately while deferring the reboot to a planned window. It is a bridge, not a destination: patch stacks have vendor-limited depth, not every CVE is patchable live, and kernel/userland skew accumulates the longer a host stays up. This article covers how the mechanism works, the vendor options, the real limits, and the operational discipline that makes live patching a security control rather than a new risk.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How live patching works

1. **Function-level replacement via ftrace.** The kernel livepatch subsystem, built on ftrace function tracing, redirects calls to patched kernel functions to replacement implementations shipped as a kernel module; the old code stays in memory but becomes unreachable. This is why patches are per-function rather than general.
2. **Consistency models.** Applying a patch while threads execute the old function requires a transition: the kernel migrates tasks onto the new code using its task-consistency engine. Most simple patches converge in seconds; ones touching deep call paths can take longer and log transition warnings.
3. **Patch stacking.** Successive fixes accumulate as a stack of live patches, and vendors cap cumulative depth — commonly around three to five — before requiring a fresh kernel plus reboot, because each layer adds transition risk and complexity.
4. **What cannot be patched live.** Changes requiring data-structure migration, heavy scheduler or memory-management rework, and some ABI-visible behavior never ship as live patches; vendors publish a per-CVE live-patchable determination, and a "no" means scheduling the real reboot.

## Vendor options

1. **Canonical Livepatch (Ubuntu Pro).** Free for small personal use and included with Ubuntu Pro for fleets; delivers CVE fixes for the running LTS kernel with a machine-readable status CLI that is easy to scrape for monitoring. Pairs naturally with unattended-upgrades for userspace packages.
2. **Oracle Ksplice.** Operates at a lower level, updating kernel memory objects directly, and historically patches a broader set of changes including some non-security updates; included with Oracle Linux support and common on OCI fleets.
3. **SUSE Live Patching (KLP).** Integrated with SLES maintenance and delivered as kernel-livepatch packages specific to each running kernel, with documented cumulative-patch limits per service pack that should be read before relying on long deferral windows.
4. **Red Hat kpatch and TuxCare.** Red Hat ships live patches for select critical CVEs on RHEL kernels; TuxCare KernelCare provides vendor-neutral live patching across distros, which suits mixed fleets or kernels near end-of-life — evaluate licensing fit against fleet composition.

## Operational practices

1. **Enable it where reboot windows are scarce.** The highest-value targets are stateful singletons (databases, message queues), long-lived bare-metal hosts, and any system whose reboot requires coordinated downtime or customer notification.
2. **Stage patches before fleet rollout.** Apply each live patch to a canary cohort first — live patches are kernel-version-exact, and a bad interaction is far cheaper to find on one host. Watch the kernel log for livepatch transition warnings and confirm the status tool reports the patch applied.
3. **Monitor patch state as a fleet metric.** Every vendor exposes machine-readable state (livepatch status, kpatch status, ksplice); scrape it, alert on failed or pending patches, and report kernel CVE coverage as the fraction of the fleet with the current patch level applied.
4. **Keep a reboot cadence anyway.** Live patching defers reboots, it does not remove them: schedule rolling reboots monthly or quarterly to reset the patch stack to zero, flush accumulated kernel/userland skew, and prove the fleet can still boot — a host that has not rebooted in a year carries an untested boot path and config drift.

## Limits and failure modes

1. **False sense of coverage.** Because not every CVE is live-patchable, dashboards must distinguish "patched live" from "requires reboot"; conflating the two hides exactly the exposure that reboot scheduling was supposed to close.
2. **Module-loading prerequisites.** Live patches load as kernel modules, so secure-boot signatures, module-signing keys, module-load policies, or lockdown mode can silently block application — verify in staging that your security configuration permits livepatch modules.
3. **Stack exhaustion surprises.** Hitting the vendor patch-depth cap during an active CVE incident forces an unplanned reboot under pressure; track stack depth per host and trigger planned reboots at roughly two-thirds of the cap.
4. **Rollback is limited and less tested.** Reverting a live patch is possible but far less exercised than applying; treat rollback as break-glass only — the safe recovery path for a misbehaving patch is the planned reboot you were deferring anyway.
