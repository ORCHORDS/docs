# swap-configuration-linux

**Issue:** Swap configuration on Linux is widely misunderstood: folklore from the 2000s ("always disable swap on servers", "set swappiness to 10", "swap must be a partition sized at 2x RAM") persists even though the kernel's memory management and the available options have changed fundamentally. Modern kernels offer zram (compressed RAM-backed swap), zswap (a compressed writeback cache in front of disk swap), and per-cgroup swap controls, and the vm.swappiness sysctl now accepts values above 100 with entirely different semantics. Misconfigured swap either wastes RAM by refusing to evict cold anonymous pages or wrecks latency by paging hot working sets to spinning disks. This article covers the current models, sizing, and per-workload guidance, informed by the 2025-2026 zram/zswap discourse.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What swap actually does now

1. **Swap holds anonymous pages, not just overflow.** Anonymous memory (heap allocations, language runtimes) cannot be dropped like page-cache; without swap the kernel's only move under pressure is OOM-killing. Swap lets the kernel evict genuinely cold anonymous pages — every long-running server has some — and reclaim that RAM for cache and active work.
2. **Swapping is not failure.** A few hundred MB of swap used on an 8 GB server is the kernel correctly deciding some startup-time allocations will never be touched again; the failure mode is thrashing — sustained high swap-in rates with falling major-fault latency — which is a different signal entirely.
3. **The three mechanisms.** Plain disk swap (file or partition) writes pages to storage; zram compresses pages into a RAM-backed block device (no disk I/O at all, Fedora default); zswap intercepts pages on their way to disk swap, compresses them into a RAM pool, and writes back only what overflows. Chris Down's widely-cited 2026 analysis argues the zswap-vs-zram choice is workload-dependent, not ideological.

## Choosing the mechanism

1. **zram alone for memory-constrained and typical servers.** zram with a fast algorithm (zstd or lz4) effectively multiplies RAM by the compression ratio at CPU cost, with zero disk I/O; Fedora ships it by default for exactly this reason. A common sizing is 50-100% of RAM as the zram device, accepting that it caps total anonymous capacity at (RAM + zram x ratio).
2. **zswap plus disk swap when you need overflow.** If workloads can transiently exceed what RAM+zram can hold and you would rather degrade than OOM, run zswap in front of a disk swap file: hot reclaimed pages stay compressed in RAM, only cold ones hit storage.
3. **Do not stack zram and disk swap naively.** The same analysis warns that running zram as a higher-priority swap device alongside lower-priority disk swap fills fast RAM with cold, stale pages while displacing usable memory — the kernel happily pages cold junk into zram and keeps it there. Pick a coherent design instead of both-at-once by accident.
4. **Disk-only swap still has two jobs.** Hibernation requires disk swap at least as large as RAM, and very latency-tolerant batch boxes can use plain files; a swap file is easier to resize online than a partition and works identically on modern kernels.

## Sizing and sysctls

1. **Size to your workload class, not folklore.** The 2x-RAM rule came from machines with 256 MB. Practical 2025 guidance: zram-sized devices at 50-150% of RAM for servers; disk swap of min(RAM, 4-8 GB) for general-purpose hosts; RAM-sized (or larger) disk swap only when hibernation is in play.
2. **vm.swappiness semantics changed.** On modern kernels swappiness is a cost ratio between reclaiming page cache and swapping anonymous pages, and values above 100 are legal: with zram, the Arch Wiki and community consensus recommend 100-180 because "swapping" to compressed RAM is cheap; with disk-only swap, 10-20 remains right for latency-sensitive servers to bias the kernel toward dropping cache instead of paging out.
3. **Watch the right metrics.** Track si/so rates and major faults per second, not the used-swap gauge; systemctl or vmstat showing steady-state zero swap-in with a full swap device is fine, while continuous swap-in under modest memory pressure is the thrashing signature.
4. **Per-cgroup control.** systemd units accept MemorySwapMax to deny specific services swap (useful for latency-critical or untrusted workloads), letting you keep global swap as an OOM safety net while pinning chosen services to RAM-only behavior.

## Operational practice

1. **Prefer swap files, managed by config.** Create them with fallocate or dd plus mkswap and swapon, declare them in fstab or a systemd unit, and let configuration management reproduce the whole setup; a forgotten partition-based swap from 2014 that is smaller than RAM is a common audit finding.
2. **Never leave zero swap on by default.** Disabling swap to "avoid slowness" trades graceful degradation for random OOM kills; even a small 1-2 GB disk swap as a pressure absorber materially improves the failure mode of memory spikes.
3. **Tune for the storage underneath.** Swap on NVMe tolerates higher swappiness than swap on SATA SSD or HDD; putting swap on network storage or slow object stores is a latency trap that converts memory pressure into system-wide stalls.
4. **Alert on thrashing, not usage.** Set alerts on sustained psi-memory pressure and swap-in rates (e.g., more than a few MB/s for more than a few minutes), and treat them as a capacity signal — if the box routinely needs swap to fit, the correct fix is RAM, not a bigger device.
