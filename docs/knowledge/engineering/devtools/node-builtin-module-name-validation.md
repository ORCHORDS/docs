# Node.js builtin-module name validation

**Problem**

String-prefix checks for builtin modules can misclassify aliases or user packages and create unsafe loader policy.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use in resolvers, bundlers, or policy tools that distinguish Node builtins.

## Controls

- Use `module.isBuiltin()` on the pinned Node version.
- Decide whether `node:` and bare forms are normalized.
- Keep builtin status separate from permission.

## Implementation

- Validate before custom resolution.
- Record normalized specifier, not user-controlled source.
- Update fixtures on Node upgrades.

## Tests

- Test bare/prefixed builtins, subpaths, near-name packages, Unicode, and new releases.

## Gotchas

- Builtin sets evolve.
- Builtin does not mean safe for untrusted code.
- Bundlers may polyfill names.

## Official sources

- [Official documentation](https://nodejs.org/api/module.html#moduleisbuiltinmodulename)
