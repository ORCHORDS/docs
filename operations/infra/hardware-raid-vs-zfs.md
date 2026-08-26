# hardware-raid-vs-zfs

**Issue:** Every storage build faces the same fork: a hardware RAID controller that presents the OS a single virtual disk, or an HBA exposing raw drives to ZFS so the filesystem owns redundancy, caching, and repair. Choosing wrong is silent — ZFS running on top of hardware RAID benchmarks fine and behaves normally for months, but the controller's abstraction hides disk-level errors from the checksummer, defeats self-healing, masks SMART data, and turns bit rot and partial-drive failures into undetectable corruption. Meanwhile, hardware RAID done well still has genuine advantages in boot-volume support and vendor-tested paths. This article covers why the two models conflict, when each wins, how to structure the cache layers, and the operational practices (scrubs, SMART, spares) that make either choice safe.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why the models conflict

1. **ZFS assumes it sees the truth.** ZFS's core guarantee — end-to-end checksumming with self-healing repair from redundancy — requires direct block access to each disk. When a controller presents one virtual volume, ZFS cannot map a checksum failure to the specific mirror or parity member to repair and cannot issue targeted sector-repair operations.
2. **Controllers hide errors ZFS needs to see.** RAID controllers remap or silently fix sectors in the background, so ZFS never observes the error and its scrub statistics, error counters, and replacement heuristics operate blind; failures present as "volume vanished" or, worse, data that is silently wrong.
3. **Two layers of write caching fight.** Controller write-back cache plus the ZFS intent log creates double buffering and reordering surprises; on power loss, the interaction between controller cache and ZFS sync semantics is exactly where torn writes and corrupted pools come from.
4. **SMART and slot mapping disappear.** With a controller in RAID mode, per-disk SMART is often unreadable and mapping a failing bay to a physical disk becomes archaeology at 3 a.m. — precisely the moment it needs to be unambiguous.

## The case for HBA passthrough with ZFS

1. **Put the controller in IT/HBA mode.** Flash the controller to IT-mode firmware (LSI/Broadcom HBAs are the classic choice) or use a plain HBA, so every drive appears directly and ZFS owns everything. This is the overwhelming consensus of the TrueNAS and Proxmox communities for ZFS builds, backed by community benchmarks showing raw-disk ZFS outperforming stacked configurations.
2. **Self-healing actually works.** With raw access, scrubs detect checksum mismatches, repair from the mirror or parity member, and record per-vdev error counts — the property that distinguishes ZFS from a plain filesystem on mdadm or hardware RAID.
3. **Replacement is per-disk and online.** ZFS resilvers only allocated data, shows progress, and lets you watch error counters clear; there is no opaque controller rebuild of a virtual disk whose internals you cannot inspect.
4. **Bring your own caching.** ZFS replaces controller cache with the ARC (RAM), L2ARC (read-cache devices, safely lossable), and SLOG (sync-write accelerator, must be power-safe NVMe); losing a cache device never loses data, which is not true of a controller's write-back cache without a healthy battery.

## What hardware RAID still does well

1. **Vendor-supported boot volumes.** On mainstream server hardware, a controller-managed RAID1 pair for the OS or hypervisor boot keeps firmware, monitoring, and support in the vendor's tested path — a pragmatic split: hardware RAID1 for boot, HBA passthrough for the ZFS data pool.
2. **Opaque block devices beneath self-redundant software.** If the application provides its own redundancy (certain databases and appliances) and genuinely treats storage as an opaque block device, hardware RAID with battery- or flash-backed write cache is legitimate and well understood.
3. **Inflexibility can be a feature.** Controller RAID cannot be casually restructured from the OS shell, which some security teams prefer for boot-disk integrity; ZFS pools conversely are restructurable by anyone with root on the host.
4. **Never stack them for performance.** Despite the temptation, ZFS on hardware RAID benches slower than raw-disk ZFS in community testing while surrendering every integrity advantage — it is strictly worse than either pure option.

## Cache and durability settings

1. **Size the ARC deliberately.** The ARC consumes RAM (OpenZFS on Linux defaults to about half of system memory); on a combined hypervisor and storage box, cap it so VMs and ZFS are not thrashing each other, and treat RAM as the main performance investment.
2. **SLOG only for sync-heavy workloads.** Add a small power-loss-protected NVMe SLOG when the workload does frequent fsync (databases, NFS, zvols for VM disks); a SLOG device that lies about power safety is worse than none at all.
3. **L2ARC last.** L2ARC helps repeated random reads that exceed RAM, at the cost of write amplification and pointer overhead in RAM; add it after maximizing the ARC, never before.
4. **If a controller is unavoidable, fix its cache.** Disable write-back (or verify the battery/flash protection is genuinely healthy), leave read cache enabled, and never rely on controller cache to satisfy ZFS sync semantics.

## Operational practices

1. **Schedule monthly scrubs and read the output.** Scrubs surface latent errors while they are still repairable; alert on any nonzero checksum errors, not just pool DEGRADED state, because checksum errors on a healthy-looking pool mean the media is lying to you.
2. **Monitor SMART per disk.** Export SMART attributes (reallocations, pending sectors, media errors) for every physical disk and replace on trend, not on failure; keep the by-id slot mapping documented next to the rack.
3. **Keep hot spares or a spare-on-shelf policy.** Auto-replacing with a hot spare shortens the vulnerability window after a failure; apply the same SMART discipline to spares as to pool members.
4. **Rehearse replacements deliberately.** Run a controlled pull-and-resilver drill on every new build before production — you are testing the runbook, the slot labels, and the monitoring as much as the disks.
