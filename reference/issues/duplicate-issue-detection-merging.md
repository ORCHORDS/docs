# duplicate-issue-detection-merging

**Issue:** The tracker accumulates five separate issues for the same crash, each with its own comment thread, partial repro information, and subscribers. Maintainers answer the same questions five times, "+1" comments scatter across copies, and when a fix finally lands only two of the five issues get closed — the other three resurface months later as "is this still broken?" Duplicate issues are not just noise: they split evidence, inflate the apparent bug count, and waste triage time re-deriving the same diagnosis. The team needs a systematic way to detect duplicates at intake, canonicalize them into one tracking issue, and close the copies without alienating the reporters who filed them in good faith.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Detection at intake

1. **Enable the platform's duplicate suggestions.** GitHub's duplicate detection (public preview since 2026) surfaces potentially matching issues in the issue-composer as the reporter types, killing the cheapest duplicate — the one never filed.
2. **Search before filing, enforced by template.** Put a "Similar issues found?" checklist step at the top of the bug-report form so the reporter acknowledges they searched; this converts etiquette into process.
3. **AI-assisted triage on creation.** Marketplace actions (e.g. the AI-powered duplicates/relations detector) and agents using the GitHub MCP server can comment with candidate duplicates within minutes of filing, before a human ever looks.
4. **Match on stack trace, not prose.** Two reports written in different words about the same assertion failure only correlate on the traceback; normalize error signatures (file, function, message template) when comparing.
5. **Watch for symptom clones.** Different user-visible symptoms can share one root cause; when closing one fix resolves several reports, link them all before closing so the relationship is recorded while memory is fresh.

## Marking protocol

1. **Use the native "Duplicate of" comment.** Typing `Duplicate of #N` in a comment creates a formal duplicate relationship that GitHub renders as a linked banner — never rely on free text alone.
2. **Verify before marking.** Open both issues side by side and confirm the repro, environment, and stack match; a wrong duplicate-close is worse than a duplicate because the reporter of the real distinct bug gives up.
3. **Pick the canonical issue deliberately.** The keeper should be the issue with the clearest repro, not the earliest or the one with the most emoji-reactions; if the best data is split across copies, consolidate it into the canonical body first.
4. **One canonical, many pointers.** Every duplicate closes with the machine-readable link; the canonical issue's comment thread becomes the single place where progress is announced.
5. **Deduplicate in both directions.** Before closing #42 as a duplicate of #17, check whether #17 itself was already closed as a duplicate of something else — chains happen and orphan the real thread.

## Merging vs closing as duplicate

1. **Closing as duplicate is the default.** GitHub has no true merge for issues, so "close as duplicate with link" is the standard move; state this explicitly so nobody hunts for a merge button.
2. **Manually merge information first.** Copy any unique repro detail, environment, or screenshots from the duplicate into the canonical issue body before closing, citing the original reporter.
3. **Preserve subscriber intent.** People subscribed to the closed copy will not see the canonical thread's activity unless they subscribe again — tell them so in the closing comment.
4. **Never close-as-duplicate a superset.** If the new report covers strictly more ground, the new issue becomes canonical and the old one closes instead; size and clarity beat file order.
5. **Reopen policy.** If the reporter argues the issues are distinct, reopen and investigate rather than relitigating in comments — a false duplicate is a triage bug and gets fixed like one.

## Communicating with reporters

1. **Treat the close as a customer interaction.** A one-line "closing as duplicate of #N, follow there" reads as dismissal; add a sentence explaining why they match and thanking them for the extra data point.
2. **Credit contributions.** If evidence from the duplicate influenced the fix, mention the reporter in the canonical thread — duplicates are signal about prevalence, not garbage.
3. **Explain what duplicates mean for priority.** Multiple independent reports of one bug is escalation evidence; note the count in the canonical issue so it factors into prioritization.
4. **Avoid blame language.** "Already reported, please search next time" turns a helpful reporter into an ex-contributor; the template checklist owns that job, not the closing comment.

## Prevention and hygiene

1. **Audit duplicates monthly.** Grep closed issues for `Duplicate of` and check that canonical targets are still open where they should be — canonicals sometimes get closed without their duplicates being re-homed.
2. **Seed the FAQ from duplicates.** Anything duplicated three or more times belongs in the issue template hints or docs, because the duplication is a documentation failure.
3. **Track the duplicate rate.** If more than roughly a quarter of incoming reports are duplicates, the problem is searchable-knowledge, not reporter discipline.
