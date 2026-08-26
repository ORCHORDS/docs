# Declarative Shadow DOM Serialization and Cloning

**Issue:** Server-rendered components can lose shadow roots during serialization, cloning, or hydration, while unsafe HTML restoration can introduce injection vulnerabilities.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use a `template` with `shadowrootmode` for declarative shadow DOM and opt into `shadowrootserializable` or `shadowrootclonable` only when a component genuinely needs those behaviors. Serialization through `getHTML()` excludes child shadow roots by default; request serializable roots explicitly. Cloning includes a shadow root only when it was created clonable.

Treat serialized markup as untrusted at every storage or transport boundary. Prefer sanitized APIs and Trusted Types. `setHTMLUnsafe()` is accurately named: it must not receive untrusted strings merely because the source was previously serialized. Keep closed roots out of generic diagnostics unless the component explicitly authorizes inclusion.

During hydration, detect an existing declarative root and attach behavior to it rather than trying to create a second root. Define ownership for event listeners and state so cloning markup does not clone runtime behavior or confidential state.

## Verification

Test server parse, streaming parse, hydration, `getHTML()`, nested serializable roots, clone/import, open/closed modes, and unsupported browsers. Feed mutation-XSS payloads and prove the sanitizer boundary remains effective. Verify form labels, focus delegation, slots, custom-element upgrade order, and no duplicate listeners.

## Gotchas

Serialization is not sanitization. `innerHTML` does not serialize shadow roots. A cloned DOM tree does not clone JavaScript listeners or application state. Browser serialization can escape attribute characters differently, so avoid brittle string-equality tests.

## Sources

- [MDN ShadowRoot.serializable](https://developer.mozilla.org/en-US/docs/Web/API/ShadowRoot/serializable)
- [MDN ShadowRoot.getHTML](https://developer.mozilla.org/en-US/docs/Web/API/ShadowRoot/getHTML)
- [WHATWG HTML declarative shadow roots](https://html.spec.whatwg.org/multipage/scripting.html#attr-template-shadowrootmode)
