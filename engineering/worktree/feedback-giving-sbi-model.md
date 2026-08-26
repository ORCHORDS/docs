# feedback-giving-sbi-model

**Issue:** Feedback is vague, personal, or delivered in ways that make recipients defensive
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
"You're not communicative enough." The engineer doesn't know what to change. Or feedback is so hedged ("it was great, but maybe...") that it doesn't land. Or a manager delivers critical feedback publicly and kills psychological safety.

## Pattern / Solution
Use the SBI model (Situation, Behavior, Impact) to structure feedback that is specific, observable, and actionable.

**SBI format:**
- **Situation:** When and where did this happen? (Specific, not "always" or "never")
- **Behavior:** What exactly did the person do or say? (Observable, not inferred intent)
- **Impact:** What was the effect on you, the team, or the project?

**Examples:**

Vague feedback:
> "You communicate poorly in meetings."

SBI feedback:
> **S:** In yesterday's architecture review, **B:** you presented the design without leaving time for questions, and when someone asked one, you interrupted them to continue your slide. **I:** Two engineers told me afterward they felt their input wasn't valued, and the decision moved forward without their concerns addressed.

Positive SBI:
> **S:** When we were debugging the production outage last Thursday, **B:** you stayed calm, kept a running timeline in the incident channel, and explicitly checked in with the on-call engineer. **I:** It reduced the panic in the room and we resolved it 30 minutes faster than our last similar incident.

**Delivery checklist:**
- [ ] Feedback is given privately unless it's purely positive
- [ ] Within 48–72 hours of the event (memory fades)
- [ ] Ask before delivering: "Is now a good time for some feedback?"
- [ ] Follow with a question: "What do you think about what I've described?"

## Gotchas
- SBI describes behavior, not character — never say "you are X", say "you did X"
- Positive feedback is feedback too — don't only use SBI for criticism
- The impact statement must be real, not manufactured to justify the feedback

## Related
- `engineering-manager-one-on-ones.md`
- `performance-review-process.md`
- `blameless-culture-implementation.md`
