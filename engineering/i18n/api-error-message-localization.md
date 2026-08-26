# api-error-message-localization

**Issue:** APIs serve two audiences at once: client code that must branch on what went wrong, and humans who read the message when something fails. Teams conflate the two by putting human-readable English sentences in error responses, which clients then display untranslated, or worse, which clients string-match on to infer behavior. Meanwhile the same backend serves users in dozens of locales whose clients legitimately want to show the error in the user's language. The engineering problem is separating stable machine-readable error identity from localizable human text — the modern answer being RFC 9457 Problem Details — deciding where translation happens (server-rendered per Accept-Language versus client-side catalogs keyed by error code), interpolating dynamic values safely into localized messages, and never leaking internal details under the guise of "detail".

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Separating machine identity from human text

1. **type is the stable contract.** RFC 9457 defines a problem detail object with type (a URI identifying the error class), title, detail, status, and instance. The consensus implementation guidance is that type must be a stable, never-localized identifier clients switch on; title and detail are advisory human text. If clients branch on the text of detail, the contract is already broken.
2. **Error codes over prose.** Define a closed enum of error codes (one per user-actionable failure: account_suspended, card_declined.insufficient_funds, rate_limited) and make them the join key between backend, client catalogs, and analytics. Every new code is an API design decision with documentation, not a free-form sentence a developer typed during an incident.
3. **Extension members for sub-codes and fields.** RFC 9457 allows extension members; use them for machine-readable structure — an errors array with field-level codes for form validation, retry-after for rate limits, required-action URIs for onboarding blockers. Clients then map each code to their own localized strings with full fidelity.
4. **One error, one identity, forever.** Renaming or recycling a type URI is a breaking change: old clients match on it. Version problem types like APIs (…/errors/insufficient-funds) and treat their stability with the same discipline as route paths.

## Where translation happens

1. **Client-side catalogs as the default.** The cleanest split: the server returns codes plus parameters, and each client renders the message from its own translation catalog using the same ICU resources as the UI. This guarantees the error message matches the app's language instantly (including offline), reuses existing pluralization infra, and keeps the API locale-neutral.
2. **Server-rendered messages when the client is not yours.** Public APIs consumed by third parties cannot ship your catalogs; there, honor Accept-Language on the request and localize title/detail server-side via content negotiation, while keeping type and codes constant. Both models can coexist: localize detail for Accept-Language-bearing requests, and always include codes so first-party clients ignore the server text.
3. **Vary correctly when server-localizing.** If responses vary by Accept-Language, set Vary: Accept-Language (or use the newer structured field variants) so caches do not serve German errors to Japanese users from a shared CDN cache. This composes with the general content-negotiation rules for locale-sensitive responses.
4. **Logs and support in one canonical language.** Localize only the outward-facing copy; internal logging, alerting, and support tooling should key on the error code and log canonical English diagnostics. Localized error text in server logs makes cross-locale incident analysis needlessly hard.

## Interpolation and safety in localized errors

1. **Pass parameters, not pre-joined sentences.** A rate-limit error should carry limit and reset-time as structured members; the client composes "Too many attempts — try again in 5 minutes" from its catalog with proper plurals and number formatting for the locale. Pre-joined server text forecloses correct grammar, word order, and plural rules in every language but English.
2. **ICU for error strings too.** Error messages embed counts ("3 fields need attention") and selections; author them in ICU MessageFormat in the same catalogs as UI strings, with translator context describing where the string appears (toast, form banner, API docs).
3. **Never interpolate user input back unescaped.** When detail includes user-supplied values (an invalid username, a colliding email), escape and length-limit them; reflected user input in API responses consumed by web clients is an injection surface.
4. **Redact internals.** detail is advisory human text, not a debugging channel: stack fragments, SQL, internal hostnames, and PII do not belong. Correlate debugging through an error identifier (instance or a trace id extension member) that support can look up server-side.

## Testing and governance

1. **Contract tests pin every emitted code.** A snapshot test enumerates all error paths the API can emit and asserts each returns a documented type/code pair. Any new undocumented error code fails CI — this is the only way to keep the client catalog complete.
2. **Catalog completeness check.** CI cross-references the enum of error codes against every client locale catalog: a missing translation for zh-TW fails the build exactly like a missing UI string, with fallback-locale behavior applied consistently.
3. **Fuzz the human-adjacent surfaces.** Invalid UTF-8, very long inputs, and unicode edge cases in user-supplied values must not produce errors whose own detail is unrenderable; fuzz endpoints and assert responses serialize cleanly.
4. **Verify the language actually follows the user.** For server-localized responses, integration-test the Accept-Language negotiation matrix (exact match, fallback chain, q-values, unknown locale) against fixtures in at least an LTR, an RTL, and a heavily-inflected language, and assert cache keys differentiate by negotiated language.
