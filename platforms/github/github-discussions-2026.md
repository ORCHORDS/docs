# github-discussions-2026

**Issue:** The repo's issue tracker drowns in questions, feature ideas, and "any update?" bumps — none of which are actionable bugs. Issues get closed as "not a bug", users feel dismissed, and maintainers lose the signal. GitHub Discussions is the designated home for this traffic, but enabling it with the default six categories and no moderation plan just moves the noise: questions go unanswered in the wrong category, duplicates pile up, and nobody has permission to tidy up. A governance layer (categories, roles, conversion flows, moderation habits) is what separates a Discussions instance that compounds knowledge from one that decays.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Enabling and structuring

1. **Enable per repo or org-wide.** Repository Settings → General → Features → Discussions. For org-level discussions, enable on an org-owned repo and choose "Organization" scope in the announcement banner — org discussions host cross-repo topics (governance, RFCs, community) instead of repeating setup per repo.
2. **Default categories and formats.** The starter set is Announcements (announcement format, maintainers-only posting), General / Ideas / Show and tell (open-ended), Polls (poll format), and Q&A (question-and-answer with mark-as-answer). Each category's format controls the interaction model — Q&A enables accepted answers; polls require vote options; announcements are one-to-many.
3. **Limit 25 categories, unique emoji+name.** A repo/org can have at most 25 categories, each a unique emoji-and-name pair. Categories can be grouped into sections (max one section per category) — use sections like "Support", "Ideas", "Meta" so the sidebar scans.
4. **Ruthless category design.** Categories should map to distinct moderation postures: Announcements (locked-down broadcast), Q&A (answerable, dedupe-heavy), Ideas (triage into roadmap), Show and tell (low-touch celebration). If two categories have the same moderation posture, merge them.
5. **Discussion category forms.** Like issue forms, YAML category forms can structure inputs for chosen categories — put them in `.github/`/`docs` of the `.github` repo to inherit org-wide (see `github-community-health-files.md`).

## Roles and permissions

1. **Base permissions.** Anyone who can view the repo can open a discussion in non-announcement categories and comment; write permission is not required. Only maintain/admin users can post in announcement categories (anyone can reply).
2. **Promote trusted community members.** Repo admins can promote any participant to category moderator or maintainer from their discussion comment's context menu — granting delete/lock/transfer within Discussions without granting repo write. This is the main lever for scaling moderation.
3. **Triage roles match repo permissions.** Users with triage permission can act as category maintainers (edit titles, pin, lock, convert) — a good sandbox before full write access.
4. **Answer authority in Q&A.** The discussion author or a maintainer can mark one reply as the answer; maintainers can unmark. Encourage answer-marking culture — it's what makes Q&A searchable knowledge instead of meandering threads.
5. **Spam and abuse handling.** Report-abuse is available on every discussion/comment for routed escalation; combine with org-level moderation tools rather than ad-hoc deletion when conduct, not content, is the problem.

## Issue↔discussion lifecycle

1. **Convert issues to discussions.** From an issue sidebar, "Convert to discussion" moves it (author preserved, issue auto-redirects) into a chosen category — default a "Questions" label rule so closers reach for conversion instead of lock. Converted issues keep their timeline as comments.
2. **Converting preserves history and redirects.** The old issue URL redirects to the new discussion, so inbound links don't rot — safe to convert even heavily-linked issues.
3. **Promote discussions to issues.** When an Idea matures, "Convert to issue" (or reference it) turns the discussion into a tracked issue — the funnel is issues→discussions for support traffic, discussions→issues for validated work.
4. **Transfer between repos.** Discussions can be moved to another repo's discussions (except announcements); used with org discussions to relocate misfiled cross-repo threads without deleting content.
5. **Templates route at creation time.** Point issue templates' "guidance" links at Discussions categories and vice versa so users self-select the right tracker before a maintainer has to move them.

## Moderation operating loop

1. **Daily-ish Triage.** One moderator sweep: unanswered Q&A older than 48h gets a reply or a "need more info" nudge; misfiled threads get moved; duplicates get linked and locked (not deleted — the duplicate's title still serves search).
2. **Pin the canonical threads.** Pin FAQ/high-traffic threads per category; a pinned "Read this first" Q&A thread with links to docs cuts repeat questions measurably.
3. **Lock stale threads.** Auto-lock isn't built in — run `gh api` / GraphQL (`lockLockable`) on a schedule for threads inactive beyond N days in announcement/ideas categories to prevent zombie-thread revivals.
4. **Retire categories deliberately.** Deleting a category forces choosing a destination for its existing discussions ("Delete & Move") — never lose content, but do communicate category changes in Announcements first.
5. **Measure and iterate.** Watch unanswered-rate and time-to-answer in Q&A (GraphQL `Discussions` / `Discussion` queries expose comments and answer state); if a category's unanswered-rate stays high, it's a docs gap, not a moderation gap.
6. **Set expectations in the banner.** The Discussions homepage announcement/banner should state response SLAs and what belongs where — governance is mostly written-down defaults, not policing.

## Related

1. **`github-wiki-vs-docs.md`.** Where Discussions sits versus wikis, docs sites, and issues.
2. **`issue-and-pr-templates.md`.** Issue forms and links that funnel support traffic to Discussions.
3. **`github-stale-bot-config.md`.** Stale-bot analogies for discussion lifecycle automation.
