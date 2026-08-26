# signals-fine-grained-reactivity

**Issue:** Most component frameworks historically re-render by diffing a component tree (VDOM) whenever state changes, which wastes work: changing one value re-runs whole components even when a single text node depends on that value. Signals invert this model with push-based, fine-grained reactivity — a reactive value knows exactly which computations and DOM bindings depend on it, so an update touches only those nodes and skips re-rendering entirely. As of 2025-2026 this is no longer a niche idea: Angular rebuilt its reactivity around signals and zoneless change detection, Solid and Preact popularized it, Vue adopted signal-like reactivity primitives, and a cross-framework TC39 proposal is standardizing the primitive at the language level. Teams choosing a state architecture today need to understand how signals differ from hooks/VDOM, what the TC39 proposal does and does not standardize, and the failure modes (conditional dependencies, effect chains, memory leaks from untracked subscriptions) that signal-based code introduces.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How fine-grained reactivity differs from VDOM re-rendering

1. **Dependency tracking instead of tree diffing.** When a computed or effect reads a signal, the runtime records that edge in a dependency graph. On write, only the dependents of that exact signal are invalidated — no component function re-runs, no VDOM diff walks the tree.
2. **Signals are values with subscribers, not framework state.** A signal can live outside any component, be passed around as a plain reference, and be read by multiple frameworks or vanilla TypeScript. This decouples state ownership from the component tree.
3. **DOM bindings instead of re-render.** In libraries like Solid, JSX compiles to direct DOM update expressions (template cloning plus targeted writes). The "render" runs once to set up bindings; afterwards, data changes patch text nodes, properties, and attributes directly.
4. **Glitch-free synchronous propagation.** Signal implementations batch and topologically sort the dependency graph so each computation runs at most once per update cycle, avoiding the intermediate-state "glitches" you get when effects trigger effects in unmanaged order.
5. **Cheaper mental model for derived state.** Because computed chains re-execute lazily and only invalidated branches, teams can model more state as derivations rather than synchronized copies stored in stores or effects.

## The framework landscape (2025-2026)

1. **SolidJS.** The pioneer of signals-plus-compiled-JSX rendering; components run once and fine-grained updates replace re-rendering. Solid 2.0 work has aligned its core primitives closely with the TC39 proposal shape.
2. **Preact Signals.** The @preact/signals package adds signals to Preact with near-zero-cost integration into JSX, proving the model can be retrofitted onto a VDOM library — signal reads in JSX become direct bindings, and unchanged branches skip diffing.
3. **Angular.** Signals (v16 onward) are now the core reactivity model: signal(), computed(), effect(), linkedSignal(), and input() replace much of zone.js-driven change detection, enabling zoneless apps where Angular only updates views where signal dependencies changed.
4. **Vue.** Vue 3 reactivity (ref, reactive, computed) is signal-like proxy-based tracking; the reactivity system is usable standalone via @vue/reactivity, and Vue team members contribute to the TC39 proposal.
5. **Qwik and Starbeam.** Qwik uses signals as its core reactivity for resumability (no hydration); Starbeam (from the Ember/Glimmer ecosystem) provides a framework-agnostic reactive toolkit designed to interoperate with the standard proposal.

## The TC39 Signals proposal

1. **Status: advancing, not yet Stage 3.** As of 2025 the JavaScript Signals proposal (tc39/proposal-signals) remains in early-to-mid stages, with the committee still refining graph semantics, effect scheduling, and memory management. Do not ship production code that assumes the global Signal API exists.
2. **Core primitives under standardization.** The proposal defines Signal.State (writable value), Signal.Computed (derived value with automatic tracking), and an effect/watcher API with equality configuration — the low-level building blocks, intentionally without a prescribed component model.
3. **Cross-framework authorship is the point.** Authors and contributors come from Solid, Preact, Angular, Vue, Svelte, Qwik, Starbeam, and MobX. The goal is interoperability (shared reactive state across framework boundaries) and engine-level optimization that userland implementations cannot match.
4. **Higher-level helpers are follow-ons.** Ergonomic wrappers (subscribing to observables, async signals, signal utilities) are deliberately deferred to layered proposals so the core stays minimal and semantics stay testable.
5. **Design for portability now.** Even before standardization, keeping signal usage behind small adapters (a createSignal/compute/effect facade per app) makes it cheap to swap implementations or adopt the standard later.

## Best practices when building with signals

1. **Prefer computed over duplicated state.** Model anything derivable as a computed chain instead of storing a second signal synchronized by an effect. Effects that write other signals are the number one source of infinite loops and ordering bugs.
2. **Effects are for the outside world only.** Use effects for DOM manipulation, logging, analytics, and persistence — side effects that cannot be expressed as derivations — never for deriving state.
3. **Watch conditional reads.** Reading a signal inside an if branch only registers a dependency when the branch executes; a later change to the skipped signal will not re-run the computation. Restructure so all conditionally-needed signals are unconditionally tracked, or re-read inside the derived logic.
4. **Use custom equality deliberately.** Passing an equality function to a signal or computed (shallow compare, id compare) prevents downstream recomputation when the value is observationally unchanged — critical for arrays and objects produced fresh each time.
5. **Dispose subscriptions and effects.** Effects created outside a component's ownership (in services, stores, or vanilla code) must be manually disposed, or the dependency graph retains listeners and leaks memory across route changes.
6. **Keep stores signal-first.** In a signals architecture, a "store" is a module exporting signal/computed values plus mutation functions — not a class with an event emitter. This keeps updates traceable through the graph.

## Pitfalls and debugging techniques

1. **Write-in-computed crashes.** Computed values must be pure; writing a signal during a computed evaluation corrupts the graph or throws in strict implementations. Move the write into an explicit event handler or effect.
2. **Async tracking boundaries.** Dependency tracking is synchronous. Awaiting before reading a signal loses the reactive context — capture dependencies before the await, or use framework-provided async utilities designed for tracked scopes.
3. **Untracked reads in callbacks.** Reading a signal inside setTimeout or an event listener does not make the enclosing computation depend on it. Reads only track during the synchronous execution of a computed or effect.
4. **Memory leaks from long-lived graphs.** A computed that depends on a signal owned by a destroyed feature keeps that feature's objects alive. Audit with heap snapshots after route churn; look for retained subscriber arrays.
5. **Debugging tooling.** Name signals in dev builds (many implementations accept a debug name or expose a graph inspector), log effect firings in development, and write unit tests that assert how many times a computed executes — execution counts are the assertions of fine-grained reactivity.
