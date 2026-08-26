# filesystem-selection-ext4-xfs

**Issue:** Choosing between ext4 and XFS looks like a bikeshed decision until the wrong choice bites a production workload: a database that cannot shrink a volume after over-provisioning on XFS, a large-file media pipeline that crawls on ext4's single-block allocation, or a backup volume whose fsck window after an unclean shutdown stretches into hours. The two filesystems have genuinely different performance envelopes, online-operation support, and failure characteristics, and unlike a package choice this one cannot be changed after data is written without a full copy. Every server role (OS root, database data, object storage backing, log spool) deserves a deliberate pick, recorded alongside the provisioning code, not inherited from whatever the cloud image defaulted to.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Performance envelopes

1. **XFS owns large-file and parallel-write throughput.** Allocation groups let XFS place and write multiple streams in parallel across large devices, which is why it is the default in RHEL and why benchmarks consistently show it winning on sequential throughput for multi-hundred-GB files, video pipelines, and backup images. It supports files up to 16 EiB, far beyond ext4's limits.

2. **ext4 wins on latency stability and small-file churn.** ext4's lower per-operation overhead keeps it responsive under heavy mixed I/O, and directories with millions of small files (mail spools, cache tiers, package mirrors) historically behave more predictably on ext4. Linux Community benchmarking through 2025 still shows ext4 with the lowest latency floor under heavy generic load.

3. **Neither has data checksums.** Unlike ZFS or Btrfs, neither ext4 nor XFS detects silent bit rot on data blocks; metadata journaling protects consistency, not content. On commodity SSD fleets this argues for application-level checksums or periodic scrubbing regardless of which of the two you pick.

4. **Benchmark your workload, not the filesystem.** Allocation behavior interacts with RAID stripe size, SSD page size, and write pattern; a half-day with fio on a representative volume beats any internet benchmark table.

## Operational capability differences

1. **XFS cannot shrink, only grow.** This is the single most operationally decisive difference: an XFS volume can be extended online (xfs_growfs) but never reduced, so any over-provisioned XFS volume requires a full data migration to reclaim space. ext4 supports both online grow and offline shrink.

2. **Both grow online, differently.** ext4 grows with resize2fs after a partition or LV extension; XFS grows with xfs_growfs mounted and active. Both are routine, but only XFS makes shrink impossible, so provision XFS tight and grow, never generous.

3. **Repair characteristics differ.** xfs_repair requires the filesystem unmounted and generally runs fast but simply resets what it cannot reconcile; ext4's e2fsck can take a long time on huge volumes after an unclean shutdown but is more conservative. Neither is a substitute for backups; both are consistency tools.

4. **Snapshots depend on the layer below.** Neither filesystem has native snapshots; LVM thin snapshots, the cloud provider's volume snapshots, or ZFS underneath are the standard answers, and XFS in particular requires a consistent freeze (fsfreeze) for crash-consistent block-level snapshots.

5. **Project quotas and reflinks.** XFS supports project quotas and has first-class reflink (copy-on-write file clones), which backup tools and container snapshot layouts exploit; ext4 gained reflink support only in recent kernels and it is far less battle-tested there.

## Workload-to-filesystem mapping

1. **OS root volume: ext4.** Root volumes want maximum compatibility, easy rescue-mode tooling, and the ability to shrink during migrations; every installer and recovery guide assumes ext4. Default here is a feature.

2. **Database data (PostgreSQL, MySQL): XFS, aligned.** RHEL ships XFS as the database default for a reason: large sequential WAL/write-ahead files and parallel allocation map well onto allocation groups. Format with su and sw set to the RAID or SSD stripe geometry so allocations align with the hardware stripe.

3. **Object storage and media: XFS.** MinIO and similar object stores explicitly document XFS as the recommended backing filesystem, and large-file throughput is the whole job.

4. **Log and cache spools: ext4.** Millions of small append-heavy files with constant creation and deletion favor ext4's directory handling, and the volumes are cheap enough that shrink support matters more than peak throughput.

5. **Virtualization hosts: XFS for image stores.** Disk images are large append-mostly files; combined with reflink, cloning VM images becomes near-instant where the hypervisor supports it.

## RAID and alignment practices

1. **Align XFS allocations with the stripe.** Pass su (stripe unit) and sw (stripe width) to mkfs.xfs, or let it auto-detect on MD and device-mapper arrays; misaligned allocations cause read-modify-write storms on parity RAID.

2. **Set ext4 stride and stripe-width equivalents.** mkfs.ext4 accepts stride and stripe-width for the same purpose on RAID 5/6; on plain SSDs and RAID 10, defaults are fine.

3. **Reserve lazy initialization and discard policy at mkfs time.** Decide -K (no discard) versus fstrim.timer cadence when formatting; redoing either later on a multi-terabyte volume is a maintenance event, not a tweak.

4. **Record the mkfs arguments in provisioning code.** Whether Terraform, Ansible, or a bootstrap script, the exact mkfs command with its alignment flags belongs in version control next to the volume definitions, because a filesystem recreated during disaster recovery must match what monitoring and tuning expect.
