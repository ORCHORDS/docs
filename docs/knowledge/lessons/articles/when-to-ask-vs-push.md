# when-to-ask-vs-push

**Issue:** When to ask the user vs when to push forward
**Date:** 2026-08-09
**Status:** documented (decision framework)

## Symptom
You face a design decision. Two reasonable approaches. You
pick one, ship it. The user wanted the other. You rework. Time
wasted: 2 hours.

## Root cause
The agent is wrong to always pick, and wrong to always ask.
The right answer depends on the situation.

**Source:** General principle of judgment under uncertainty:
https://en.wikipedia.org/wiki/Decision_theory

## Fix
A simple decision matrix:

### Ask the user when:
- **The decision is hard to reverse.** Schema design, public API
  shape, security boundary — these cost hours to undo.
- **The decision affects user-visible behavior.** Brand colors,
  copy, UX flow.
- **You have low confidence (< 70%) the user agrees with you.**
- **The user explicitly said "ask me before X."**

### Push forward when:
- **The decision is easy to reverse.** Variable name, file
  structure, internal helper function.
- **The decision is a clear improvement** of the current state
  (e.g. bug fix, performance optimization).
- **You have high confidence (>90%) the user agrees.**
- **The user explicitly said "use your judgment on X."**

### Default to push-forward
When in doubt, push forward. The agent's job is to make
progress, not to ping the user every 5 minutes. Only ask when
the cost of being wrong is high.

### "I made a judgment call" disclosure
When you push forward on a non-obvious decision, mention it in
the response:
> "I used `jsonOk(payload, undefined, { status: 201 })` for the
> 201 Created responses (rather than `new Response(...)`) to
> match the existing pattern. Easy to change if you prefer the
> other."

This gives the user the option to override without making them
re-derive the decision.

## Verification
- **Audit:** Weekly review of "I made a judgment call" disclosures
  to calibrate the threshold
- **Live:** The user feels "I can trust the agent to push forward
  on small stuff and ask on big stuff"

## Gotchas
- **"I can decide later" is a trap.** For non-reversible
  decisions, decide early. Pushing forward "to see" creates
  tech debt to undo.
- **The user might be busy.** If asking blocks them for hours,
  push forward with a sensible default + disclosure. They can
  override later.
- **"What would I do if the user wasn't here?"** If the answer
  is "I'd push forward," push forward. If the answer is "I'd
  ask the user," ask.
- **A "wrong" call that's reversible is a learning opportunity.**
  Document it, move on. Don't ask permission next time on the
  same kind of decision.
- **"I'm not sure" is the worst state.** If you're not sure
  AND the decision is non-reversible, ask. If you're not sure
  AND the decision is reversible, push forward + disclose.

## Related
- `lazy-fail-evidence-discipline.md`
- `scope-discipline.md`
- `user-pivot-rule.md`
