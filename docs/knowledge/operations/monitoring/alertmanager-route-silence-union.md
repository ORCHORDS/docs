# Alertmanager Route and Silence Union Semantics

Alertmanager decides who gets paged by intersecting two independent mechanisms: routes, declared in configuration as a tree, and silences, created live via the API or UI. Both are matchers over alert label sets, but their semantics differ in ways that repeatedly surprise operators. Routes continue on sibling paths even after a child matches; silences match by the union of their matchers against alert labels, and multiple overlapping silences behave as a union of suppressed sets. Misunderstanding either produces pages that nobody silenced or silence windows that suppressed far more than intended.

## Scope

Covers Alertmanager routing-tree semantics (route matching, continuation, grouping, and the interaction of `continue`), silence matcher semantics (matchers as label equalities or regexes, intersection within a silence, union across silences), and the practical pitfalls of combining the two. Applies to Prometheus Alertmanager; Grafana Alerting's unified alerting shares concepts but is out of scope except where noted. Excludes receiver integration details, high-availability gossip, and notification templates.

## Workflow or implementation guidance

Model the semantics precisely, then test both mechanisms as configuration.

Routing semantics first. An incoming alert walks the route tree from the root: at each level, every sibling route is evaluated in order, and the first matching child is entered. By default, matching stops descending after the first matching child at each level — sibling routes after a match are skipped unless the matched route sets `continue: true`, which lets evaluation proceed to the next sibling as well. An alert therefore matches at most one path per level (or several with continuation), and the deepest matching route determines grouping, timing, and receivers. The root route must match everything and typically has no matchers. When designing a tree, put the highest-cardinality discriminator (for example, team or severity) at the first level, and remember that a route with no matchers matches everything — a common accidental catch-all when someone copies a block and deletes its matchers.

Silence semantics second. A silence is a set of matchers plus a time window. Within one silence, all matchers must all hold for the silence to match an alert — matchers intersect. Across silences, suppression is the union: if any active silence matches an alert, notification is suppressed. Two consequences follow. A silence with zero matchers matches every alert in the system, which is why the UI requires confirmation for empty-matcher silences and why such silences should never outlive a maintenance window. And the union property means overlapping partial silences can quietly cover an entire label space — silencing `team=payments` for a deploy and `severity=critical` for an unrelated incident together suppress every critical alert from every team, because each alert matches at least one of them.

Silence expiry and creation matter as much as matchers. Silences are created with a start and end time; a silence in the future is pending, not active. Authors and comments are required by good practice (and the API records them) because the audit trail is the only defense against forgotten silences. Alertmanager's federation model also matters: in a clustered Alertmanager, a silence created on one instance gossips to the others, but an alert routed to a different Alertmanager cluster entirely (for example, split by environment) is unaffected by a silence on the first.

The testing workflow: treat routing as code. Every route tree change is validated with `amtool check-config` for syntax and with unit fixtures — `amtool` can route a synthetic alert through the config and print the receivers chosen, which converts the tree into an executable specification. For silences, run a pre-change audit (`amtool silence query`) to list active silences intersecting the labels you are about to touch, and after maintenance, the same query proves the silence expired or was deleted.

## Controls

- `amtool check-config` in CI on every configuration change, plus routing fixture tests asserting receiver selection for representative alerts (including continuation cases where `continue: true` is used).
- Silence policy: required author and comment conventions, maximum default duration, and a mandatory link to the change or incident record; enforced by a creation wrapper or periodic audit.
- Scheduled silence audit job listing all non-expired silences older than a threshold, paging the author's team for renewal or deletion.
- Catch-all review: any route without matchers flagged in review; any silence with zero matchers requires incident-commander approval.
- Cross-cluster checklist item: silences verified on every Alertmanager cluster an alert can reach.
- On-call handoff includes the active silence list, so incoming engineers inherit suppression state knowingly.

## Validation evidence

Routing evidence: `amtool` output showing a synthetic alert with a given label set resolving to the expected receivers, run against the proposed configuration in CI — filed with the pull request. Silence evidence: `amtool silence query` output before and after the maintenance window, showing the silence's matchers, window, author, and then its expiry; plus a test alert fired during the window confirming it was suppressed, and a second alert with labels outside the matchers confirming it paged. Together these prove both the union behavior you rely on and the boundaries you expect.

## Failure modes and correction

- Page during a silence: the alert reached a different Alertmanager cluster, or a label value mismatched (regex matchers are anchored; a substring expectation becomes an anchored pattern miss). Verify with `amtool silence query` against the alert's exact labels on the cluster that dispatched.
- Silence suppressed too much: overlapping silences' union swallowed adjacent alerts. Split into narrower silences and add an explicit label to the maintenance target so the silence matches that label alone.
- Alerts to the wrong receiver: a no-matcher catch-all route earlier in order captured them. Fix ordering or add matchers; the routing fixture test encodes the expectation so it cannot regress silently.
- `continue: true` double-pages: an alert matched two sibling routes and both receivers fired. Confirm intentional; if not, remove continuation or make matchers mutually exclusive.
- Forgotten silence mutes an incident: expiry audit caught it late. Shorten durations and require renewal instead of long windows.
- Inhibition rules interacting with silences confuse triage: inhibition happens at notification time like silences; reproduce the full label set in a test alert to see the effective outcome.

## Limitations

Matcher semantics have tightened across Alertmanager versions, including UTF-8 name handling and the deprecation of loose matcher forms; behavior depends on the deployed version, so its configuration reference governs. Silence state is cluster-local: there is no global silence across independent Alertmanager deployments, and no cross-vendor propagation. The routing fixture approach tests declared cases only — label spaces not covered by fixtures remain untested. This article does not cover Grafana Alerting's receiver and mute-timing model, which is similar in spirit but distinct in configuration. Finally, silence audit tooling depends on API access that some locked-down deployments restrict.

## Canonical sources

- Alertmanager configuration reference (routing, matchers, continue, inhibition): https://prometheus.io/docs/alerting/latest/configuration/
- Alertmanager overview (silences, notification pipeline): https://prometheus.io/docs/alerting/latest/alertmanager/
