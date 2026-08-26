# Apple App Intents authorization boundaries

**Issue:** App Intents expose application actions through Siri, Shortcuts, Spotlight, widgets, and other system surfaces. Reusing an in-app function without explicit authorization and execution rules can make a sensitive action available while the app or device is in an unexpected state.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Treat every App Intent as a public application entry point. Define its authentication policy, allowed execution targets, foreground requirements, parameters, and idempotency deliberately, then call the same domain authorization layer as the foreground app.

## Controls

- Select an `IntentAuthenticationPolicy` matching the action’s sensitivity.
- Never use `alwaysAllowed` for an operation that should require an unlocked or authenticated context.
- Constrain supported execution modes and request foreground continuation when safe completion needs UI.
- Validate and authorize resolved entities against the current account and tenant.
- Require confirmation for destructive, financial, or externally visible actions.
- Keep `perform()` idempotent or protect it with a durable operation key.
- Localize title, description, dialogs, and parameter summaries.
- Inject auditable dependencies rather than reaching uncontrolled global state.
- Return minimal result data to system surfaces.

## Verification

Invoke from Siri, Shortcuts, Spotlight, widgets, locked and unlocked device states, foreground and background, wrong account, stale entity, cancellation, and duplicate execution. Assert that direct intent invocation cannot skip domain authorization. Test localized disambiguation and confirmation text.

## Gotchas

Discoverability is not authorization. Parameter resolution can identify a stale or similarly named entity. An intent may run outside the app’s usual UI sequence; never rely on a screen having initialized security state.

## Sources

- [Apple App Intents overview](https://developer.apple.com/documentation/AppIntents/app-intents)
- [Apple AppIntent protocol](https://developer.apple.com/documentation/AppIntents/AppIntent)
- [Apple IntentAuthenticationPolicy](https://developer.apple.com/documentation/appintents/intentauthenticationpolicy)
