# agent-generated-code-needs-human-review-2026

> By 2026 a meaningful fraction of merged code originated as AI-agent
> output. Several production incidents traced back to a common failure:
> the human "reviewed" the diff, saw it looked plausible, and approved it
> — without re-deriving whether the code was actually correct.

## Symptom

A junior engineer asks a coding agent to "add a retry to the order-create
call." The agent produces a clean 12-line diff: wraps the call in a `for`
loop, catches the exception, retries up to 3 times with a 1-second sleep.
Tests pass. The PR is opened, a senior reviews it in two minutes ("looks
reasonable, the retry loop is idiomatic"), and approves.

Three weeks later, the payments provider has a 90-second blip. The retry
loop fires, queues 3 attempts per in-flight order, and — because the loop
does not check idempotency before retrying — debits a non-trivial set of
customers two and three times. Refunds take 9 days. The postmortem's root
cause reads: **"the retry logic was syntactically correct and semantically
wrong, and the reviewer evaluated syntax, not semantics."**

This is the new shape of review failure. The agent's output is fluent,
well-formatted, and passes linters. It is also exactly the kind of code a
human would write if they were thinking about *the loop* but not about *the
system the loop lives in*. The reviewer, seeing polished code, defaulted to
the cheap review (does it look right?) instead of the expensive one (is it
right, given everything else this service does?).

## Gotchas

- **Plausibility is not correctness.** Agent-generated code is optimized to
  look like the surrounding codebase. That is precisely what makes it
  dangerous: it bypasses the "this looks weird, let me look closer" instinct
  that catches human-written bugs. Treat unusually clean diffs from an agent
  as a yellow flag, not a green one.

- **Agents reason about the function, not the system.** The retry bug above
  is the canonical example. The agent correctly solved "add a retry." It had
  no model of "this call is not idempotent" or "retries here double-charge
  users." The human reviewer is the only party in the loop who can hold the
  system context. If the reviewer also reasons only about the function, the
  system bug ships.

- **"The tests passed" is the most dangerous sentence in agent-assisted
  dev.** Agents are good at writing tests that pass — including tests that
  assert the wrong thing. A retry test that mocks the provider and checks
  "it tried 3 times" will pass on the double-charging code. Review the
  *tests* as hard as the implementation. Ask: does this test fail if the
  bug were present? If not, the test is theater.

- **Diff size is no longer a proxy for review effort.** A 12-line agent
  diff can encode a system-level correctness bug that takes an hour to
  reason through. Senior engineers who skim small diffs in 2 minutes are
  applying a heuristic calibrated to human-authored small diffs. For
  agent-authored code, the right heuristic is: small diff, full review.

- **Approval counts from agents inflate trust.** Some teams let an agent
  "approve" a PR before a human looks at it. That approval is a lint pass,
  not a review. It checks shape, not meaning. Never let agent approval
  substitute for a human who can be held accountable for the system
  behavior — and never let "the agent approved it" appear in a postmortem
  as a reason the change shipped.

- **Agents do not know what they don't know.** They won't volunteer "by the
  way, this call isn't idempotent, did you consider that?" because they
  didn't consider it. Build the habit of asking the agent *what could go
  wrong with this change at the system level* before approving — and then
  verify its answer independently, because it will also hallucinate
  reassurances.

- **Copy-paste from agent output into a PR is the worst pattern.** The
  worst-reviewed agent code is the code someone pasted without ever running
  it locally or reading it aloud. Require that any agent-authored change be
  executed against a real (or realistic) environment by the human before
  merge. "It ran in the agent's sandbox" is not the same as "I ran it."

- **Blast radius scales with what the agent is allowed to touch.** An agent
  that can open PRs to a payments service is more dangerous than one that
  can only touch docs. Scope agent permissions to blast radius, not to
  convenience. The convenience of "let the agent ship it" is paid for in
  the incident that follows.

## What to do instead

1. For any agent-authored PR touching money, auth, data mutation, or
   retries: require a named human reviewer who writes one sentence
   describing the system-level consequence of the change. No sentence, no
   merge.
2. Add a PR checklist item: "I have considered whether this change is safe
   to retry / safe to run twice / safe to run on stale data." If the answer
   is no and the change doesn't enforce idempotency, block it.
3. Periodically inject a known-bad agent diff into your review queue as a
   control. If it gets merged, your review process is not catching what you
   think it is.
4. Treat the agent as a very fast, very confident junior engineer who never
  sleeps and never asks clarifying questions. That is exactly the level of
  trust it has earned.
