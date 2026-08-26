# gpu-accelerator-monitoring

**Issue:** GPUs and other accelerators are the most expensive compute most teams ever operate, yet standard host monitoring (CPU, memory, disk) says almost nothing about whether that hardware is healthy or productive. A training job can silently degrade from thermal throttling, ECC errors can precede a card failure, and a mis-scheduled inference workload can leave a datacenter-class GPU at a few percent of real SM activity for days while host dashboards look green. This article covers how to observe accelerators (NVIDIA-centric, via DCGM) so hardware health, true utilization, and per-tenant fairness are all visible and alertable.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why host metrics do not cover GPUs

1. **GPU "utilization" is not SM activity.** The utilization number exposed by nvidia-smi only says a kernel was resident during the sample window. DCGM profiling metrics such as DCGM_FI_PROF_SM_ACTIVE report the ratio of streaming multiprocessors with active warps, and they reveal cards that are "100% utilized" while doing almost no math — the signature of data-starved, I/O-bound, or deadlock-spinning jobs.
2. **Accelerator failures are silent before they are catastrophic.** Correctable ECC errors, remapped rows, XID fault codes, and PCIe degradation appear in DCGM field IDs long before the device disappears; host-level monitoring only learns about the problem when the process crashes hours or days later.
3. **Thermal and power state is a leading indicator.** Temperature-violation counts, clock-throttling reasons, and current clocks versus max clocks show when a job is being throttled into slow motion. Users report it as "the model got slower", not as "the hardware is hot", so it never reaches the on-call engineer without instrumentation.

## Metrics worth collecting

1. **Utilization family.** DCGM_FI_PROF_SM_ACTIVE, DCGM_FI_PROF_PIPE_TENSOR_ACTIVE, and DRAM activity distinguish compute-bound, tensor-core-bound, and memory-bandwidth-bound phases of a workload, which points directly at whether optimization effort belongs in kernels, batch size, or data loading.
2. **Memory pressure.** Device memory used versus total plus allocator failure counts; GPU out-of-memory is the most common hard failure for model serving and is predictable from trend lines well before it kills a replica at peak load.
3. **Health and reliability.** Correctable and uncorrectable ECC counts, row remap events, DCGM_FI_DEV_XID_ERRORS for the actual fault codes, and NVLink or NVSwitch error counters for multi-GPU training jobs.
4. **Environment.** Temperature, power draw, and throttle reason codes; correlate throttling episodes with job slowdown reports to separate hardware problems from software regressions.
5. **Per-process accounting.** DCGM can attribute GPU memory and SM time per process and per container, which is the minimum needed to run a multi-tenant model fleet without blind spots.

## MIG and shared accelerators

1. **Enable per-instance metrics when using MIG.** With Multi-Instance GPU the physical card splits into isolated instances; counters must carry GPU-instance and MIG-device labels so a noisy neighbor in one slice is visible instead of averaged away by a per-card aggregate.
2. **Monitor fairness, not just totals.** On shared hardware, track per-tenant SM activity and memory separately; a fleet average of 80% utilization can hide one tenant pinned at 100% while another is starved.
3. **Prefer the GPU Operator on Kubernetes.** NVIDIA recommends deploying dcgm-exporter through the GPU Operator rather than a hand-rolled DaemonSet, because it keeps exporter configuration, drivers, and device plugins consistent across node upgrades.

## Alerts that pay for themselves

1. **Idle expensive hardware.** Alert on sustained low SM activity (for example, p95 tensor-pipe activity under 10% for six hours on a GPU not marked reserved). Idle GPUs are pure wasted spend and usually indicate a stuck scheduler or a crashed supervisor holding an allocation.
2. **ECC and XID faults.** Any uncorrectable ECC error or nonzero XID code warrants immediate attention; a rising rate of correctable errors on one card is a reliable predictor of retirement and should drive a drain-and-replace ticket.
3. **Thermal violations and sustained throttling.** A nonzero thermal-violation rate on air-cooled boxes is a cooling or placement problem, not a software problem; route it to facilities-aware on-call rather than the application owner.
4. **Inference memory headroom.** Alert on device memory above a safety threshold relative to peak batch size so OOM kills are prevented rather than diagnosed.

## Cost and capacity signal

1. **Treat utilization as a spend-efficiency metric.** Fleet-average SM and tensor-pipe activity weighted by card type translates directly into dollars per useful operation, and that number either justifies or kills the next hardware request.
2. **Watch queue wait alongside GPU metrics.** A fleet at 40% SM activity with a long pending queue is a scheduling problem, not a capacity problem; the two signals together prevent buying the wrong fix.
3. **Tune the dcgm-exporter counters file.** The default counters CSV is deliberately lean; enabling every profiling field multiplies series count per GPU and per MIG instance, which matters at fleet scale and belongs inside a cardinality budget.
