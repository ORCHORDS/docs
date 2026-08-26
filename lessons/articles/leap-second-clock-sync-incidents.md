# leap-second-clock-sync-incidents

**Issue:** Software assumes time only moves forward, and the universe disagrees. At 23:59:60 UTC on December 31, 2016, the inserted leap second made Linux kernels step the clock backward, and Cloudflare's Go-based RRDNS resolver crashed globally: code computing DNSSEC RRSIG signature validity subtracted two timestamps, got a negative elapsed value because time had gone backwards, and panicked. Roughly 1% of DNS queries failed at peak until a fix (essentially an absolute value) rolled out by 06:45 UTC. The postmortem is a permanent lesson in a failure class that has nothing to do with timezone logic: system-clock synchronization itself is a dependency that can step, jump, and lie — through NTP corrections, VM live migrations, leap seconds, and misconfigured time sources — and any code doing arithmetic on wall-clock time is exposed. This is the sibling article to the timezone/DST bugs lesson: that one covers time-zone modeling errors; this one covers the physical clock being untrustworthy as an ordering or duration authority.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What the Cloudflare postmortem taught

1. **Negative durations panic.** The RRDNS bug was elapsed-time arithmetic (when does this RRSIG expire?) where a backward clock step produced a negative value that the code treated as impossible. Every "this cannot be negative" assumption about time deltas is a latent crash waiting for a clock step.
2. **The fix was one character; the outage was global.** Taking the absolute value of the delta fixed it — but the blast radius was worldwide DNS for hours. The gap between code-level triviality and incident-level severity is why clock assumptions deserve explicit review, not just bug-fix attention.
3. **The runtime shared the blame.** Go before 1.9 had no monotonic clock reading in time.Now(), so even "correct-looking" elapsed-time code silently used the wall clock. Language runtimes fixed this after the incident (Go 1.9 embedded monotonic readings in time.Time) — meaning legacy code bases carry the vulnerable pattern invisibly.
4. **Leap seconds are announced but never rehearsed.** Everyone knows the date weeks in advance; almost nobody runs their production path through a backward-stepping clock before it happens. Cloudflare's own remediation included leap-smearing their NTP infrastructure afterward — making the correction gradual instead of stepped.

## Failure patterns beyond leap seconds

1. **NTP corrections step clocks in normal operation.** A VM paused for live migration resumes with stale time and receives a hard correction; an NTP server flap can shift hosts by seconds. Any ordering, expiry, or signing logic keyed to wall time breaks on hosts, not just at year boundaries.
2. **DNSSEC and certificate validation are clock-sensitive.** Skewed hosts reject otherwise-valid signatures as not-yet-valid or expired — the same RRSIG-validity class as the Cloudflare incident, triggerable by mere drift without any leap second.
3. **Distributed ordering built on wall clocks corrupts data.** Last-write-wins registries and timestamp-indexed event stores that trust per-host clocks will silently drop or reorder records when clocks diverge. The corruption is quiet, discoverable much later, and unfixable after the fact.
4. **Positive jumps are as dangerous as negative ones.** Leasing systems (lock TTLs, rate-limit windows, session expiry) see all leases instantly expire when a host jumps forward — turning a time correction into a thundering herd of renewals.

## Prevention

1. **Monotonic clocks for duration, wall clocks only for display.** Elapsed time, timeouts, retries, and rate measurement must use a monotonic source (Go's time.Since with monotonic readings, Java's System.nanoTime, CLOCK_MONOTONIC); wall time is for human display and absolute scheduling, never deltas.
2. **Run NTP with discipline, and prefer smeared corrections.** Multiple reachable sources, monitoring of offset, and (where supported) leap-smearing so steps never appear as discontinuities to applications. Alert on clock offset like any other dependency — an host at 500ms offset is a brewing incident.
3. **Make crypto-validity code tolerant of skew.** Signature and certificate checks should accept a configured clock-skew window on both ends, and never assume now minus past is positive.
4. **Rehearse clock weirdness in staging.** Periodically step a canary host's clock backward and forward (and test through a simulated leap second) and watch what crashes. This is cheap, and it is the only way to find the RRDNS-pattern bugs before a global event does.

## Testing for clock weirdness

1. **Fault-inject time in unit tests.** A fake clock that goes backward, stalls, and jumps is as standard a test double as a fake database; any module doing time arithmetic should prove it under non-monotonic input.
2. **Assert no negative durations, everywhere.** Lint or code-review rule: elapsed-time subtraction must be either abs-wrapped or explicitly justified. The one-character fix in the Cloudflare case is the review criterion.
3. **Verify cross-host skew budgets in integration.** Tests that depend on multiple services agreeing on "now" should run with deliberately skewed host clocks (hundreds of milliseconds) to expose ordering assumptions that only manifest in production.
