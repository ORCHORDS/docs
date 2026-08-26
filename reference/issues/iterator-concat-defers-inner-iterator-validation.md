# Iterator.concat Defers Inner Iterator Work

**Issue:** `Iterator.concat` produces a lazy iterator. Later sources and their yielded values are not consumed until prior sources finish, so failures and side effects occur during iteration rather than construction.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Do not use construction success as validation of every input sequence.
- Define ownership and closing behavior for each source on early termination or abrupt completion.
- Avoid sharing stateful source iterators with other consumers.
- Put resource acquisition as close as possible to actual iteration and make cleanup idempotent.

## Verification
- Instrument acquisition, `next`, and `return` across empty, finite, throwing, and infinite sources.
- Break before reaching later sources and assert they remain untouched.
- Throw while moving between sources and assert active resources close.

## Gotchas
Concatenation is lazy, not materialization. An infinite first iterator makes every later iterator unreachable.

## Official sources
- [ECMAScript Iterator.concat](https://tc39.es/ecma262/multipage/control-abstraction-objects.html#sec-iterator.concat)
