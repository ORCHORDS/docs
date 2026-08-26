# ntp-time-sync-criticality

**Issue:** Time is the one dependency every layer of the stack assumes and almost nobody monitors: TLS certificate validation, Kerberos and short-lived certificate windows, JWT `exp`/`nbf` checks, distributed database consensus, and log correlation all silently break when a host's clock drifts seconds-to-minutes off. The failure presents as something else — "mysterious auth failures on a subset of hosts," "logs that don't line up during the incident review," "certificates that appear expired before their time" — and by the time anyone suspects the clock, triage has burned hours. This article covers why clocks break things, how chrony (the 2025-2026 Linux default) should be configured, time infrastructure design, and the leap-second smearing trap.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why Clocks Break Things

1. **Certificate validation assumes correct time.** A server whose clock runs ahead sees not-yet-valid certificates; one running behind sees expired ones — the symptom is TLS handshake failures on one host while every other host works fine, which looks exactly like a network or CA problem and is neither. Short-lived certificates (SSH CAs, SPIFFE IDs, tokens good for hours) shrink the tolerance window from days to minutes.
2. **Authentication protocols embed timestamps.** Kerberos rejects tickets outside a small clock-skew window (5 minutes by default), and JWT libraries enforce `exp`/`nbf`/`iat` strictly — drift manifests as intermittent login failures on specific machines, the classic "works from my laptop, fails on that cluster node" ticket.
3. **Logs become uncorrelatable.** When hosts drift apart, events reorder across machines: the database logs the error before the application logs the request that caused it, and post-incident timelines assembled from centralized logs are simply wrong; during incident reviews this costs more than any single outage, because nobody can trust the sequence of events.
4. **Distributed systems degrade or halt.** Consensus systems and clustered databases are the most sensitive consumers — Ceph monitors warn and can refuse quorum participation past their monotonic-clock tolerance, and databases using hybrid logical clocks paper over small skew but fail on steps and jumps; an NTP step mid-transaction is a genuine corruption-class event for some engines.
5. **Scheduled operations misfire.** Cron jobs, TLS renewal timers (certbot, step-ca), token refresh loops, and rate-limit windows all key off wall time; a host that jumps backward re-executes or skips work, and a host that drifts forward renews "too early" or fires jobs in the wrong order relative to its peers.

## chrony as the Standard

1. **chrony is the default on modern Linux.** RHEL-family and current Ubuntu releases ship chrony rather than ntpd, and it is the right choice in 2026: it converges faster after startup, tolerates intermittent network (laptops, spot instances, paused VMs) far better, and slews rather than steps by default — new deployments should standardize on it and treat ntpd as legacy.
2. **Slew by default, step only deliberately.** chrony gradually corrects small offsets (no jumps, so logs and timers stay sane) and steps only when the offset exceeds a threshold at startup or via `makestep` — a sane production directive is `makestep 1.0 3` (step once if off by more than a second in the first three measurements), avoiding surprise mid-flight steps while still fixing badly-off boots.
3. **Use multiple, independent sources.** The chrony project's own guidance is three or four well-synchronized, nearby servers so that one bad source is outvoted; a host syncing from a single upstream is one confused stratum away from silent drift, and a single-VM "internal NTP box" syncing from nothing is a fleet-wide time bomb.
4. **Read the state, don't guess.** `chronyc tracking` shows stratum, current offset, and estimated error; `chronyc sources -v` shows which upstreams are actually selected vs reachable-but-rejected; `chronyc sourcestats` exposes jitter per source — these three commands resolve most "is time the problem here" questions in under a minute.
5. **Give VMs and containers explicit attention.** VMs pause under live migration, snapshots, and host oversubscription, causing clock stalls chrony handles but only if running; containers should not run their own NTP daemons stacked on the host — sync the host, and let containers inherit the kernel clock (chrony inside every pod is an anti-pattern unless the pod runs as a VM-like appliance).

## Designing Time Infrastructure

