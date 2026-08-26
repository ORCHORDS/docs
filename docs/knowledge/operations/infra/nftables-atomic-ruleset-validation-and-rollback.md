# nftables atomic ruleset validation and rollback

**Issue:** A firewall change can lock out management access or partially apply if built from unsafe imperative updates.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Build declarative nftables rulesets, validate them with the supported check mode, and load a complete transaction so accepted changes are atomic. Validation proves syntax and kernel acceptance, not that policy intent or remote access is correct.

## Controls and verification

- Preserve an out-of-band recovery path.
- Keep established management traffic during rollout.
- Apply from versioned files with exact interface and address assumptions.
- Use a timed rollback for remote high-risk changes.
- Test IPv4, IPv6, loopback, forwarding, and stateful flows.
- Inspect live rules and counters after loading.

## Sources

- [nftables wiki: Atomic rule replacement](https://wiki.nftables.org/wiki-nftables/index.php/Atomic_rule_replacement)
- [nft manual](https://netfilter.org/projects/nftables/manpage.html)
