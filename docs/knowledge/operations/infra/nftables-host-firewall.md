# nftables-host-firewall

**Issue:** iptables has been deprecated in favor of nftables across every major distribution — Debian, RHEL, and Ubuntu all default to nftables backends, and firewalld, libvirt, Docker, and Kubernetes tooling now build on it — yet production hosts still carry years of hand-written iptables rules that must eventually migrate. Running both toolkits naively produces two competing rule sets in the kernel with unpredictable precedence, and teams that defer migration accumulate risk on a deprecated tool with shrinking community knowledge. This article covers why the migration is happening, the nftables model, a sane host-firewall design, how to convert legacy rules safely, and how to coexist with the container platforms that also program nftables.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why iptables is being retired

1. **One framework for everything.** nftables replaces iptables, ip6tables, arptables, and ebtables with a single subsystem, ending the divergence where IPv4 and IPv6 rules lived in separate tools and quietly drifted out of sync.
2. **Atomic updates and native sets.** Rules load atomically (no mid-update window where half a ruleset is applied), and native sets and maps replace long linear chains of near-duplicate iptables rules — faster to evaluate and dramatically more readable.
3. **Performance at scale.** Set lookups and concatenations let the kernel classify traffic in constant time instead of walking rules one by one, which matters on hosts carrying thousands of CIDR or port entries.
4. **The compatibility shim has limits.** The iptables-nft shim translates legacy syntax into nftables rules, but mixing manual nftables with iptables-nft creates two owners of the same hooks; the destination is native nftables everywhere, and the shim is a migration tool, not a resting state.

## Core concepts

1. **Tables, chains, hooks.** A table groups chains; chains attach to hooks (input, forward, output). The inet family applies one ruleset to IPv4 and IPv6 together, which is the default recommendation — write each rule once and cover both protocols.
2. **Base chain policies.** Set the input base chain policy to drop with an explicit early accept for established and related connections; everything else must be enumerated. Default-deny on hosts is table stakes.
3. **Sets and concatenations.** Group trusted CIDRs, admin sources, and service ports into named sets that rules reference; updating access becomes editing the set, which is cheap enough to automate from inventory data.
4. **Stateful filtering.** A conntrack accept for established,related traffic at the top of input keeps return traffic fast and the ruleset small; stateless allow-all rules for port ranges are an anti-pattern.

## Host firewall design

1. **Loopback and management first.** Accept loopback, accept established, then a tightly scoped rule for SSH and management restricted to a bastion or VPN CIDR set — never the whole internet on port 22 where it can be avoided.
2. **Enumerate services, default-drop the rest.** Each deployed service gets one allow rule referencing a named set, so the ruleset doubles as machine-readable documentation of exactly what the host exposes.
3. **Rate-limit and log judiciously.** Use the limit matcher for new-connection floods on exposed ports and a low-rate log rule with a prefix for dropped input; unbounded logging of drops is a disk and noise hazard.
4. **Version-control the ruleset.** Ship nftables.conf through configuration management so hosts rebuild identically — the file is the source of truth, loaded atomically at boot and on change, not imperative commands run by hand.

## Migrating from iptables safely

1. **Translate, do not rewrite from memory.** The iptables-restore-translate and iptables-translate tools convert existing rules mechanically; review the output rather than hand-porting, because transcription mistakes are the top migration risk.
2. **Stage with a safety timer.** Test the candidate ruleset on a canary cohort, or enable it with a scheduled rollback timer, so a management rule that locks you out self-heals instead of requiring console access.
3. **Verify equivalence with counters and drop logs.** Run the translated ruleset with per-rule counters alongside the old one and diff hit counts before enforcing drop policies — behavioral equivalence is proven, not assumed.
4. **Retire old tooling explicitly.** After cutover, remove legacy iptables save/restore units and any leftover ufw or firewalld configuration so nothing races nftables at boot; a host should have exactly one firewall owner.

## Coexistence with platform firewalls

1. **Know what Docker and Kubernetes do.** Docker generates its own nftables rules with forward-drop policies, and Kubernetes kube-proxy plus NetworkPolicy also program the packet filter; do not fight them from your host ruleset — scope host rules to the input hook and leave forward to the platform.
2. **Firewalld for dynamic hosts.** On systems needing runtime-defined zones (libvirt guests, roaming laptops, VPN changes), firewalld on its nftables backend is a sound management layer; pick either firewalld or raw nftables per host, never both.
3. **Respect hook priority.** When multiple subsystems inject rules (firewalld, libvirt, your custom table), ordering at the same hook follows priority values; keep custom tables at a priority that cannot preempt security drop rules.
4. **Test with production rigor.** Validate syntax with nft check-mode before loading, integration-test in CI with containers or VMs, and include IPv6 in every test — the most common post-migration hole is an inet ruleset that accidentally omits v6 allow rules.
