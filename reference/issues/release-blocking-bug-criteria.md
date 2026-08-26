# release-blocking-bug-criteria

**Issue:** Every release needs a go/no-go decision, but without pre-agreed blocking criteria the decision degenerates into a negotiation held under time pressure, where the loudest stakeholder or the most anxious engineer sets the bar. Two failure modes dominate: shipping with a blocker because the deadline was treated as fixed and the criteria as soft, or holding a release for cosmetic defects because nobody distinguished blocking from non-blocking. Both are process failures, not judgment failures — the team never wrote down what "blocking" means before the pressure arrived. This article defines explicit release-blocking criteria, the decision procedure that applies them, and how to ship responsibly with the known, non-blocking bugs that remain.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Defining blocking classes

1. **Data loss or corruption.** Any defect that can destroy, corrupt, or silently truncate user data is blocking in all releases, without exception. The zero-bug literature frames the goal as "zero bugs impacting users" — data integrity is the clearest instance of user impact, and it cannot be waived by workaround documentation.
2. **Security and privacy defects.** Authentication bypasses, privilege escalation, injection paths, and exposure of personal data block the release. If the fix is not ready, the release waits or the vulnerable feature ships disabled behind a flag.
3. **Core-path failure.** The defect breaks a primary user journey — sign-up, login, checkout, the product's central operation — for a material share of users. The judgment is scope: a broken login for all users blocks; a broken export for one deprecated format does not.
4. **Regression of previously working behavior.** A feature that worked in the last release and is now broken blocks even if its absolute severity would not, because regressions destroy more trust than novel bugs and are exactly what users notice first.
5. **No viable workaround at expected scale.** A severe defect with a documented, tolerable workaround for the affected population may be non-blocking; the same defect without a workaround, or with one that only support staff can perform, stays blocking. The workaround test converts severity into a release decision.

## Decision procedure

1. **Write the criteria down between releases, not during one.** Blocking rules authored mid-crunch encode whatever the current pressure wants them to encode. A short, versioned criteria document — reviewed like code — is the reference every release decision cites.
2. **Tag blockers as a distinct tracker state.** A release-blocker label with owner and target-release fields makes the blocking set queryable at any moment, so the go/no-go meeting reviews a list rather than reconstructing one from memory.
3. **Require the zero-bug triage stance: fix now or formally release-with.** The 0-bugs policy pattern (InfoQ; Ministry of Testing glossary) forces every bug into an explicit decision — fix before release, or consciously accepted as shipped-with — so nothing blocks implicitly and nothing ships implicitly. Ambiguity is the enemy; the backlog is not a decision.
4. **Hold a time-boxed go/no-go with a named decision owner.** The release manager decides; engineering, QA, and support advise with evidence. Consensus-seeking under deadline pressure produces either gridlock or silent vetoes; a named owner with pre-agreed criteria produces a defensible call.
5. **Make waivers explicit and priced.** Any blocker waived at go/no-go needs a written waiver: the accepting owner, the customer impact, the workaround, and the follow-up issue with a due date. Waivers that cost nothing procedurally become routine.

## Shipping with known bugs responsibly

1. **Publish a known-issues list with the release.** Every accepted non-blocking defect appears in release notes with user-visible symptoms and workarounds. Customers who discover an undocumented known issue assume it is unknown-and-uncared-about; the documented list converts the same bug into managed expectations.
2. **Slot accepted bugs into the next planned release before shipping.** An accepted bug without a target release is a decision deferred, not made. Scheduling it at acceptance is what distinguishes deliberate tolerance from backlog rot.
3. **Instrument the accepted bugs.** Where feasible, add telemetry or error tracking for the known defect so its real-world frequency after release is measured, not guessed. If the accepted bug fires far more than estimated, that is the trigger to revisit the decision.
4. **Brief support before the release goes out.** Support must hear each known issue, its workaround, and its phrasing before customers do — a support team surprised by the release notes cannot absorb first contact.

## Post-release review

1. **Score the decision, not just the release.** Within one or two cycles, compare outcomes: did waived blockers actually bite? Did held releases for alleged blockers prove justified? Feeding this back is how the criteria document improves instead of fossilizing.
2. **Track escaped-blocker incidents.** If incidents occur that the criteria should have classified as blocking but did not, the gap is in the criteria wording or in the tagging, and the review must amend the specific rule that failed.
3. **Watch the blocker count trend per release.** A climbing number of blockers per release indicates quality debt accumulating upstream — usually weakened regression coverage — and should trigger investment there rather than ever-stricter release policing.
