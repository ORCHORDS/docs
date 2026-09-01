# Accessibility Axe Core Rules Update Cadence

Accessibility regressions slip into production because the accessibility test suite is pinned to
an old version of axe-core while the rule set underneath it evolves. Deque ships axe-core
releases on a frequent cadence, and each release can add rules, tag new rules against a different
WCAG success criterion mapping, change the severity of existing rules, or fix rule logic that
previously produced false positives. A team that never upgrades never sees new violations; a team
that upgrades blindly sees the suite go red for reasons unrelated to their own changes. The
update cadence for the rule engine deserves the same deliberate treatment as any other
third-party dependency that changes the meaning of a quality gate.

## Scope

Applies to any repository where `axe-core` (directly or through `@axe-core/playwright`,
`@axe-core/react`, `axe-selenium-java`, or `@deque/attest`) is used to gate builds or produce
accessibility reports. Covers how often to bump the rule engine, how to evaluate the delta
between versions, how to keep CI verdicts stable while the rule set changes, and how to
distinguish a genuine new accessibility defect from a rule-set change. Does not cover manual
accessibility audits, screen-reader scripting, or WCAG conformance claims beyond what automated
rules can support.

## Workflow or implementation guidance

Pin an exact version rather than a floating range. A caret range on `axe-core` means the rule set
that decides whether your build is green can change on a routine `npm install` with no commit,
no review, and no owner. Lock to a precise version in `package.json` and treat the bump as a
reviewed change:

1. Schedule the check on a fixed cadence — monthly is a reasonable default, and always
   immediately before a WCAG audit or a compliance milestone. Subscribe to the release feed for
   the axe-core repository so new versions are visible rather than discovered by accident.
2. Read the release notes before upgrading. Deque's notes enumerate added rules, deprecated
   rules, changes to rule metadata (`tags`, WCAG mapping, impact level), and bug fixes in rule
   logic. Classify each item as *additive* (new rule, new report entries), *tightening*
   (existing rule now fires more often), or *loosening* (rule logic corrected, previously
   reported issue no longer reported).
3. Run a baseline scan of the current version against a representative set of pages and capture
   the output with rule ids and node selectors. This is your *pre* snapshot.
4. Bump the version in a dedicated branch and repeat the same scan to produce the *post*
   snapshot. Diff on rule id plus impact, not on total count alone — a count delta tells you
   nothing about severity or which WCAG success criteria moved.
5. Triage the delta:
   - Violations that appear because of a new rule are real accessibility defects in the page
     that were previously unreported. File them as bugs with the rule id attached, and exclude
     them from the blocking gate only with a documented, time-boxed justification.
   - Violations that disappear indicate the earlier report contained false positives. Confirm
     the fix, then close the stale tickets so your backlog stops arguing with the rule set.
   - Unchanged rule ids with different node counts usually indicate your own page changed
     between snapshots, not the rule engine. Re-baseline before concluding anything.
6. Encode the accepted exclusions in an explicit, versioned disable list rather than inline
   comments scattered across components. Centralised configuration makes it possible to review
   the whole list each cadence and to detect exclusions that are no longer needed.
7. Merge the bump with the triage notes attached so the change history explains why the violation
   count moved. This is the artefact an auditor or a new engineer will ask for.

Keep the scanning harness stable across the bump: same pages, same viewports, same authentication
state, same waits for async content. If you change the harness and the engine in the same change
you cannot attribute the delta to either.

## Controls

- Exact version pin for `axe-core` and every wrapper package; no `^` or `~` ranges on the rule
  engine.
- A scheduled task (calendar or CI scheduled pipeline) that checks for a newer axe-core release
  and opens an issue containing the release-notes link, rather than silently upgrading.
- Baseline snapshots keyed by axe-core version, storing rule id, impact, help text, WCAG tag,
  and the violating selector, so diffs are meaningful rather than a bare integer.
- A reviewed disable list with, for each entry: rule id, reason, owning team, and an expiry or
  review date. Entries without a reason are rejected in review.
- A gate that fails the build on `serious` and `critical` impact violations and reports
  `moderate` and `minor` as non-blocking, with the severity mapping itself reviewed at each
  bump.
- Release notes for the bump committed alongside the version change.

## Validation evidence

- The pre/post scan diff, with each newly reported rule traced to a release-note entry,
  demonstrates that the engine change was evaluated rather than absorbed.
- Regression tests that assert specific known-good pages produce zero violations of a given
  impact level continue to pass after the bump, confirming the engine did not silently loosen.
- The disable list shrinks over time when rules are corrected upstream; a list that only ever
  grows is evidence the cadence is not being followed.
- Each accessibility fix lands with a test that reproduces the violation on the pre-fix build
  and passes post-fix, so the rule id is tied to a durable check rather than a one-off report.

## Failure modes and correction

- *Suite goes red immediately after an engine bump with dozens of new violations.* This is
  expected when rules are added. Correct response is triage by impact, fix or explicitly defer
  each item, and land the bump together with the triage — not to roll back the version and
  forget about it for a year.
- *Version pinned for a year, then a forced upgrade produces an unmanageable delta.* Restore the
  cadence and shorten it; break the backlog upgrade into staged bumps across releases rather
  than one giant jump.
- *Rule logic change reclassifies a violation as a pass and the team assumes the defect was
  fixed.* Cross-check disappearing violations against the release notes; if a rule was corrected
  rather than the page repaired, close the ticket with that explanation instead of claiming a fix.
- *Inline disables accumulate and nobody knows which engine version they targeted.* Migrate to
  the centralised list with a review date and remove unattributed inline disables during the
  next bump.
- *Wrapper and engine versions drift apart.* Keep `@axe-core/*` wrappers and `axe-core` itself on
  compatible releases; a wrapper bundling an older engine will silently report the old rule set
  regardless of the version in `package.json`.
- *Count-only reporting.* Report by rule id and impact. A single number invites cargo-cult
  threshold tuning that says nothing about user impact.

## Limitations

- Automated rules cover only a subset of WCAG success criteria; a stable, current axe-core pass
  is necessary but not sufficient for conformance and says nothing about keyboard-only flows,
  focus order, screen-reader announcements, or cognitive load.
- Rule sets lag and lead the standards they encode: a rule may map to a WCAG success criterion
  whose interpretation is contested, and Deque occasionally tags rules differently across
  releases. Treat WCAG mapping metadata as advisory context, not a conformance determination.
- The engine runs against rendered DOM, so results depend on the completeness of the snapshot;
  late-rendering widgets can escape a scan that samples too early.
- Frequent bumps surface more findings than a team can fix at once. The cadence manages
  surprise, not capacity — prioritisation by impact is still a human decision.

## Canonical sources

- Deque Systems, *axe-core releases* (release notes enumerating rule additions, deprecations,
  and rule-logic fixes): https://github.com/dequelabs/axe-core/releases
- Deque Systems, *axe-core rule descriptions*: https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md
- W3C Web Accessibility Initiative, *Web Content Accessibility Guidelines (WCAG) overview*:
  https://www.w3.org/WAI/standards-guidelines/wcag/
