# ci-contract-drift-structural-selectors-2026

**Issue:** Repository contract tests and policy verifiers can fail even when runtime behavior is correct because they anchor on human-readable labels or stale expected values instead of the behavior or canonical source they intend to protect.
**Date:** 2026-08-19
**Author:** ORCHORDS
**Status:** verified-live
**Source:** https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
**Source:** https://docs.github.com/en/actions/reference/workflows-and-actions/contexts

## Symptom

A previously green CI lane starts failing after an unrelated refactor or release-state change even though the production contract still exists.

Two common forms:

1. A source-contract test searches a workflow for an exact display label such as a step `name:`. The step is renamed, but its `env`, command, permissions, and behavior are unchanged. The test reports the contract as missing.
2. A policy verifier hard-codes an old release-state value while the canonical application configuration has intentionally advanced. The verifier now contradicts the source of truth.

The result is a **false negative**: CI is red, but the protected runtime behavior is not actually broken.

## Root cause

The verifier accidentally treats presentation or duplicated policy text as the contract.

Fragile selectors include:

- workflow step display names;
- comments;
- ordering of unrelated YAML fields;
- copied status literals maintained in a second file;
- file paths that are incidental rather than semantically required;
- formatting-dependent regular expressions.

These values are easy to change without changing behavior, so they create maintenance coupling instead of safety.

## Preferred contract hierarchy

When writing repository contract tests, anchor on the strongest semantic signal available:

1. **Executable behavior or public API** — preferred when practical.
2. **Canonical machine-readable configuration** — one source of truth, imported or parsed directly.
3. **Structural source pattern** — narrowly identify the block by behavior, keys, commands, or bindings.
4. **Human-readable display label** — use only when the label itself is part of the required contract.

If a verifier must duplicate an expected literal, document why the duplication is intentional and add a synchronization mechanism.

## Workflow selector pattern

Bad:

```js
const block = workflow.match(
  /- name: Sync service configuration[\s\S]*?env:\s*([\s\S]*?)\s*run:/,
);
```

This fails when the display name changes even if the configuration inventory and synchronization loop remain identical.

Better:

```js
const block = workflow.match(
  /env:\s*([\s\S]*?)\s*run:\s*\|\s*\n\s*json='\{\}'[\s\S]*?for name in /,
);
```

The selector anchors on the behavior being protected: creation of a configuration bundle plus the synchronization loop.

Still better, when feasible: parse YAML and assert the relevant step's structured `env` keys and commands rather than matching raw text.

## Canonical-state verifier pattern

Bad:

```js
for (const expected of [
  'featureA: "unavailable"',
  'featureB: "unavailable"',
]) {
  if (!canonical.includes(expected)) throw new Error(...);
}
```

This becomes stale the moment the product intentionally enables those capabilities.

Preferred options:

- import the canonical configuration into a test and assert invariants rather than a historical state;
- parse the source once and derive public-copy checks from the same value;
- if a transition is intentionally gated by policy, change the canonical state and its policy verifier in the same reviewed change.

Examples of durable invariants:

- a capability renders only when its canonical state permits it;
- production-sensitive features fail closed when configuration is absent;
- public copy reflects the canonical capability state;
- a deployment configuration inventory covers every declared runtime binding.

## Debugging sequence

When a source-contract test fails:

1. Read the exact failing assertion before changing runtime code.
2. Inspect the current canonical runtime/workflow source.
3. Determine whether the protected behavior is genuinely absent or only the selector/expected literal changed.
4. If runtime behavior is intact, fix the verifier rather than mutating production configuration to satisfy a stale test.
5. Run the focused test first, then the full type/lint/unit/policy sequence.
6. Record the discovered drift so future failures are easier to diagnose.

## Guardrails

- Never change secret values or production configuration merely to make a source-contract regex pass.
- Do not weaken the assertion's intended coverage while making its selector less fragile.
- Keep selectors narrow enough that they cannot accidentally bind to another unrelated workflow block.
- Prefer one canonical source over duplicated expected-value lists.
- A green test is not proof of runtime behavior if the test only checks labels or comments.
- A red contract test is not proof of runtime breakage until the canonical source is inspected.

## Native/readiness corollary

The same principle applies to platform build lanes. If an Android, iOS, or desktop-native target has not actually been bootstrapped, CI should report a deterministic **blocked/readiness** result rather than inventing a green build lane. Readiness checks should verify real prerequisites—project files, toolchain pins, tests, application identifiers, capabilities, and wrappers—before native build task names are enabled.

This prevents false evidence such as:

- claiming Android coverage when no Gradle project exists;
- claiming iOS coverage when no Xcode workspace/test targets exist;
- claiming desktop-native coverage when the chosen native shell has not been created;
- treating responsive browser tests as native-platform certification.

## Related

- `draft-pr-readiness-gated-review-2026.md`
- `stacked-prs-workflow-2026.md`
- `branch-protection-codeowners-2026.md`
- testing/contract-testing and CI-pattern entries
