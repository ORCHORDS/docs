# Swift Strict Concurrency: Complete Checking Migration

Swift's concurrency-safety story culminates in strict checking: the compiler treats every reference crossing between isolation domains as an error unless the code proves safety (through `Sendable` conformance, actor isolation, or explicit markers). Swift 6 language mode turns these checks from warnings into build failures. Migrating a real codebase is therefore a deliberate campaign: enabling incrementally (per-target, per-diagnostic), classifying every violation (genuinely unsafe, accidentally unsafe, or safe-but-unprovable), and fixing by architecture rather than annotation spam. Teams that skip the classification step end in `@unchecked Sendable` swamps; teams that do it come out with a codebase the compiler can reason about. This article covers the checking levels, the migration ladder, the fix taxonomy, and rollout strategy.

## Scope

This article addresses Swift strict concurrency checking: `Minimal`, `Targeted`, and `Complete` checking levels; Swift 5-compatibility warnings versus Swift 6 errors; `Sendable` (checked and `@unchecked`), actor isolation and `@MainActor`, region-based isolation and `sending`/`isolated` parameter markers, `nonisolated(unsafe)` and dynamic checks, and per-target migration strategy. It covers the concurrency-checking layer. It does not cover structured concurrency APIs (tasks/groups/continuations) generally, performance of actors, or distributed actors.

## Workflow or implementation guidance

**The checking ladder.** Swift 5.10+ builds can opt in per target via build settings (`SWIFT_STRICT_CONCURRENCY`): `minimal` (only obvious violations), `targeted` (your code checked, dependencies lenient), `complete` (everything). In Swift 6 language mode, complete checking is implied and violations are errors rather than warnings. The migration path for an existing codebase is: targeted warnings → complete warnings → Swift 6 errors, per target, over time.

**The fix taxonomy.** Every diagnostic falls into one of four classes, and the right fix differs:

1. **Genuinely unsafe — fix the code.** Shared mutable state crossing domains: a singleton `var` cache read from any thread, a non-synchronized collection captured by escaping closures, a delegate property assigned on one queue and read on another. Fixes: make it an actor (queue all access through the actor's isolation), make it immutable (`let` of value types/Sendable types), or protect with the appropriate synchronization (lock in one place). The diagnostic did you a favor: this was a real race, possibly the intermittent crash you've been chasing.
2. **Accidentally unsafe — tighten the types.** A class crossing domains merely because it *could* mutate: `final class` with only `let` stored properties of `Sendable` types can become `Sendable` by declaration (or often by moving to a `struct`). The code was fine; the type didn't promise it. Fix at the type level so all users benefit.
3. **Safe-but-unprovable — restructure or mark narrowly.** The compiler can't see the invariant: a class guaranteed accessed only from one queue, a callback guaranteed synchronous. Preferred modern fixes: region-based isolation and `sending` parameters (let the compiler track that a value leaves its region exactly once), `isolated` parameters (a generic function running in the caller's domain), `nonisolated` where truly domain-free. Last resorts, in order of decreasing preference: `@unchecked Sendable` with a comment stating the invariant and its owner; `nonisolated(unsafe)` for compatibility bridges; `MainActor.assumeIsolated`-family dynamic checks where runtime structure (main-thread-only frameworks like UIKit entry points) is guaranteed but invisible to the compiler.
4. **Framework-boundary friction — isolate at the boundary.** UIKit/AppKit types are `@MainActor`; background work feeding UI must hop deliberately (`await MainActor.run { }` or actor methods). Serial-queue-based legacy APIs surface as non-Sendable closures; wrap them in async bridges with clear isolation rather than letting them leak `@unchecked` through the codebase.

**Migration workflow per target:**

1. **Enable targeted warnings, fix the trivial.** Typo-level fixes (missing `Sendable` on public value types, `@preconcurrency import` for un-audited dependencies) clear most of the volume cheaply.
2. **Complete warnings, triage into the taxonomy.** Work file-by-file or feature-by-feature; each warning gets a class and a fix from the corresponding row. Track the count; it should only decrease.
3. **Bound `@unchecked Sendable`.** Every use carries a comment (invariant + owner) and a count tracked in CI (`grep -rc "@unchecked Sendable"`). A rising count is the swamp metric — it means classification is being skipped.
4. **Audit dependencies.** Third-party libraries without Sendable-awareness generate noise; `@preconcurrency import` quiets them per-import (deliberate, visible, removable when the library updates). Check the library's Swift 6 status before adopting it into concurrent code paths.
5. **Flip the target to Swift 6 mode** (errors) only when the warning count is structurally zero — not suppressed to zero, fixed to zero with suppressions bounded and reviewed. One target at a time; new code in migrated targets gets compile-time races for free forever.

