# wontfix-policy-communication

**Issue:** Every tracker eventually fills with requests the team will not fulfill — out-of-scope features, behavior that is actually working-as-intended, fixes that conflict with the architecture, and requests with costs wildly exceeding their value. Teams without a defined decline policy handle these inconsistently: some issues sit open for years as silent rejections, others get closed with a bare "wontfix" label that reads as contempt, and a few get reopened in a loop by frustrated reporters. Each pattern damages trust and burns maintainer time. Declining work is one of the highest-frequency decisions a project makes, so it deserves an explicit policy covering when to decline, how to word the decline, and how to keep declined issues from becoming recurring disputes. This article defines that policy and deliberately complements issue-staleness-automation, which covers the bot mechanics of closing stale issues; here the focus is the human decision and its communication.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The cost of an undefined decline policy

1. **Open-but-dead issues lie to everyone.** An issue left open because nobody wants the confrontation still signals "planned" to reporters and dashboards. Product-management guidance on declining requests is unanimous on this point: leaving requests dangling indefinitely is worse than a clear, early no.
2. **Inconsistent declines read as arbitrary.** When one maintainer closes a similar request as wontfix and another accepts it, reporters conclude decisions are political rather than principled, which invites re-litigation of every decline.
3. **Bare "wontfix" damages the project's reputation.** A close reason with no explanation is the most-complained-about maintainer behavior in community threads on this topic (for example, the Hacker News discussion "How to say no to a GitHub issue feature request?"). The label answers nothing; only the accompanying rationale does.
4. **Undocumented declines get re-decided.** Six months later nobody remembers why the issue was declined, so it gets reopened, re-triaged, and re-declined — the same decision purchased twice at full price.

## Decision framework: decline now, defer, or redirect

1. **Reserve wontfix for genuine, stable declines.** The wontfix/not-planned state should mean "we have decided this will not be done under the current product direction," not "we are tired of looking at this." Deferrals belong in backlog or later labels so the decline vocabulary stays credible.
2. **Ask what the requester actually needs first.** Feature-request handling guides (Canny, Featurebase, and similar) consistently recommend asking clarifying questions before deciding, because the stated request is often one solution among several for an underlying need the team can meet more cheaply.
3. **Check the request against written scope.** A decline that cites the project's stated scope or design principles ("this conflicts with the zero-config goal documented in the README") converts a personal refusal into an appeal to shared, reviewable rules. If no scope document can justify the decline, that itself is a signal to reconsider or to write the scope down.
4. **Distinguish defect from expectation.** "Working as intended" is not wontfix — it is a documentation or expectation problem. Route it to a docs task or an explicit behavior note rather than closing it as declined, so the next reporter is not surprised the same way.
5. **Record the decision, not just the outcome.** The closing comment should name the reason category — out of scope, cost exceeds value, conflicts with design, duplicate of a prior decline, or no longer relevant — so declines become a queryable dataset about the product's boundaries.

## Communication patterns

1. **Thank, then explain, then decline.** The near-universal template across both open-source and product-management practice: acknowledge the effort of the report, state the reason in one or two honest sentences, then close. Honesty ("this serves perhaps a dozen users and would complicate every migration") beats vague deference ("maybe someday").
2. **Offer the alternative or the path, when one exists.** Point to the existing feature that covers most of the need, the config workaround, the plugin or extension surface, or the process for proposing a design change. A decline with an exit ramp preserves the relationship; a dead end invites an argument.
3. **Use the platform's close vocabulary correctly.** GitHub's "not planned" close reason, added in 2022, plus labels like wontfix, out-of-scope, and working-as-intended, make the outcome machine-readable and visually distinct from completed work. Free-text closes defeat reporting on decline rates.
4. **For contested or high-traffic declines, decide in public first.** Moving the debate to a discussion thread or RFC before closing — the pattern used by large projects to avoid backlash — means the close is executing a documented decision instead of appearing to suppress one.
5. **Keep the wording reusable.** Maintain a short library of decline snippets per reason category. Consistent language across maintainers is what makes the policy feel institutional rather than personal.

## Managing reaction and reopens

1. **State the reopening conditions explicitly.** The best declines end with a concrete trigger: "if the streaming API lands and this still matters, reopen and we will reassess." This converts reopens from nuisance into the agreed signal, and reporters respect it.
2. **Answer the substance of a reopen once, then hold.** If a reporter reopens with a genuinely new argument, engage it on the merits; if they reopen with the same argument, point to the original rationale and reclose. Escalating tone in reply is how a decline becomes a public incident.
3. **Lock threads sparingly and never silently.** Locking a heated thread after a final explanatory comment is legitimate pile-on control; locking with no explanation is read as censorship and gets screenshotted. Prefer locking only after the record is complete.
4. **Watch for decline clustering.** If five similar requests are declined over a quarter, that is not five decisions — it is demand signal. Route the cluster into roadmap review rather than continuing to decline instances one by one.

## Measuring the policy

1. **Track decline rate by reason category.** A healthy tracker shows a stable mix. A spike in "cost exceeds value" declines signals under-resourcing; a spike in "out of scope" may signal the scope document drifting out of date.
2. **Measure reopen-after-decline rate.** A small steady rate is healthy engagement; a climbing rate means either the rationale quality is dropping or the policy has lost legitimacy and reporters are voting with reopens.
3. **Audit time-to-decision on requests.** Declining fast is a feature: every week a doomed request stays open, the reporter's expectations grow and the eventual no lands harder. Median time from intake to decline is the metric to watch.
