# third-party-api-changes-break-silent-integrations

**Issue:** A vendor changes an API you depend on — deprecates an endpoint, alters a field's format, or silently changes query-parameter semantics — and your integration doesn't crash, it just quietly does the wrong thing: empty results, truncated syncs, zeroed metrics. Real incidents include a CrowdStrike API filter-behavior change that silently dropped a customer's ingestion to ~3,000 active devices without a single error, and Microsoft's December 2025 removal of a Teams third-party API that broke dependent products on a vendor's schedule, not theirs. This article captures why external API changes are an outage class of their own and the defenses (contract tests, deprecation monitoring, pinning) that catch them before customers do. Industry data from 2025-2026 suggests proactive API change management cuts update-related incidents by roughly 70%.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the silent breakage unfolds

1. **The vendor ships a "non-breaking" change that breaks you anyway.** A field that always returned an array starts returning an object when it has one element; an ID switches from numeric to string; nulls appear where empty strings used to. None of this trips a version bump, and your deserializer either fails mysteriously downstream or — worse — coerces and corrupts.
2. **The deprecation notice never reaches an engineer.** The vendor announced the sunset in a changelog, a forum post, or an email to the account owner, none of which routes to the team that owns the integration. The deprecation window expires while the announcement sits unread, and the shutdown date arrives as a surprise outage.
3. **Nothing monitors for semantic drift, so absence looks like success.** The endpoint keeps returning 200s — with fewer records, new default pagination, or different filter behavior. Your health checks pass, your dashboards show the job "completed", and the data loss is discovered weeks later by a business user who notices a report looks wrong.
4. **Version pinning rots into forced emergency upgrades.** The integration was pinned to `v2` years ago; the vendor now sunsets v2 with a 90-day window. The team must upgrade across years of accumulated API drift under deadline pressure — the exact conditions guaranteed to inject new bugs.
5. **The emergency fix trades correctness for uptime.** Under incident pressure, the team hot-wires the new API shape with broad exception handlers and default values, restoring uptime while encoding new silent-failure paths. The follow-up hardening ticket is deprioritized, and the next vendor change finds the same hole.

## Root causes

1. **"Integration works" is treated as a project, not a service.** The connector is built once with a spike of effort, then left unowned; nobody is accountable for watching the vendor's roadmap, and the code has no tests that would notice behavioral change. External dependencies require standing ownership, not one-time wiring.
2. **Happy-path integration tests give false confidence.** Tests that assert "response contains field X" pass even when X's meaning changes; tests against recorded fixtures keep passing while the live API evolves away from the recording. The test suite verifies the contract of the past, not the present.
3. **Deprecation signals arrive in channels engineering doesn't watch.** Sunset headers in responses, `Deprecation`/`Sunset` HTTP headers, changelogs, developer forums, and account emails are the vendor's official notification channels — and none of them are in the on-call's field of view. Unwatched notification is functionally no notification.
4. **Data-completeness has no invariant to violate loudly.** If nothing asserts "we ingested between N and M records today" or "this sync's checksum matches the source", then truncation and filtering changes are invisible by construction. Silent failures require silent observability to persist.
5. **Single-vendor coupling has no circuit breaker.** When one third party's change can take down a core flow, the blast radius was designed in — via hard coupling, no fallback, and no degradation mode. The vendor's release calendar becomes your availability ceiling.

## Defenses: catch it before customers do

1. **Run consumer-driven contract tests against the live API on a schedule.** Nightly or weekly, replay a small suite of real request/response assertions against production vendor endpoints (in addition to fast fixture-based tests in CI). Pact-style contract verification catches drift within a day instead of within a quarter.
2. **Assert semantics, not shape.** For each critical field, test the meaning: record counts within expected ranges, referential integrity after sync, known values for a canary record, monetary totals reconciling against an independent source. Shape tests catch breakage; semantics tests catch corruption.
3. **Alert on volume and completeness invariants.** Define expected bounds for records synced, bytes transferred, and entities matched per run; page a human when a run lands outside them. This is the control that would have caught the silent-ingest-truncation class of incident on day one.
4. **Monitor the deprecation channels programmatically.** Capture and diff `Sunset`/`Deprecation` response headers on canary calls, subscribe the team (not the account owner) to the vendor's changelog RSS/release notes, and grep release notes for your used endpoints quarterly. Route findings into the normal backlog with lead time, not into an inbox.
5. **Log and alarm on schema drift in responses.** A schema-observation layer (JSON Schema inferred per endpoint, diffed over time) turns "field silently became nullable" into an alert instead of a downstream null-pointer weeks later. The diff is also the evidence base for a controlled upgrade.

## Vendor change management

1. **Maintain a used-surface inventory per vendor.** A machine-readable list of endpoints, fields, and parameter semantics you actually consume — reviewed each quarter — is what makes vendor release-note triage a 10-minute task instead of an archaeology project.
2. **Prefer vendors that version loudly and run parallel versions.** Vendors offering overlapping old/new version windows let you migrate on your schedule; guidance from the deprecation-playbook literature is consistent that maintaining a deprecated version slightly longer is cheaper for everyone than a forced hard cutover. Make migration windows a selection criterion.
3. **Negotiate and document notice periods.** For paid/enterprise APIs, get deprecation notice commitments (e.g., 180 days) in the contract, and calendar them. For free APIs, assume zero notice and compensate with the monitoring above.
4. **Upgrade on a cadence, not on a cliff.** Schedule deliberate upgrade passes every 1-2 quarters so each delta is small and testable; a standing "keep current" cadence is what keeps the eventual forced migration from being a rewrite under fire.
5. **Design a degradation mode for every core integration.** Decide in advance what the system does when a vendor goes away or changes: cached last-good data, feature-limited fallback, queue-and-retry, or a clear user-facing "vendor integration degraded" state. The Teams-API-style removals show that even major vendors will cut features on their schedule — the outage is optional, the change is not.
