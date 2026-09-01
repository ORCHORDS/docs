# AI Review Comment Triage Workflow

## Scope

This article covers the operating procedure for triaging comments left by AI code review bots on pull requests: how to classify them, who decides what happens next, how quickly each class must be answered, and how to stop the bot from drowning human reviewers in low-value noise. It applies to any repository where an automated reviewer posts inline comments alongside human reviewers, and it assumes the bot is advisory, not blocking. It does not cover how to build or configure a review bot, how to write prompts for code-generation assistants, or how to run human review checklists — those are separate concerns.

## Workflow or implementation guidance

The core rule is that an AI comment is an input to a decision, never the decision itself. Every comment gets classified into exactly one of four buckets, and the bucket determines the response and the clock.

**Bucket A — Valid and blocking.** The comment identifies a real defect that would fail human review anyway: an unhandled error path, a missing authorization check, a breaking API change, a data-integrity risk. Action: fix on the branch, reply to the comment with what changed, and link the fixing commit. The human reviewer confirms resolution.

**Bucket B — Valid and non-blocking.** The comment is correct but cosmetic or stylistic: naming suggestions, doc phrasing, a test that could be table-driven. Action: either apply it in the same PR if it takes under five minutes, or open a follow-up issue and reply to the comment with the issue link. Never leave it silent — silent acceptance trains readers to ignore the bot.

**Bucket C — Invalid but plausible.** The comment is wrong on the facts — it misread the control flow, proposed an API that does not exist, or flagged a pattern that is intentional and documented. This is the most important bucket to handle well. Action: reply with the specific reason it is wrong, in one or two sentences, citing the code line or document that contradicts it. If the same invalid comment reappears across PRs, feed the pattern back into the bot's ignore rules rather than answering it every time.

**Bucket D — Noise.** Duplicate comments, comments on generated files, comments about lockfiles, or restatements of what the linter already enforces. Action: resolve without reply, and add a path filter so the bot stops reading generated files.

Triage ownership follows the author. The PR author owns all four buckets for their own pull request; reviewers may re-open a Bucket C if they disagree with the dismissal, and that disagreement is settled in the human review, not by re-litigating with the bot. This keeps the accountability chain human.

Timing discipline matters more than perfection. Adopt a simple service level: every AI comment is answered — fixed, ticketed, rebutted, or resolved — before the PR leaves "Changes requested" or before the author requests re-review, whichever comes first. A PR merged with unanswered AI comments is the failure signal, not a PR with rebutted ones. Track two numbers weekly: the percentage of AI comments answered before merge, and the ratio of Bucket A plus B to total comments. If that ratio drops below roughly one in five, the bot configuration is the problem, not the reviewers.

A practical safeguard for large PRs: cap the bot's comments per PR in its configuration. Most review bots expose a max-comments or severity threshold. Twenty well-chosen comments get triaged; two hundred get bulk-resolved, which is worse than having no bot because it manufactures false confidence that the code was reviewed.

Finally, keep the audit trail in the PR thread itself. The reply to each comment is the record of why the suggestion was accepted or rejected. Do not move these discussions to chat, because the PR is the artifact a future maintainer reads when the same pattern appears again.

## Controls

- The bot runs as a required check that reports "comments posted" but never "merge approved." Merge authority stays with human review and branch protection.
- Bot configuration lives in version control with review by the platform team; a change to the bot's rules is itself a PR with a human reviewer.
- Path filters exclude generated code, vendored dependencies, lockfiles, and snapshots from bot review.
- A per-PR comment cap prevents flooding on large refactors.
- A monthly review of the most-repeated Bucket C comments feeds ignore rules or prompt improvements back into the bot.
- PR templates include a short triage checklist: classify, respond, resolve, merge-ready.

## Validation evidence

Verification for this workflow is observational rather than a one-off test. Confirm the following on a rolling basis, and treat any gap as a defect in the process rather than in the people:

- Sample ten merged PRs per month and check that every AI comment has a terminal state: a fixing commit reference, a follow-up issue link, a written rebuttal, or an explicit resolution. Unanswered comments in merged PRs should trend to zero.
- Compare Bucket A findings with findings raised later by human reviewers or production incidents. An AI comment classed as blocking that a human reviewer confirms is a genuine catch; a Bucket C dismissal followed by a defect in the same area is a triage miss and deserves a retro.
- Track the volume ratio of AI comments to PR size (comments per hundred changed lines). A rising ratio with a flat Bucket A plus B share means the bot is getting noisier, not better.
- Run the bot against a small set of known-defect benchmark PRs periodically. If a defect the bot previously caught stops being caught after a configuration change, the change regressed the bot.

## Failure modes and correction

- **Bulk dismissal.** A reviewer resolves all comments in one click to unblock CI. Correction: remove the resolve-all affordance from the workflow by making AI comments advisory-only in configuration, and review the last two weeks of bulk resolutions to rebuild the habit.
- **Author deference.** Authors accept Bucket C suggestions they do not understand, producing code nobody can explain. Correction: require a one-sentence justification in the reply for every accepted suggestion; reviewers challenge justifications that only restate the suggestion.
- **Reviewer abdication.** Humans stop reading because "the bot already looked." Correction: keep the bot's verdict out of merge requirements, and periodically review a PR with the bot disabled to calibrate what human review still catches.
- **Configuration drift.** Someone widens the bot's scope to hit a coverage number and generated files flood in. Correction: path filters and comment caps are code-reviewed changes, not local edits.
- **Silent repeats.** The same invalid comment appears on twenty PRs and twenty people answer it independently. Correction: a standing agenda item that promotes repeated Bucket C patterns into ignore rules.

## Limitations

This workflow assumes the bot's comments are visible to all reviewers and preserved in the PR record; bots that post private summaries to the author break the shared-audit-trail assumption. It assumes advisory-only behavior — if the bot can block merges, the triage rules need an escalation path this article does not define. Effectiveness metrics here are process metrics, not quality guarantees: a fully triaged PR can still contain defects the bot and reviewers both missed. The bucket ratios and response targets are calibrated defaults, not research-derived numbers, and teams with very large refactors or heavily generated codebases will need different caps. Nothing here substitutes for the human review tiers defined in the code review checklist.

## Canonical sources

- GitHub Docs — About pull request reviews: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/about-pull-request-reviews
- GitHub Docs — About protected branches and required status checks: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- Git documentation — git-commit (message and change auditing practices): https://git-scm.com/docs/git-commit
