# Code Freeze Exception Approval Workflow

## Scope

This article covers the exception approval workflow for code freezes: who may request an exception, what a request must contain, the approval chain by risk class, how fast each class must be answered, and how freezes are lifted. It applies to release freezes, change freezes around high-traffic periods, and compliance-driven lockdowns. It does not cover branch strategy, release branch mechanics, or general hotfix procedure — the freeze workflow only governs changes that must land while normal channels are closed.

## Workflow or implementation guidance

A code freeze is a policy state, not a technical state. Branch protection tightens to enforce it, but the freeze's real definition is a written scope: which branches, which dates, which change classes are blocked, and who may grant exceptions. Without a written scope, a freeze means whatever the most recent person to say "we're frozen" believes, and exceptions become hallway negotiations.

Define the freeze in a short, versioned document with five fields: the branches covered (typically the release branch and the default branch), the start and end timestamps with timezone, the blocked change classes, the exception approvers by class, and the emergency path. Publish the document where contributors already look — linked from the repository's pinned issue — rather than in a separate portal nobody visits.

Exception classes and their approval chains:

**Class 1 — Release blocker fix.** The change fixes a defect that blocks the release the freeze exists to protect. Approver: release manager alone. Target response: same day. This class exists because freezes fail most often from their own rigidity; a freeze that cannot absorb a blocking fix gets cancelled instead.

**Class 2 — Customer-impacting defect with no release dependency.** A production issue whose fix does not interact with the release. Approver: release manager plus the owning team's tech lead. Target response: same day. The second approval exists because the change still ships into a frozen tree and the owning lead is accountable for its blast radius.

**Class 3 — Security fix.** Approver: release manager plus security on-call. Target response: immediate; security fixes never queue behind a freeze. The request may be filed after the fact for details that would leak exploitation guidance.

**Class 4 — Anything else.** Documentation, dependency bumps, features, refactors. Approver: none during freeze; the request is a request to schedule for after the freeze. Recording it still matters — the queue of deferred changes is the freeze's backlog, and it should be worked in order, not by whoever asks loudest after thaw.

Every exception request carries four items: the change (PR link, not prose), the reason it cannot wait, the rollback plan, and the requested class. The rollback plan is the field teams most often leave blank and the field that most often changes the answer. A change with no rollback plan during a freeze is a change that can end the freeze early in the wrong direction.

Record every decision — granted or denied — in the tracking issue. The record is not bureaucracy; it is the freeze's audit trail and its post-freeze review data. A freeze whose decisions live in chat threads cannot be reviewed, and a freeze that cannot be reviewed cannot be improved.

Operationally, enforcement happens at the branch, not at the person. Tighten the default and release branches so direct pushes are blocked and merges require the freeze label plus the exception approval recorded on the PR. A freeze enforced only by convention gets violated within a week by a well-meaning contributor in a hurry. The enforcement configuration change itself goes in before the freeze starts, tested on a branch, because a misconfigured freeze that blocks Class 1 fixes is its own incident.

Lifting a freeze is a scheduled, announced event with a defined order of operations: revert branch protection to normal policy, announce the thaw with the deferred-change queue attached, and assign owners to the queue. The post-freeze review happens within a week and answers three questions: how many exceptions by class, what was the median response time against target, and what did the deferred queue teach about the freeze's scope being wrong. A freeze with forty Class 4 requests that were all obviously safe is a freeze whose scope is too broad, and next cycle should exclude that change class.

## Controls

- A versioned freeze document with branches, timestamps, blocked classes, approvers, and emergency path, pinned where contributors look.
- Exception classes 1 through 4 with named approver roles and response targets per class.
- Mandatory request fields: PR link, justification, rollback plan, requested class.
- Branch-level enforcement on default and release branches requiring the freeze exception label plus recorded approval.
- All decisions logged in a single tracking issue, granted or denied.
- Scheduled thaw with announced deferred-queue ownership, and a post-freeze review within a week.

## Validation evidence

Verification of a freeze workflow is a mix of drill-time checks and post-freeze analysis:

- Before each freeze, test the tightened branch policy by attempting a direct push and an unapproved merge from a scratch clone; both must be rejected with a message pointing to the exception process.
- During the freeze, verify each exception request has all four fields and an approval matching the class's chain before its PR merges; sample every Class 2 and 3, since they are the risky ones.
- Confirm Class 3 security fixes were never queued and their response times were immediate.
- After thaw, compute exception counts by class, median response time versus target, and deferred-queue size; compare against the previous cycle to detect scope drift.
- Check that no merged commit during the freeze window lacks either an exception record or a label — untracked merges are enforcement gaps, and the gap's cause goes into the review.

## Failure modes and correction

- **Freeze by folklore.** Scope lives in memory and chat, so different teams freeze differently. Correction: the versioned document is the freeze; anything else is a proposal.
- **Approver bottleneck.** One release manager is the sole approver for every class and travels during the freeze. Correction: named deputies per class with the same authority, listed in the document.
- **Rubber-stamp Class 2.** The second approval is granted in seconds without reading the rollback plan. Correction: the post-freeze review samples Class 2 approvals for substance; a pattern of empty second approvals is escalated to engineering management.
- **Enforcement misconfiguration.** The tightened policy blocks Class 1 blocking fixes and the release slips because the fix cannot land. Correction: test the freeze policy configuration before the freeze starts, including the exception path.
- **Silent violations.** Urgent changes land via direct push from an admin bypass. Correction: audit commits during the window against the exception log; admin bypasses during a freeze are review findings, not privileges.
- **Zombie queue.** Deferred changes never get owners after thaw and rot for a quarter. Correction: thaw assigns owners; the next freeze's review checks the previous queue's completion rate.

## Limitations

The workflow presumes freezes are periodic and bounded; a permanently frozen branch is not a freeze but a dead branch, and this process will not rescue it. Class response targets assume approvers work roughly aligned hours — globally distributed teams need follow-the-sun approver lists this article only gestures at. The approval chains rely on role clarity that small teams may not have; a five-person team will compress the chains, which trades oversight for speed and should be a conscious choice. Freeze enforcement strength depends on the hosting platform's branch policy features; where policies cannot express label-plus-approval conditions, enforcement degrades to CI checks and audit. Finally, this workflow governs process only — it says nothing about whether a freeze is the right change-risk tool for a team whose deployment cadence is already continuous.

## Canonical sources

- GitHub Docs — About rulesets and branch protection (freeze enforcement): https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- GitHub Docs — Managing environments for deployment (protected deployment gates): https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment
- Git documentation — git-revert (rollback plans referenced by exception requests): https://git-scm.com/docs/git-revert
