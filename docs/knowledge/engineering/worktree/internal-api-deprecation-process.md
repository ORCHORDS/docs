# internal-api-deprecation-process

**Issue:** An internal service team wants to delete v1 of their API. They announce it in a Slack channel, get silence, wait a month, and shut it down — breaking four downstream teams who never saw the message and one who saw it but deprioritized the migration for two quarters. Internal deprecations fail not because engineers are lazy but because there is no process: no usage data, no machine-readable signals, no migration support, and no enforcement mechanism other than hope.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The deprecation lifecycle

1. **Announce early — six months minimum for anything broadly consumed.** OneUptime's 2026 guidance and the Nordic APIs lifecycle model agree: internal consumers need a full planning cycle to slot migration work into their roadmaps. A two-week notice is not a deprecation; it is an outage with a warning label.
2. **Move through explicit stages: announced → deprecated → brownout → sunset → removed.** Each stage has entry criteria and a published date. The point of stages is that consumers can feel the approaching deadline (a brownout is a one-hour scheduled outage) instead of discovering it on removal day.
3. **Announce in every channel a consumer might touch.** The deprecation notice goes to the API changelog, the consumer teams' owners directly, the API response itself (headers), and the dashboard of any internal service catalog — not just one Slack channel that half the org has muted.
4. **Pick sunset dates by usage data, not by vibe.** If telemetry shows 40 active callers, the window is longer than if it shows three; if it shows zero, skip deprecation entirely and delete. Deciding the timeline before looking at the data inverts the process.
5. **Freeze new adopters first.** The moment deprecation is announced, the old version stops accepting new integrations (enforced by registry/review, not goodwill). A deprecation that keeps gaining consumers while counting down never converges.

## Usage telemetry before anything else

1. **No deprecation without caller telemetry.** Instrument per-consumer usage on the endpoint being retired (API gateway logs, service mesh metrics, or the Moesif-style consumer-tracking pattern). "Who calls this" is the first question every deprecation review asks; "we think the payments team maybe" is not an answer.
2. **Identify impacted consumers before the announcement, not after.** The migration plan is written for the actual list of callers with names and contact owners — an announcement addressed "to whom it may concern" transfers zero accountability.
3. **Distinguish production traffic from CI and cron noise.** A caller that only hits the endpoint in nightly tests needs a different (and cheaper) migration than one in the request path; telemetry that cannot tell them apart produces wildly wrong urgency estimates.
4. **Track the burn-down publicly.** During the window, publish a weekly "remaining v1 callers" chart visible to every consuming team and their managers. Peer-visible numbers migrate systems; polite reminders do not.
5. **Watch for new v1 traffic as a tripwire.** A rising caller count after announcement means either the freeze failed or telemetry has gaps — both are process failures to fix immediately, not consumer misbehavior to escalate.

## Machine-readable signals

1. **Use the IETF `Deprecation` and `Sunset` HTTP headers.** `Deprecation: @<timestamp>` (or versioned date form) and `Sunset: <HTTP-date>` turn every API response into a self-describing deprecation notice that client tooling, linters, and dashboards can surface automatically — no human needs to read a wiki to learn the deadline.
2. **Pair `Sunset` with a `Link` header to the migration guide.** The RFC 8594 pattern points machines and their operators directly at the replacement path: `Link: <https://internal.example/api/v2/migration>; rel="deprecation"`.
3. **Log first-use of deprecated endpoints per consumer.** The gateway emits a structured warning (one per consumer per day, not per request) so owning teams can grep their own logs and find their own deadline.
4. **Annotate SDKs and clients, not just servers.** `@deprecated since 2.4, removed in 3.0 — use sendV2()` in typed SDKs surfaces the migration in IDEs at the exact line that needs changing, which is worth more than any email.
5. **Keep old docs online but marked as sunset.** Zuplo's guidance: moving or deleting the v1 docs breaks the engineers who most need the migration guide — mark them deprecated at the top with the date and the link to v2, and archive them only after removal.

## Migration support

1. **Ship the replacement before announcing the deprecation.** Consumers must have somewhere to go on day one; "v2 coming soon, v1 dying in June" forces teams to plan around a product that does not exist.
2. **Write a migration guide that starts with the diff.** Lead with the exact mechanical change (endpoint rename, auth change, payload field mapping), then explain semantic differences. Concepts-first guides get skimmed; diff-first guides get migrations.
3. **Offer a dual-running window with behavioral parity checks.** Where feasible, let consumers run both versions and compare responses — a shadow-traffic or side-by-side mode converts "big scary migration" into a verifiable toggle.
4. **Provide runnable examples for the top three client languages.** Copy-paste curl/TypeScript/Python snippets migrate more teams than prose; the teams least equipped to migrate are exactly the ones who will not assemble the request from a spec document.
5. **Give consumers a help channel with a named human.** A #api-v2-migration channel staffed by the deprecating team (with office hours for the top consumers) is cheap insurance versus the escalation call you will otherwise take on sunset day.

## Enforcement and fairness

1. **Use staged brownouts before the final shutdown.** Schedule a one-hour v1 outage at a low-traffic hour, announce it, run it, restore service. Brownouts convert "someday" migrations into scheduled ones — they are the single most effective enforcement tool short of removal.
2. **Escalate by exception, not by default.** A consumer with a genuine blocker (regulatory freeze, staffing) can request a short, documented extension from the platform lead — an explicit exception with an owner and an end date, not silent drift.
3. **Charge unmigrated work back to the consuming team after the deadline's last extension.** Past the final date, remaining v1 callers are the consuming team's P1, on their on-call and their sprint board — the deprecating team's obligation ended with the migration window.
4. **Post-mortem every breaking consumer.** If a team breaks on removal day, the process failed somewhere: telemetry gap, unowned consumer, muted channel. Fix the process step, not just the outage.
5. **For external/public APIs, hold a higher bar.** Everything above applies doubly outside the org: longer windows, contractual notice, versioning via the URL or header, and legal review before sunset dates are published — internal speed is a privilege of shared management.

## Source URLs (verified 2026-08-15)

- https://oneuptime.com/blog/post/2026-02-02-api-deprecation/view
- https://nordicapis.com/how-to-smartly-sunset-and-deprecate-apis/
- https://zuplo.com/learning-center/deprecating-rest-apis
- https://swagger.io/blog/best-practices-for-deprecating-apis/
- https://www.moesif.com/blog/api-product-management/deprecation/How-to-Properly-Deprecate-an-API-Using-Moesif/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Sunset