**Rollout strategy at team scale:** start with leaf targets (models, utilities — few dependencies, high Sendable density), then feature modules, app targets last (they carry the framework-boundary friction). Keep the ladder set in CI at the maximum achieved level so regressions are new warnings on the next build, never silent. A new module created mid-migration starts life at the strictest level — never birth non-strict code.

A worked example: a feed app's `ImageCache` — a class with a dictionary, accessed from network callbacks and the main thread — produces complete-checking errors. Classification: genuinely unsafe (it was the cause of a rare crash report triad). Fix: convert to an actor (`actor ImageCache` with `func image(for:) async throws -> UIImage`); call sites `await`; UI updates hop to `@MainActor`. The class's stored `UIImage` crosses domains — UIKit's main-actor-ness handled by returning through the actor and hopping at the call site. Three warnings, three classes, one architecture change instead of one `@unchecked Sendable` hiding a real bug.

## Controls

- CI enforces the maximum-achieved checking level per target; target-level settings only ratchet up (`minimal → targeted → complete → Swift 6 mode`), and lowering requires an explicit exception documented in the PR.
- `@unchecked Sendable` and `nonisolated(unsafe)` counts tracked and trended per target; every instance carries an invariant comment with an owner; new instances require PR justification.
- New modules and files start at the strictest active level; scaffolding/templates embed the settings.
- Dependency audit in review: libraries used across isolation domains must be Sendable-aware or wrapped at a single audited boundary (`@preconcurrency import` confined to that boundary module).
- Migration progress is a tracked metric (warnings-by-class remaining per target) reviewed in planning until closure — concurrency debt made visible, not vibes.

## Validation evidence

- The checking levels (`minimal`, `targeted`, `complete`), Swift 6 language-mode error semantics, `Sendable`/`@unchecked Sendable`, actor isolation and `@MainActor`, region-based isolation with `sending`, `isolated` parameters, `nonisolated(unsafe)`, and `@preconcurrency` are specified in the Swift language documentation and Swift 6 migration guide published at swift.org, with evolution proposals (SE-0302, SE-0337, SE-0414 family) documenting the underlying semantics.
- The per-target build settings (`SWIFT_STRICT_CONCURRENCY`, language mode) are documented in Swift and Xcode build-setting references.
- A reproducible proof of value: write a class with unsynchronized shared mutable state accessed from two detached tasks; under minimal checking it compiles; under complete/Swift 6 mode the compiler rejects it — the same code, the race the diagnostic exists to catch, demonstrated in a two-file scratch target before the team's migration begins.

## Failure modes and correction

- **`@unchecked Sendable` swamp.** Symptom: warnings gone, races not — suppression masquerading as migration. Correct by the count metric and the classification discipline (each unchecked use must argue it's class 3, not class 1).
- **Sendable-by-annotation on mutable classes.** Symptom: compiler silenced on genuinely shared state; crashes persist. Correct by refusing `@unchecked` in review for anything not proven externally synchronized.
- **Boundary friction smeared everywhere.** Symptom: `MainActor.run` sprinkled through business logic. Correct by isolating hops at framework-adapter layers.
- **Stuck at warnings forever.** Symptom: "complete warnings" enabled for a year. Correct by the ratchet + per-target flip plan with the warnings-by-class metric driving scheduling.
- **Dependency noise flooding the signal.** Symptom: can't see your violations among the library's. Correct by `@preconcurrency import` scoping and library upgrades/audits.

## Limitations

- Complete checking proves what the type system can express; dynamic structure (queue guarantees by convention, C-interop invariants) needs the escape hatches and their manual discipline.
- Libraries without Swift concurrency audits remain friction sources until they update; wrapping costs code.
- Swift 6 mode across mixed-language targets (C/C++/Objective-C interop) surfaces additional boundary work the pure-Swift ladder doesn't prepare for.
- Migration costs real engineering time on large codebases; the ladder exists precisely because big-bang flips don't.

## Canonical sources

- Swift.org, Swift 6 migration guide and strict concurrency documentation (checking levels, migration ladder): https://www.swift.org/documentation/concurrency/
- Swift.org, Sendable and actor isolation evolution documentation (SE-0302 Sendable and @Sendable closures; SE-0306/SE-0316 actors and global actor inference): https://github.com/swiftlang/swift-evolution