1. **Run internal NTP servers as the fan-in point.** Two or three internal hosts (or your router/load-balancer tier) sync to external stratum-1/2 pools or, better, to GNSS/GPS receivers; the fleet syncs from these — this caps external dependency exposure, makes `allow` ACLs enforceable, and gives one place to verify sanity.
2. **Prefer local hardware time where accuracy matters.** A GPS-disciplined clock (or PTP where sub-millisecond matters — financial, some industrial telemetry) removes internet variance entirely; for most fleets, GPS on two internal servers plus external pool fallback is the pragmatic ceiling of rigor.
3. **Peering for clusters.** Distributed systems with strict skew tolerances (Ceph monitors, etcd-heavy nodes) benefit from syncing to the same internal sources and, where documented for the software, peering with each other — the goal is minimizing relative skew between members even if absolute offset drifts slightly.
4. **Make time a config-managed invariant.** chrony.conf belongs in your configuration management baseline with the internal server list baked in; the drift scenario that hurts is the new region / freshly-imaged appliance / forgotten legacy host that defaulted to pool servers with no monitoring.
5. **Prefer time-aware APIs where they exist.** NTP is not the only option: cloud metadata services and protocols like Roughtime provide authenticated time (protecting against a MITM feeding you wrong time to stretch certificate windows); a determined attacker controlling your NTP is a real, under-appreciated attack path for anything trust-short-lived-credentials.

## Leap Seconds and Smearing

1. **Know which convention your sources use.** At a leap second, UTC either steps (23:59:60 — the classic POSIX-hostile behavior) or gets "smeared" — spread over a day (usually noon-to-noon, ~11.6 microseconds per second in Google/AWS-style smearing) so clocks never visibly jump; both are legitimate, but mixing them across hosts in one fleet produces up to half a second of relative skew between smeared and non-smeared machines exactly at the boundary.
2. **Never mix smeared and non-smeared upstreams.** This is the canonical chrony FAQ warning: a host syncing some servers from a smearing provider and others from a stepping provider cannot converge and oscillates; pick one convention per fleet and configure every internal server to match it.
3. **Smear at the serving tier, not per host.** The clean architecture is internal NTP servers that take the leap (or smear) once and present a uniform smeared time to all clients — clients then contain no leap-specific config at all, and the fleet behavior changes nowhere except the two servers.
4. **PTP and TAI sidestep leaps.** Environments already running PTP grandmasters often operate in TAI-with-offset, making leap seconds a non-event; if your accuracy requirements justified PTP, use its time distribution consistently rather than layering NTP assumptions on top.
5. **Test before leap events.** Simulate offsets (stop chrony, `chronyc makestep` on a canary) and know your blast radius: which alerts fire, which systems log warnings; the systems that surprise you in the drill are the ones that would have failed during the real event.

## Monitoring and Pitfalls

1. **Alert on measured offset and on sync health, separately.** Export chrony's metrics (node_exporter's ntp collector or chrony exporter) and page on absolute offset beyond your tolerance (e.g., >250 ms is broken, >50 ms is a warning) and on "not synchronized / no selectable sources" — the second condition catches the host that lost all upstreams and is coasting on its drift rate.
2. **Monitor relative skew for critical clusters.** Absolute offset to UTC matters less than member-to-member skew for consensus systems; a pair of monitoring checks comparing member clocks catches the mismatch that breaks quorum while every individual host looks "fine."
3. **Beware the NTP-broken host that looks healthy.** A VM that cannot reach UDP/123 falls back to its virtual RTC or hypervisor clock and may drift slowly for weeks; monitoring must verify actual synchronization state (`chronyc tracking` sync state, not just daemon-running), because "chronyd active" is not "time correct."
4. **Firewalls and NAT eat NTP.** UDP 123 blocked by egress policy, or mangled by NAT timeout, produces exactly the silent-coasting failure above; after any network policy change, include time sync in the verification checklist alongside DNS.
5. **Clock jumps during incidents make everything worse.** The worst instinct mid-incident is manually stepping a clock (`date -s`, ntpdate) on a misbehaving host — the step invalidates caches, breaks in-flight auth, and scrambles the logs you are actively reading; always correct via chrony slewing (`chronyc makestep` only as a deliberate, understood action), and fix the underlying sync problem instead.
