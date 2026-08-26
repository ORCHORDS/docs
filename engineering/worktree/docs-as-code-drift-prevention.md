# docs-as-code-drift-prevention

**Issue:** Docs-as-code — storing documentation as Markdown next to source, reviewing it in pull requests — solved the workflow problem but not the decay problem. Documentation drift, the slow divergence of written guidance from the code it describes, now has CI-native tooling aimed directly at it: Vale for prose linting, link checkers, freshness scoring pipelines that grade staleness on every PR (Dosu published a 0-100 freshness scoring approach), and anchor-based linters like Fiberplane's Drift that bind Markdown claims to code symbols via tree-sitter and git history so CI fails when the two disagree. The 2025-2026 wave extends this with AI "doc-sentries" that flag PRs whose code changes plausibly invalidate nearby docs. The engineering problem is choosing which of these mechanisms to wire into CI, who owns the resulting failures, and how to keep the cure cheaper than the disease.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Detection mechanisms in CI

1. **Prose linting with Vale.** Vale enforces style, terminology, and banned phrases in CI exactly as a linter treats source. Configured per-repository with a shared style directory, it stops the slow fragmentation of voice and vocabulary that makes docs feel unmaintained and encourages readers to distrust them.
2. **Link checking as a scheduled job.** Intra-repo links can be checked on every PR, but external links need a nightly or weekly workflow so a single dead URL does not block unrelated merges. Failures route to the owning team through the same triage channel as flaky tests.
3. **Freshness scoring on every PR.** A freshness signal —Dosu's writeup describes a 0-100 score combining last-reviewed date, code-churn near the doc, and reader traffic — surfaces the most rotted pages automatically. Score, do not block: a freshness number on the PR dashboard changes writer behavior without turning CI red.
4. **Anchor docs to code symbols.** Tools such as Fiberplane's Drift bind a Markdown statement to the code element it describes; when that element changes in a commit, CI flags the doc as suspect. This converts drift from a vibes problem into a diff problem.
5. **Generated-reference discipline.** API references should be generated from OpenAPI specs or doc comments so they can never drift by construction. Hand-written pages then only cover what generation cannot: rationale, workflows, and operational guidance.

## Ownership and workflow

1. **Co-location with the code it describes.** A doc lives in the same repository and preferably the same directory as the system it documents, so any change that might invalidate it appears in the same diff and the same review. Docs in a separate wiki are docs destined to rot.
2. **CODEOWNERS for documentation paths.** Route doc changes to the people who can verify accuracy, not whoever is online. When docs sit in-repo with ownership rules, the review that approves a behavior change also covers its documentation.
3. **A definition of done that includes docs.** The PR template asks: does this change alter a user-visible or operator-visible behavior? If yes, the doc delta belongs in the same PR or in a linked, tracked follow-up issue — never in neither.
4. **Freshness labels with expiry semantics.** Every operational doc carries a last-verified date and an owner. A page older than its stated review horizon (90 days for runbooks, 180 for guides) renders with a stale banner until someone re-verifies and bumps the date.
5. **Delete aggressively.** The cheapest drift fix is removal. Docs describing decommissioned systems, superseded processes, or one-off migrations should be archived on sight; a smaller corpus is a more trustworthy corpus.

## Guardrails against over-tooling

1. **Warn before you block.** Ship freshness scores, Drift-style anchors, and prose lint results as advisory checks for a quarter before making any of them merge-blocking, then only for the checks whose precision you have observed. A CI that fails constantly on docs gets disabled entirely.
2. **Budget maintenance like a dependency.** Reserve a recurring slice of team capacity (the same argument used for refactoring budgets) for doc re-verification driven by the freshness report, so the work is planned rather than aspirational.
3. **Let AI triage, not author blindly.** Use AI doc-sentries to draft "this PR likely affects X.md" comments and proposed updates, but require a human who understands the change to approve. Unreviewed AI-written docs drift in a new way: confidently and at scale.
4. **Track one drift metric.** Choose a single number — median freshness score across operational docs, or percentage of PRs flagged as doc-affecting that included a doc change — and review it monthly. The metric exists to justify the tooling, not the reverse.
5. **Keep runtime docs generated from the system itself.** Runbooks that can embed live values (current alert names, dependency versions, dashboard links) should interpolate them from configuration at build time, eliminating an entire class of copy-paste drift no linter can catch.
