# multi-step-form-wizard-ux

**Issue:** Onboarding, checkout, and KYC flows are built as one giant form or as naive step components, and both fail users the same ways: no visible sense of progress, a refresh or stray back-press silently destroys everything typed so far, validation errors from step 1 surface on step 4's submit, keyboard and screen-reader users get no announcement when the step changes, and there is no way back to fix an earlier answer without re-entering everything. A multi-step wizard is a state-machine-plus-persistence problem wearing a form costume, and the UX and a11y requirements are well documented (W3C WAI multi-page forms tutorial, USWDS step indicator guidance, NN/g guidance).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Step structure and progress disclosure

1. **Chunk by mental model, not by field count.** Group questions a user thinks of together (identity, shipping, payment); 3-5 steps beats 8 micro-steps or one mega-page. Each step should answer one question the user can hold in their head ("where does this ship?").
2. **Show a persistent, honest progress indicator.** "Step 2 of 4" plus labeled steps (per USWDS step-indicator guidance) sets expectations and reduces abandonment; a bare percentage bar gives no navigational signal. Make completed steps clickable links back (see navigation below) but never let users jump forward past unvalidated steps.
3. **One primary action per step.** A single "Continue" (with a subdued "Back") removes decision fatigue; put destructive exits ("Save and exit" vs "Cancel") visually and semantically apart from the forward path. Never dual-label the same button ("Submit/Next") depending on hidden state.
4. **Progressive disclosure within steps.** Hide conditionally-irrelevant questions (e.g., billing address same-as-shipping) via conditional fields rather than branching into more steps — branch explosion is how wizards become unmaintainable state machines.
5. **Design the review step.** For consequential flows (KYC, payments), a final read-only review of all answers — with per-section edit links that jump back to the right step and return — catches errors cheaper than a post-submit rejection loop.

## State: the URL is the step, storage is the draft

1. **Encode the current step in the URL.** `?step=payment` makes refresh survive, deep-links into a step work for support ("go to step 3 and check the field"), and analytics can measure per-step funnel drop-off — the argument from `url-search-params-state-management.md` applied to wizards. Steps in component state only is the root cause of refresh-loses-everything bugs.
2. **Persist the draft to the server on step transition, not on final submit.** Saving each validated step (or debounced field-level autosave) means abandonment at step 3 of 5 still yields a recoverable lead, and users who bail out can resume by email link. LocalStorage/IndexedDB drafts cover anonymous pre-account flows; treat them as a cache of the server draft when one exists.
3. **Model the wizard as an explicit state machine.** Steps, guarded transitions (step N+1 requires step N valid), and forward/back edges belong in one definition — XState or a reducer — not scattered `setCurrentStep(n + 1)` calls. This makes invalid states (skipping ahead, submitting from step 2) unrepresentable; see `xstate-finite-state-machines.md`.
4. **Keep all answers in one form-level store.** React Hook Form's field arrays or a schema-driven store (zod/RHF resolver) spanning steps means final submit assembles one payload from one source of truth — no "step 3 state lost when its component unmounted" class of bug. Unmounting a step must not discard its values.
5. **Version the draft schema.** When you add a field mid-funnel, old drafts must load without crashing: store a `schemaVersion` with the draft and write migrations (or invalidate gracefully and tell the user what needs re-entry).

## Validation and error strategy

1. **Validate each step on exit, not on first keystroke.** Run the step's schema on "Continue"; show inline errors per field; block forward movement but never block backward. First-touch/blur validation per field is fine, but the gate is the step schema.
2. **Never lose cross-step errors.** If step 4's server validation contradicts step 1's answer (e.g., address undeliverable), route the error back to the offending field on its step, deep-link the user there, and announce the move — an error message on step 4 about a step-1 field with no navigation is a dead end.
3. **Distinguish client-gate vs server-authoritative validation.** Client schemas are UX grease (fast feedback); the server re-validates everything. Design the step gate so server rejections map back into per-step/per-field errors in the same shape the client uses.
4. **Guard double-submits and async submits.** Disable the final action in-flight, show a pending state, and make submission idempotent (client-generated draft ID) — users on flaky mobile networks retry final submits aggressively.
5. **Warn before destructive exits.** `beforeunload` guards and in-app "you have unsaved changes" dialogs on back/close only work if drafts are actually unsaved; with step-level autosave (above) the warning becomes rare and meaningful instead of a boy-who-cried-wolf modal.

## Accessibility requirements

1. **Announce step changes.** On transition, move focus to the new step's heading (or an `aria-live="polite"` status announcing "Step 3 of 5: Payment") — otherwise screen-reader users are silently left on stale content. This is the WAI multi-page-forms tutorial's core recommendation adapted to SPA steps.
2. **Mark the current step with `aria-current="step"`.** Build the step indicator as an ordered list (`<ol>`) of steps; completed steps become links, the current one carries `aria-current`, and future steps are plain text — keyboard and AT users get the same mental map sighted users do.
3. **One `<form>` per step with headings, kept in DOM order.** Use an `<h1/h2>` per step title and keep the step indicator before the form in DOM order; avoid layout tricks that visually reorder them, since reading order and focus order must agree (WCAG 2.4.3 Focus Order, covered in `wcag-2-2-accessibility-compliance.md`).
4. **Preserve focus context on back/edit jumps.** Jumping back to edit a field should focus that field; returning to review should return focus to the review section edited — context restoration is what makes deep-link navigation usable non-visually.
5. **Error summaries per step.** On failed step validation, render a summary list of errors at the top of the step, each linking to its field (`<a href="#field-id">`), in addition to inline messages; this is the single pattern that most improves error recovery for AT users.

## Testing

1. **Funnel tests through the state machine.** Unit-test the transition table: cannot skip forward, back always allowed, submit only from final step with all steps valid — these are cheap reducer tests that eliminate entire regression classes.
2. **Draft-resume end-to-end tests.** Playwright: complete steps 1-2, reload, assert step 2 restored with values; complete on another device context (fresh storage) using the same resume link; corrupt a draft (wrong schemaVersion) and assert graceful re-entry.
3. **Per-step funnel analytics in CI fixtures.** Assert the analytics events (step_viewed, step_completed, step_abandoned) fire exactly once per transition — duplicate or missing events corrupt the drop-off data the product team relies on.
4. **Keyboard-only and screen-reader passes per release.** Tab through every step, trigger every error path, and verify announcements; automated axe checks plus a manual NVDA/VoiceOver pass of the announce-on-transition behavior, since live-region behavior is exactly what automation misses.
5. **Related reading in this knowledge base:** `react-form-handling-react-hook-form.md` (field-level mechanics), `xstate-finite-state-machines.md` (the wizard state machine), `url-search-params-state-management.md` (step-as-URL), `html-form-validation.md` (native validation primitives).
