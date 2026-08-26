# internal-tooling-maintenance-policy

**Issue:** The internal tools audit finds 41 tools: 6 with active maintainers, 11 whose maintainer left the company, 9 that duplicate another tool's function, and 15 that nobody has logged into in six months. Meanwhile the actively used ones are brittle — the deploy dashboard breaks monthly because one person patches it between feature work, and the password-reset bot holds a production credential with no owner. Every team builds what it needs, nothing ever gets retired, and the security review has started asking questions the org cannot answer about ownership and patching. The org needs an explicit lifecycle policy for internal tooling: who owns what, what maintenance means, and how tools die.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The problem with default tooling policy

1. **Tools are cheap to start and expensive to keep.** The build cost is one hackathon week; the maintenance cost is dependency patches, access reviews, onboarding docs, and answering questions — forever, since no one plans sunset at creation time.
2. **Ownership evaporates silently.** The maintainer changes teams or leaves, the tool keeps running on a forgotten VM, and the first reminder it exists is a security incident or an outage. Tool sprawl is really an ownership-tracking failure.
3. **Duplication compounds.** Three request-approval tools, four dashboards, and six scripts that restart the same service — each duplicate splits the maintenance budget further and each carries its own credential surface.
4. **Unmaintained tools are a security liability, not just clutter.** The password bot with a production credential and no owner is the canonical finding: access that outlives accountability. Security reviews increasingly treat ownerless tools as blockers, not noise.
5. **The fix is lifecycle, not prohibition.** Banning internal tools pushes the work to spreadsheets and shell scripts with even less visibility. The goal is a policy under which tools are created freely, owned explicitly, maintained proportionally, and retired routinely.

## Inventory and ownership (the foundation)

1. **Everything in the service catalog, including tools.** Internal tools get the same registration as production services: name, owner (a team, never a person), business justification, data accessed, and hosting location. A tool not in the catalog is by definition unsupported and gets cut during cleanup drives.
2. **Team ownership, with a named secondary.** A person's name in the owner field is a resignation away from orphanhood; the team owns it and the team's roster provides continuity. The secondary exists so vacations do not become outages.
3. **Auto-discovery beats declaration.** Scan for running web apps, bots, service accounts, and scheduled jobs; the undeclared tools found this way are the audit's real output. Compare against the catalog quarterly and reconcile.
4. **Label the data sensitivity.** Tools touching production data, credentials, or PII get flagged at registration; the flag drives their maintenance tier and access-review cadence.
5. **Make the README the ownership artifact.** Every tool repo states: what it does, who depends on it, how it is run, and how to turn it off. "How to turn it off" is the field everyone skips and everyone eventually needs.

## Lifecycle stages and exit criteria

1. **Build (time-boxed).** New internal tools get a lightweight proposal — problem, users, data touched, and the buy alternative considered (see the build-vs-buy framework; internal-tool platforms and low-code options often win on maintenance alone). A build with no named consumer team is a hobby, and gets labeled as such.
2. **Adopt (90-day trial).** The tool runs with a real consumer team and a sunset date already set. If at day 90 it has no active users, it dies — no debate, no "let's give it another quarter."
3. **Maintain (steady state).** The tool is in the catalog with its tier, its SLA, and its maintenance budget. Usage is tracked; the exit from this stage is triggered by usage decay, not by opinion.
4. **Deprecate (announced).** When usage falls below the adoption threshold or the owner team dissolves, the tool moves to deprecated: announced in the changelog, banner in the UI, new signups blocked, and a migration note pointing at the successor. Deprecation has a fixed window (commonly 90 days).
5. **Sunset (verified).** Credentials revoked, data exported or deleted per policy, DNS and cron entries removed, and the repo archived with a closing note. The step everyone skips is verification — three months later, audit the host and accounts again to confirm it is actually gone.

## Maintenance tiers (proportional SLAs)

1. **Tier 1 — business-critical.** Tools whose outage blocks deploys, auth, or money (deploy dashboards, on-call tooling). Maintained like production: on-call coverage, error budgets, dependency patch SLAs, and CI tests on the tool itself.
2. **Tier 2 — team-critical.** Regular use, workaround exists. Reviewed quarterly, dependencies patched within normal cycles, one designated maintainer with allocated time (commonly 5-10% of a role, made explicit in planning rather than smuggled into evenings).
3. **Tier 3 — convenience.** Nice-to-have scripts and dashboards. Best-effort support only, and a strict rule: no production credentials, no PII, no single points of failure. If it needs a prod credential, it is not Tier 3.
4. **Tier assignments drive access reviews.** Credential rotation and access review cadence follow the tier, not the tool's age — this is what answers the security review's question about the password bot.
5. **Re-tier on evidence.** Usage data promotes and demotes; a Tier 3 tool that has quietly become load-bearing for the deploy process is a risk finding, and fixing it (hardening, ownership, or replacement) becomes a tracked item, not an assumption.

## Keeping the policy alive

1. **Quarterly tool review.** A 60-minute session per area: usage numbers, orphan detection results, tier changes, and deprecation decisions. Small, regular, boring — the moment it becomes a big annual ceremony, accuracy dies.
2. **Sunset budgets are planning items.** Retiring a tool costs engineer time; put it on the roadmap like a feature. Organizations that never budget for deletion are choosing to accumulate the audit debt instead.
3. **Inner-source the long tail.** Tier 3 tools can accept contributions from users (with the owning team reviewing), which keeps marginal tools alive cheaply — but the core ownership never transfers to whoever last cared.
4. **Prefer platform absorption over tool duplication.** When three teams build the same thing, the fix is not choosing a winner by politics but promoting one into the platform's golden path, where it gets real ownership (see the platform-team pattern).
5. **Report the trend, not the inventory.** Track median tool age, % with valid owners, % orphaned, and count retired per quarter. A shrinking orphans number is the policy working; a static inventory list is wallpaper.

## Related
- `build-vs-buy-decision-framework.md` (the entry gate)
- `platform-team-patterns.md` (absorption path for shared tools)
- `internal-api-deprecation-process.md` (deprecation mechanics for the interfaces tools expose)
- `secret-scanning-2026.md` (credential surface of ownerless tools)
- `tech-debt-tracking-process.md`
