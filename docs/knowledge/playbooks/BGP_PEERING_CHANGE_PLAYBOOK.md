# BGP Peering Change Playbook

## Purpose

Provide a reproducible procedure for adding, modifying, or retiring a BGP
peering session on an ORCHORDS-managed network edge. The procedure makes
the change evidence capture, peer pre-flight, post-change verification,
and rollback steps explicit so that a routing incident caused by an
incorrect peer or filter can be detected and reverted in minutes rather
than hours.

## Audience

Network engineers on the ORCHORDS platform team and any on-call engineer
who must supervise a vendor or transit-provider peering change.

## Pre-conditions

- Routing change ticket is open with the peer ASN, peer IP, AS-SET or
  IRR source, expected prefix policy, and the change window.
- The current BGP state for the target router has been captured
  (`show bgp ipv4 unicast summary`, `show bgp ipv6 unicast summary`,
  `show route`).
- The pre-change configuration is checked into the versioned source of
  truth; the planned delta is reviewed and approved by a second
  network engineer.
- If the change touches a public-facing peer, the IRR-derived prefix
  filter (RFC 7454) is freshly generated and committed to the
  configuration repository.

## Procedure

1. **Schedule the change.** Confirm the change window with the remote
   peer NOC, capture their contact details, and document the agreed
   start time and rollback trigger conditions.
2. **Pre-flight verification.** Verify that RPKI ROV (RFC 8205) is
   active for the target peer, that the GTSM TTL is set to 255 on
   single-hop sessions (RFC 5082), and that the max-prefix limit and
   alarm thresholds are in place.
3. **Stage the configuration.** Render the new peer block from the
   configuration source-of-truth. Validate it offline with a parser
   that knows the router's syntax; do not hand-edit running
   configuration.
4. **Capture pre-change evidence.** Archive:
   - `show bgp ipv4 unicast summary` and `show bgp ipv6 unicast summary`
   - `show bgp ipv4 unicast neighbors <peer>`
   - `show route protocol bgp`
   - The current running configuration (exported, not screenshotted)
   - The current BGP Uptime / state counters
5. **Apply the change.** Commit the configuration through the standard
   pipeline. Confirm the new session reaches `Established` state.
6. **Verify post-change evidence.** Compare the post-change summary to
   the pre-change capture. Specifically verify:
   - Established state for the new peer
   - Expected prefix count received and accepted
   - No unexpected route withdrawals on other sessions
   - RPKI `invalid` counter is zero for accepted routes
7. **Monitor for 30 minutes.** Watch the BGP dashboard for route flaps,
   dampening transitions, or unexpected community-tagged routes.
   Capture `show bgp` at 5 and 30 minutes and archive both snapshots.
8. **Communicate closure.** Update the change ticket with the
   before/after evidence and the time-to-established.
9. **Retire change artifacts.** After 24 hours of clean operation,
   retire the change evidence to the audit archive with a SHA-256
   checksum.

## Rollback procedure

If the session cannot reach `Established`, or if the post-change evidence
shows an unexpected route withdrawal, follow the rollback path:

1. **Roll back configuration.** Revert the configuration commit through
   the standard pipeline. Do not manually edit the running
   configuration.
2. **Verify pre-change state.** Confirm the BGP summary matches the
   captured pre-change evidence.
3. **Notify the peer NOC.** Provide a short summary of what changed and
   why the rollback was triggered.
4. **Open a follow-up.** Capture the failed diff in the change ticket
   and link to a remediation task so the next attempt can succeed.
5. **If the failure indicates a security event** (e.g., unexpected
   session establishment, RPKI invalid accepted, prefix count above
   the configured limit), escalate to the security on-call and
   preserve all logs and BGP captures for forensic review.

## Evidence retention

All captured evidence (configurations, BGP summaries, route dumps) MUST
be retained for a minimum of 365 days with a SHA-256 checksum recorded
in the change ticket.

## References

- RFC 4271 — A Border Gateway Protocol 4 (BGP-4)
- RFC 5082 — The Generalized TTL Security Mechanism
- RFC 7454 — BGP Operations and Security
- RFC 7908 — Incident Handling for BGP Route Leaks
- RFC 8205 — BGPsec Protocol
- RFC 8210 — RPKI Router Implementation
- RFC 9234 — Long-Lived Graceful Restart
