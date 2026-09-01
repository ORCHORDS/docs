# Dependabot Alert Triage SLA Priority

## Scope

This article covers the triage workflow, priority classes, and service-level targets for dependency vulnerability alerts: how an incoming alert gets classified, who owns it, what the clock is per class, how to suppress or accept risk deliberately rather than by silence, and how to measure whether the program works. It applies to repositories with automated dependency alerting enabled. It does not cover version-update pull requests and their merge policy, nor general dependency upgrade strategy.

## Workflow or implementation guidance

Dependency alert programs fail in one specific way: alerts arrive faster than they are resolved, the backlog becomes permanent, and the alerting channel stops carrying information. An SLA-based triage workflow exists to prevent that failure mode, and its first rule is that every alert has exactly one of four states at all times — triaged-in-progress, accepted-risk, suppressed-with-reason, or resolved — and nothing sits in a fifth, invisible state called "new."

Classify on arrival against the vulnerability and your exposure, not against the alert's severity badge alone. The badge describes the vulnerability; your classification must describe the vulnerability in your system.

**P1 — Exploitable in your runtime, or unauthenticated remotely reachable.** A reachable deserialization flaw in a library your service calls with attacker-controlled input. Clock: mitigation plan within 24 hours, resolution or documented mitigation within 7 days. Owner: the service's on-call or tech lead, immediately.

**P2 — Present in your dependency tree but reachability is plausible and unverified.** Most alerts land here. The library ships in your artifact; whether the vulnerable path executes is unknown. Clock: reachability determination within 5 business days; resolution within 30 days if reachable, downgrade to P4 if not. Owner: the owning team's backlog with a named engineer.

**P3 — Present in a development-only or build-time dependency.** Test frameworks, linters, bundler plugins. The runtime exposure is absent but the build is still a supply-chain surface. Clock: resolution within 90 days, batched into scheduled dependency work. Owner: whoever owns the build.

**P4 — Not reachable: the vulnerable code path cannot execute in your usage.** Documented, with the reasoning recorded on the alert. Clock: none for resolution, but the acceptance is revisited when the dependency's usage changes. This is the class that keeps the program honest — "not reachable" must be a written argument, not a shrug.

Triage mechanics. Every alert routes to the repository's owning team through the tracker, not through a security channel nobody watches. The triager answers three questions in order: Is the package in a shipped artifact or only in dev tooling? Is the vulnerable path reachable with the inputs we actually pass? Is there a fixed version available, and does upgrading it break anything we own? The first two determine the class, the third determines the cost, and cost never changes the class — a P1 that is expensive to fix is still a P1 with a mitigation plan, most commonly a virtual patch or a compensating control while the upgrade is scheduled.

Suppression is deliberate or worthless. Suppressing an alert requires a written reason with an expiry and an owner: "not reachable; API never invoked with untrusted data; revisit on Q3 rewrite; owner: platform team; expires: 2026-12-31." Suppress-without-reason must be technically blocked where the platform allows it, and where it cannot be blocked, it is audited monthly. The difference between a mature program and a messy one is almost entirely the quality of its suppression records.

The backlog is managed as a queue with an age dashboard, not as a list people intend to get to. Two numbers govern the program: median time-to-triage (arrival to classification) and median time-to-resolution by class. The SLA is met or missed per alert, and misses are visible. When misses cluster, the causes are structural — a team with 300 alerts and four engineers, or a critical upgrade blocked by an incompatible breaking change — and the fix is resourcing or a mitigation decision, never lowering the SLA to match performance.

Escalation and exception handling: a P1 that cannot be resolved in its window (no fixed version exists, the fix is a major-version migration) moves to a written exception with compensating controls and an executive-visible expiry date. The exception path is what keeps the SLA honest when reality does not cooperate, because the alternative to a documented exception is an undocumented one.

Finally, feed the program back into prevention. Monthly, review the highest-frequency alert sources: the same vulnerable package across many repositories indicates a shared dependency baseline problem, solvable once with an internal blessed version, rather than N times per team.

## Controls

- Every alert holds exactly one of four states: triaged-in-progress, accepted-risk, suppressed-with-reason, resolved.
- Priority classes P1-P4 with clocks: 24h/7d for P1, 5d/30d for P2, 90d for P3, documented acceptance for P4.
- Named owner per alert, routed through the owning team's tracker.
- Suppression requires written reason, expiry, and owner; suppressions audited monthly.
- Resolution-by-class and time-to-triage dashboards; SLA misses visible per alert.
- Exceptions for unresolvable P1/P2 require compensating controls and a visible expiry.
- Monthly review of repeated alert sources for baseline-level fixes.

## Validation evidence

The program is verifiable from its own records, continuously:

- Confirm every open alert in the dashboard has a state and an owner; the count in no-state is the program's true defect count and should be zero.
- Sample ten accepted-risk and suppressed alerts monthly and check each has a written reachability argument, an expiry, and an owner. Records without reasoning are the leading indicator of program decay.
- Compute per-class SLA attainment for the last quarter: percentage of alerts resolved inside the window by class. Attainment trending down while volume is flat means capacity, not process, is the constraint.
- Test the P1 path at least twice a year with a tabletop: a simulated reachable critical alert through routing, classification, mitigation decision, and exception handling, timed end to end.
- Reconcile resolved alerts with actual dependency changes in the repository — an alert marked resolved with no corresponding lockfile or manifest change is either a false state or an undeclared suppression.
- Audit suppression expiries monthly; expired suppressions still active are reopened automatically or flagged.

## Failure modes and correction

- **The permanent backlog.** Alerts age past every SLA and the channel is ignored. Correction: burn down to a managed queue deliberately — mass triage with honest P4 acceptances — then hold the arrival rate to the resolution rate by class.
- **Severity-badge triage.** Everything labeled critical is treated as critical, so real criticals hide among noise. Correction: classification is reachability plus presence, not the badge; badge-only classifications are rejected in review.
- **Silent suppression.** Alerts dismissed with no reason to clear the queue. Correction: blocking where the platform supports it, monthly audits where it does not.
- **Reachability by assertion.** "Not reachable" with no written argument, invalidated three months later by a refactor. Correction: P4 acceptance records the specific usage constraint, and dependency-usage changes reopen the question.
- **Owner-by-team-name.** Alerts owned by "backend" are owned by nobody. Correction: a named engineer per alert; team-name owners are rejected at triage.
- **SLA redefinition under pressure.** Clocks are lengthened to make the numbers look good. Correction: SLA changes are governance decisions reviewed like policy, not tuning done quietly.

## Limitations

Alert coverage is bounded by the platform's advisory database and the ecosystem's manifest formats; vulnerabilities in vendored code, container base images, or transitive runtime dependencies outside scanned manifests produce no alerts to triage, so clean dashboards do not mean clean artifacts. Reachability analysis is genuinely hard and often unverifiable without dynamic evidence; the P2 determination is a judgment call with real error bars. SLA clocks assume business-day triage capacity — a team with no security rotation will miss 24-hour P1 targets during off-hours incidents, and the honest fix is on-call integration, not aspiration. Suppression-with-expiry depends on someone acting at expiry; without automated reopening, expiries rot. The class clocks are calibrated defaults from common practice, not regulatory requirements, and regulated environments may impose stricter or different definitions.

## Canonical sources

- GitHub Docs — About Dependabot alerts: https://docs.github.com/en/code-security/dependabot/dependabot-alerts/about-dependabot-alerts
- GitHub Docs — Configuration options for the dependabot.yml file: https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file
- Git documentation — git-submodule (dependency trees spanning repositories): https://git-scm.com/docs/git-submodule
