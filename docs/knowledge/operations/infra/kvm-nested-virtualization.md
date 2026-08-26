# kvm-nested-virtualization

**Issue:** Nested virtualization — running a hypervisor inside a virtual machine (KVM in KVM, or a VM-based CI runner that itself launches VMs) — was long treated as a laboratory curiosity, but it has become a load-bearing part of real infrastructure: CI pipelines that boot full OS images, security sandboxes that run untrusted kernels, labs that emulate multi-node clusters on one host, and Kubernetes nodes that themselves run Kata containers or VM-isolated workloads. Enabling and operating nesting correctly requires understanding the hardware assist (Intel VMX / AMD SVM), the per-host kernel toggle, the measurable performance tax at L2, and cloud-provider support. Teams that ignore these either leave the feature off and break legitimate workloads or enable it everywhere and pay for it in production where they do not need it.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How nesting works

1. **Hardware assist exposed to guests.** KVM normally uses Intel VT-x (VMX) or AMD-V (SVM) exclusively for itself; nested mode makes the CPU's virtualization extensions available inside the guest, so an L1 guest's KVM can run L2 guests with hardware acceleration rather than binary translation. The kernel exposes this as the nested module parameter (kvm_intel nested=1 or kvm_amd nested=1, now enabled by default on most modern distributions for AMD and increasingly for Intel).
2. **The L0, L1, L2 ladder.** L0 is the physical host's KVM, L1 is the guest hypervisor, L2 is the guest's guest; every exit an L2 guest takes must be forwarded through L1 to L0 and back, which is the structural source of the overhead. Early Intel nested implementations were notoriously slow because of expensive VMCS shadowing and remapping, and upstream KVM patches through 2025-2026 have steadily narrowed that gap.
3. **Check before relying on it.** On bare metal, read /sys/module/kvm_intel/parameters/nested (or the AMD equivalent); in clouds, verify the instance family supports it — GCP allows nested virtualization on most Intel VMs, Azure supports it on specific v4+ sizes, and AWS offers it only through bare-metal instances.
4. **Not a security boundary by itself.** A nested hypervisor is still a guest to L0: resource caps, vCPU limits, and isolation are enforced by the outer host. Do not treat L1 as a trusted security perimeter for malicious tenants; nest for flexibility and testing, not to contain adversaries your outer isolation cannot already handle.

## The performance reality

1. **Expect roughly 10% or worse.** Google's own documentation for its nested virtualization feature warns of a 10% or greater performance decrease for many workloads, and real-world reports (Red Hat's testing, community forums) put CPU-heavy L2 workloads at 10-30% slower than native L1; exact numbers depend heavily on exit frequency.
2. **I/O suffers disproportionately.** Emulated disk and network paths multiply exits, so L2 storage and networking are the first things to fall over — practical reports describe poor nested disk throughput and flaky virtio behavior under load; virtio-blk/virtio-net with vhost in L1, and avoiding extra emulation layers, mitigates but does not eliminate this.
3. **Idle nesting is nearly free.** Merely enabling nested mode on a host that runs no L2 guests costs under 1%, so the decision is not "enable everywhere and pay" but "which guests actually need to launch VMs."
4. **Migration and snapshots get fragile.** Live migration of an L1 guest that is actively running L2 guests is historically unreliable (the Red Hat guidance explicitly calls out migration failures and guest crashes), and suspend/resume of a nesting guest can wedge its inner hypervisor; treat nest-heavy guests as fixed-pinning, no-live-migration workloads.

## Legitimate production use cases

1. **CI that tests real images.** Pipelines that must boot the actual OS artifact — installer tests, kernel module builds against multiple distro kernels, appliance image verification — run qemu/KVM inside a runner VM; this is the most common reason to enable nesting on CI machines (GitHub-hosted larger runners and GitLab CI both offer nesting-capable configurations).
2. **VM-based isolation inside nodes.** Kata Containers, Firecracker-based sandboxing, and similar micro-VM technologies turn every workload into a lightweight VM; running those on Kubernetes nodes that are themselves VMs requires nested virtualization, and the overhead is acceptable because the inner VMs are small and short-lived.
3. **Training, labs, and demos.** Emulating a three-node cluster with libvirt guests inside one beefy cloud VM is far cheaper than three instances; identical mechanics power home-lab-in-the-cloud setups and classroom environments.
4. **Security research.** Malware detonation, exploit development, and kernel fuzzing want disposable full systems inside an already-isolated researcher VM; nesting keeps the blast radius two layers from metal.

## Operating guidelines

1. **Enable deliberately, not globally.** Turn nesting on for the host or instance classes that need it (CI runners, sandbox nodes) via module parameter in configuration management, and leave latency-sensitive production hosts native; document which classes are nest-capable so workload placement knows.
2. **Pin resources for nesting guests.** Give L1 guests dedicated vCPUs (avoid CPU oversubscription on the host), generous memory without ballooning, and the fastest storage path available (local NVMe rather than network volumes) — nesting amplifies every contention the host already has.
3. **Prefer virtio everywhere it can chain.** L0 should expose virtio devices to L1, and L1 should expose virtio to L2, minimizing emulated hardware in both layers; avoid IDE/SATA/e1000 emulation in nested stacks unless a legacy guest forces it.
4. **Plan the escape hatch.** Because migration and hibernation are unreliable with live L2 guests, size nesting hosts for their workload, set up rebuild automation for the runners, and alert on L2 launch failures — the failure mode of a wedged nested hypervisor is often a hung guest rather than a clean error, so watchdog-based recycling of CI runners is standard practice.
