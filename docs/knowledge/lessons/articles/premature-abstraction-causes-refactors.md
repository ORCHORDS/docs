# premature-abstraction-causes-refactors

**Issue:** Abstractions built before their use cases are known create wrong interfaces that must be broken and re-built when the real requirements emerge
**Date:** 2026-08-11
**Status:** documented

## What happened
An engineer built a generic "notification service" to handle all future notification types before any notification type beyond email existed. Six months later, SMS and push notifications were added. Their requirements didn't fit the "generic" abstraction — push needs device tokens, SMS needs carrier validation, email needs threading. The generic interface was broken three times during additions. The final code was more complex than three independent, specific implementations would have been.

## The lesson
Abstraction is earned, not assumed. Write the concrete implementation for the first case. Write the concrete implementation for the second case. Extract an abstraction when the third case reveals the natural seam. This is the "rule of three." Premature abstraction guesses at the interface before the real shape of the problem is known.

## Why it matters
Premature abstractions impose constraints on future code before the constraints are justified. Breaking the wrong abstraction later is expensive: every caller of the abstract interface must be updated, and the original "savings" of the abstraction are paid back with interest.

## How to apply
- [ ] Resist the urge to abstract after the first use case. Write it concretely.
- [ ] After the second similar case, note the duplication. Consider it for later.
- [ ] After the third case, the abstraction's natural shape is usually apparent — extract it now.
- [ ] If you must abstract early (e.g., for testing), keep the interface minimal and mark it with a comment noting it's provisional.
- [ ] Validate an abstraction by checking: does every caller use every part of this interface?

## Related
- `over-engineering-is-a-form-of-tech-debt.md`
- `boring-technology-wins-long-term.md`
