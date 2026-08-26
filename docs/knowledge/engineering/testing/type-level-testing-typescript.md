# type-level-testing-typescript

**Issue:** TypeScript types are executable logic: conditional types, inference, generics, template literal types, and overloads encode real behavior that can be wrong in exactly the way functions are wrong — wrong branch selected, inference collapsing to never or any, a conditional too broad, an overload shadowed. A broken utility type ships no runtime error; it silently weakens every call site that relies on it, often widening to any and disabling checking exactly where safety was the point. Yet almost no team tests types: typecheck passes, runtime tests are green, and the type system's guarantees have quietly eroded. Type-level testing makes type behavior a first-class verified contract using compile-time assertion tools — Vitest's expectTypeOf and assertType in .test-d.ts files (run under vitest typecheck), tsd's expectType/expectAssignable/expectError for published libraries, or hand-rolled Expect-Equal helper types. The engineering problem is knowing which type properties to pin, using equality versus assignability correctly, and keeping type tests fast enough to run in every CI build.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Tools and what each is for

1. **Vitest expectTypeOf.** The in-suite option: type tests live in .test-d.ts files alongside runtime tests, vitest typecheck compiles them and surfaces failures as TypeScript errors. Best for application codebases already on Vitest; one command runs both layers and there is no extra dependency, which is why Matt Pocock's Total TypeScript guidance recommends it as the default choice.
2. **tsd for published libraries.** tsd runs assertions (expectType, expectAssignable, expectError, expectDocCommentExamples) against your package's .d.ts as consumers see it, including type-visibility bugs (private types leaking into public signatures) that only manifest across package boundaries. Library authors should run it in CI even when expectTypeOf covers internal generics.
3. **assertType and markers.** Vitest's assertType performs a raw assignability check without the builder API; useful for quick pinning, but prefer expectTypeOf's matchers (toEqualTypeOf, toMatchTypeOf, toBeNullable, parameter/returns accessors) because they produce clearer failures and express intent.
4. **Hand-rolled Expect/Equal helpers.** A two-line conditional type proving exact equality (the Expect-Equal pattern) works with zero tooling and predates the libraries; fine for a handful of assertions, but migration to expectTypeOf buys composability — chains like expectTypeOf(fn).parameter(0) that walk parameters and returns read like runtime tests.

## Equality versus assignability — the core distinction

1. **Exact equality (toEqualTypeOf).** Asserts both directions: the type is the target and nothing broader. Use it to pin public generic outputs, discriminated-union results, and template-literal computations where any widening is a regression. This is the assertion that catches a conditional type silently resolving to its fallback branch.
2. **Assignability (toMatchTypeOf, expectAssignable).** One-directional: accepts the target. Use it for inputs and configuration objects where accepting a narrower type is correct and legal. Misusing assignability where equality is meant is the most common false-green in type tests.
3. **Negative assertions (expectError).** Asserting that invalid usage fails to compile is the heart of type testing: calling the API with the wrong argument shape, accessing a discriminated variant's exclusive property, or omitting a required generic must produce a compile error. tsd's expectError is the mature form; with expectTypeOf, the pattern is a contradiction check that only compiles when the error is absent.
4. **Beware any.** A type test that "passes" because the actual type collapsed to any proves nothing. Include an explicit assertion that public outputs are not any (and not unknown where specificity was promised); Vitest documents dedicated matchers for this because any-evasion is so prevalent.

## What deserves a type test

1. **Exported utility and helper types.** DeepPartial, PathOf, Result-returning inference, event map types — every conditional or infer-based type in shared packages gets exact-output assertions for representative inputs, including edge inputs (empty object, union members, readonly variants) where conditionals flip branches.
2. **Generic function inference.** Assert that type parameters infer from arguments rather than requiring explicit annotation: expectTypeOf on the return of a typed fetch wrapper or state selector proves inference survives refactors, the most common silent breakage in library upgrades.
3. **Discriminated unions and exhaustive switches.** Pin union membership and per-variant properties, plus a negative test that an impossible variant combination fails to compile. This is the contract exhaustive switch statements and React discriminated rendering depend on.
4. **Public API surfaces of libraries.** The .d.ts is your users' compile-time API; snapshot the resolved types of representative calls in tsd so a dependency bump that erodes the public type (often via a loosened upstream generic) fails CI instead of downstream builds.
5. **What not to test.** Don't pin trivially derived types (plain interfaces, one-line Pick/Omit) or implementation-only types that never cross a module boundary; every pinned type is a maintenance cost, so test where behavior lives — conditionals, inference, overloads.

## Running type tests in CI efficiently

1. **Dedicated glob and isolated step.** Keep type tests in .test-d.ts (or .test-d.tsx) files so vitest typecheck handles them separately from runtime tests; run tsc-style full typecheck in parallel rather than gating runtime tests behind it, keeping the feedback loop fast.
2. **Pin the TypeScript version.** Type-level behavior legitimately changes across TS releases (inference improvements, stricter checks); pin the compiler in CI and treat version bumps as reviewable changes that may legitimately update type-test expectations, upgrading deliberately rather than discovering drift mid-sprint.
3. **Budget type-test complexity.** Just as with runtime tests, a type test that takes minutes to compile is a smell: split suites by module so tsc project references or vitest typecheck only recompiles affected type tests, and keep chains short — deeply chained expectTypeOf accessors slow compilation quadratically in large monorepos.
4. **Review discipline.** Require that any PR touching a conditional or generic type includes a type test demonstrating the new behavior and at least one negative assertion; without this rule, type tests stagnate into a thin layer that only covers the original utilities.
