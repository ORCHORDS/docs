# webassembly-component-model-capability-boundaries

**Issue:** A WebAssembly component exposes more host functionality than it needs because its imports and exports are not reviewed as a capability contract.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A plugin or sandboxed module can access filesystem, network, clocks, randomness, or host APIs that are unrelated to its intended task. The interface boundary is implicit in runtime glue rather than a reviewed design artifact.

## Root cause

In the WebAssembly Component Model, a WIT world declares imports and exports. Those declarations can serve as a capability boundary, but only if the host supplies the minimum required interfaces and treats interface changes as security-relevant API changes.

**Source:** [Bytecode Alliance — Component Model worlds](https://component-model.bytecodealliance.org/design/worlds.html).

## Fix

- define one WIT world per component role with explicit imports and exports;
- expose narrow host interfaces instead of a general-purpose host API;
- require a security review for new capabilities, especially filesystem, network, process, time, randomness, and secret access;
- version interfaces compatibly and test consumers against the declared contract;
- enforce runtime resource limits separately from interface restrictions;
- log capability-denied operations without exposing sensitive arguments.

## Verification

- A component can invoke only the interfaces declared for its world.
- Removing an unneeded import prevents the associated host operation.
- An interface-version change is reviewed, compatibility-tested, and documented.
- Resource-limit tests prevent a valid component from exhausting host capacity.

## Gotchas

- A typed interface is not an authorization decision; the host must still authenticate and authorize callers.
- Capability minimization does not prevent logic bugs inside an allowed interface.
- Do not add a “utility” import that becomes a back door for unrelated host features.

## Related

- `cloudflare/sandbox-2026.md`
- `security/ai-agent-security.md`
- `patterns/hexagonal-architecture.md`
