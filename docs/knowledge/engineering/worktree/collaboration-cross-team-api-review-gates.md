# Collaboration Cross-Team API Review Gates

## Scope

This article covers review gates for API changes that cross team boundaries: which changes trigger a gate, who reviews, what reviewers check, how long reviews may take, and how to keep gates from ossifying into queues. It applies to HTTP interfaces, event schemas, shared library contracts, and database schemas consumed by another team. It does not cover single-team code review, API documentation tooling, or deprecation mechanics as a standalone lifecycle.

## Workflow or implementation guidance

Cross-team review exists because the cost curve inverts at the boundary. Within a team, a bad design is caught by people who share your runtime and feel your outages. Across the boundary, nobody feels your outage until their pager goes off, and by then the contract is load-bearing. The gate's purpose is to move that feedback before the merge, cheaply and predictably.

The first decision is which changes gate. Gate everything and the process drowns; gate nothing and integration breaks at deploy time. The workable trigger list is small and mechanical:

- Any new endpoint, or a new field on an existing response object.
- Any change to a field's type, nullability, or semantics.
- Any removal or rename, regardless of how unused it appears.
- Any change to error codes, status codes, or retry semantics.
- Any change to an event schema: topic name, field set, delivery guarantees.
- Any change to a shared library's exported surface.
- Any schema change to a table another team reads or writes.

Additions and removals are deliberately asymmetric. Additive changes gate lightly — the consumer confirms the addition does not break their deserialization. Removals gate fully, always, because "no one uses this" is the most frequently wrong sentence in distributed systems. If a field appears in no code you own, it may be read by a script, a dashboard, or a data pipeline you have never seen.

The gate itself has four roles. The **contract owner** is the team that owns the interface — they review for consistency with the existing surface and naming. The **consumer representative** is one named engineer from each consuming team — they review for breakage against their actual usage, which is knowledge the contract owner does not have. The **schema steward** is a rotating senior engineer who reviews for versioning and evolution policy: whether the change fits the versioning scheme or requires a new major version. The **author** drives the process and answers questions. Note who is absent: managers, architects without runtime ownership, and anyone who will not be paged when the contract breaks.

The review runs on an artifact, not a conversation. The PR must include the machine-readable diff — OpenAPI or async schema diff for interfaces, generated schema diff for databases — plus a filled-in impact statement: what changes, which consumers are believed affected, the migration path, and the removal timeline for anything deprecated. A reviewer who has to reverse-engineer the contract change from code diffs reviews poorly and slowly.

Time-boxing keeps gates humane. Consumer reviews get two business days; silence past the deadline is recorded as an approval, because a gate that can be ignored by not answering is a gate that will be deleted by frustrated authors. Contract-owner and steward reviews happen in normal PR review time. The author chases once at day one, once at day two, then merges with the recorded approval. The automatic-approval-on-silence rule is what makes the time-box real; without it, deadlines are decoration.

Breaking changes get a stricter path: a written migration plan with dates, a compatibility window (typically dual-writing or dual-returning the old and new shapes), consumer sign-off in the PR rather than by silence, and a removal date recorded in the deprecation list. The compatibility window exists so that consumers migrate on their schedule, not on yours.

Finally, instrument the gate. Track median time-to-review by role, the share of reviews finding real issues, and the queue depth. A gate that runs at zero findings for a quarter is either perfect or reviewing the wrong changes — sample its reviews and find out which. A gate whose consumer reviews median four days is a queue, and queues get routed around.

## Controls

- A written, mechanical trigger list defining which changes require the gate; ambiguity resolves toward gating.
- Four named roles per review: contract owner, consumer representative, schema steward, author.
- Machine-readable contract diff plus impact statement required before review starts.
- Two-business-day consumer review window; expiry is recorded approval.
- Breaking changes require written migration plan, compatibility window, explicit consumer sign-off, and recorded removal date.
- Gate metrics tracked: time-to-review by role, real-issue rate, queue depth.

## Validation evidence

The gate's health is measurable continuously. Verify these on a rolling basis:

- Every merged PR that matched a trigger has an artifact diff and an impact statement; sample ten per month and check for prose-only "reviews."
- Consumer representative sign-offs are present or explicitly expired-as-approved; the expired share below roughly twenty percent indicates the window is realistic.
- Post-deploy, check that incidents caused by cross-team contract changes trend toward zero; each such incident is cross-referenced against whether the change passed the gate — a gate-passed breakage is a trigger-list gap, an ungated breakage is an enforcement gap, and the two have different fixes.
- The breaking-change deprecation list is reviewed monthly for entries past their removal date; overdue removals mean the compatibility window policy is not being enforced.
- Gate metrics reviewed monthly: a findings rate pinned at zero for a quarter triggers a sample audit of review quality rather than celebration.

## Failure modes and correction

- **Gate everything.** Every internal refactor triggers four reviewers and work stalls. Correction: the trigger list is the scope; refactors that do not touch the listed surfaces do not gate, and the list is versioned so narrowing it is a visible decision.
- **Design-by-committee reopens.** Consumer reviewers redesign the whole endpoint rather than check breakage. Correction: role briefs are explicit — consumer representatives answer one question: does this break you? Design feedback goes to the author as non-blocking.
- **Silent veto.** One consumer never responds and the change dies of old age. Correction: expiry-as-approval; unresponsive consumers lose the review, not the author.
- **Phantom approvals.** The consumer rep approves without checking their usage. Correction: the approval is recorded against the person, and breakage traced to an approved change surfaces in the retro with that record attached.
- **Ornamental steward.** The versioning review nods at everything. Correction: rotate the steward role quarterly and audit a sample of its reviews.
- **Undocumented exceptions.** Urgent changes skip the gate "just this once" and a quarter later skipping is the norm. Correction: exceptions are logged with a reason and reviewed monthly; a rising exception rate is escalated, not normalized.

## Limitations

The gate covers designed interfaces; it cannot see consumers who bypass the contract by scraping endpoints or reading replicas directly, and those consumers will break regardless. Two-day review windows assume business-hours alignment — teams spanning many time zones need either longer windows or follow-the-sun reviewers, and both have costs. The role model presumes teams small enough that a named consumer representative is meaningful; platform surfaces with dozens of consuming teams need representative sampling rather than full attendance, which weakens coverage. Automatic approval on expiry trades completeness for predictability, and a genuinely affected but unresponsive consumer will be burned by it — the expiry rule only holds if consumer representatives treat the duty as real work. Nothing here substitutes for runtime contract testing between services.

## Canonical sources

- GitHub Docs — About code owners (assigning review by path ownership): https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- GitHub Docs — About pull request reviews (review mechanics and required approvals): https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/about-pull-request-reviews
- Atlassian Git tutorials — Comparing workflows (cross-team collaboration patterns): https://www.atlassian.com/git/tutorials/comparing-workflows
