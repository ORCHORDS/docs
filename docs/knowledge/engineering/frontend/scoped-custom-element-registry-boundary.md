# Scoped custom-element registry boundary

**Issue:** Scoped custom-element registries let separate component trees use different definitions for the same custom-element name. Assuming a global constructor breaks hydration, cloning, upgrades, and third-party isolation.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental

## Controls and implementation

Create registries at component-shell boundaries, bind them deliberately to shadow roots, and keep constructors/imports versioned. Do not move nodes between registry scopes without a defined adoption path. Provide an unsupported fallback and prevent registry choice from changing security semantics.

## Verification

Test duplicate names across scopes, upgrade timing, SSR/hydration, cloning/adoption, declarative shadow DOM, teardown, and unsupported engines.

## Gotchas

Element identity is name plus registry context; global `customElements.get()` is not authoritative for scoped trees.

## Sources

- WHATWG, [HTML — scoped custom element registries](https://html.spec.whatwg.org/multipage/custom-elements.html#scoped-custom-element-registries)
