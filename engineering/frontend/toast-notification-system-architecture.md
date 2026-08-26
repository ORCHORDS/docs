# toast-notification-system-architecture

**Issue:** Every app accumulates toasts, and every team reinvents them badly: toasts that stack into an unclickable pile covering the primary button, timers that expire while the user is reading, duplicates spamming five "Saved" messages in a row, and screen readers announcing nothing at all (or announcing each item in a list where live-region semantics break — a documented Sonner issue #<number> pitfall). A toast system is a small piece of product infrastructure: it needs queueing, deduplication, promise lifecycle, keyboard dismissal, and live-region semantics designed as one coherent thing rather than a component copy-pasted between features.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Semantics: what deserves a toast

1. **Toast asynchronous outcomes and background events, not every action.** Save success for an explicit button press usually does not need a toast (the UI state already changed); a background sync failure, a completed export, or a queued action that finished while the user was elsewhere does. Reserve toasts for events the user could otherwise miss.
2. **Errors get actionable text and persistence.** An error toast that vanishes in four seconds deletes the only record of what went wrong. Error toasts need longer or infinite duration, the error message (not "Something went wrong"), and an action ("Retry", "View log"). If the user cannot recover from the error in the toast, promote it to an inline banner or dialog.
3. **Never put critical info exclusively in a toast.** Screen-reader users navigating by forms mode, users on slow devices where the toast renders late, and users looking away all miss it. The toast is an alert layer; the source of truth lives in the page state.
4. **Pick one severity model and enforce it.** Success (brief, auto-dismiss), info (brief), warning (longer, optional action), error (persistent until dismissed or fixed). Ad-hoc per-call durations drift toward every toast being annoying or every toast being missed.

## Queueing, stacking, and lifecycle

1. **Cap the visible stack and collapse the rest.** A max of ~3 visible toasts with an overflow indicator ("+2 more") keeps the corner usable. Unbounded stacking over the app's primary actions is a self-inflicted usability bug during batch operations.
2. **Deduplicate by key.** Rapid-fire identical events (ten websocket "connected" flips, ten autosaves) must coalesce into one toast — either update the existing toast in place or bump its timer, never render ten siblings. Sonner-style APIs support an `id` to update an existing toast; use it for anything triggered by repeatable events.
3. **Pause timers on hover AND focus.** Mouse hover pausing is table stakes; keyboard focus pausing is the a11y-correct extension so keyboard users get the same extended reading time. Also consider pausing when the tab is backgrounded (Page Visibility API) — a toast that expires while the user is in another tab may as well not have fired.
4. **Decide the timer policy explicitly.** Sonner's default is ~4s auto-dismiss; longer text needs longer timers (a common heuristic is a base duration plus time proportional to message length). Loading/promise toasts have no timer at all — they resolve when the operation resolves.
5. **Handle the promise lifecycle correctly.** For async operations show a loading toast, then transition to success/error. Library behavior differs: react-toastify updates the promise toast in place, while Sonner dismisses the loading toast and fires a new one — know which your library does, because in-place updates preserve position while dismiss-and-recreate re-triggers screen-reader announcements.
6. **Support Escape dismissal but not click-through.** Escape dismisses the focused (or topmost) toast; clicking the toast body should focus/activate it rather than silently close, so accidental clicks do not destroy an error message the user was reading.

## Accessibility mechanics

1. **Use a single correctly-configured live region, not one per toast.** The container is `role="region"`/`aria-live="polite"` (assertive only for genuine emergencies); individual toasts must not each wrap themselves in live-region markup — nested live regions inside list items cause some screen readers to miss announcements entirely (the Sonner issue #<number> lesson).
2. **Prefer polite over assertive.** Assertive interrupts whatever the screen reader is saying; for 99% of toasts ("Saved", "Export ready") polite is correct. Reserve assertive for data-loss-imminent warnings.
3. **Announce dynamically-added toasts only once.** Content present when the live region first renders is not announced by most AT; only mutations are. Toast systems that render the full list into a fresh container per toast re-announce everything — another reason for one stable container element.
4. **Keep the accessible name meaningful.** Icon-only close buttons need `aria-label="Dismiss notification"`; the toast message itself should be concise text (screen readers read all of it, so multi-paragraph legal text in a toast is an AT nightmare).
5. **Give keyboard users a path to every action in a toast.** If a toast has a "Retry" button, Tab must be able to reach it before the toast expires — which is the concrete argument for focus-pauses-timer.

## Implementation choices

1. **Sonner (Emil Kowalski) is the current default for React.** Small, unstyled-friendly, ships the hover/focus pause, stacking, promise toasts, and per-position containers; its author's writeup ("Building a toast component") covers the edge cases (tab switching, timer pausing) worth stealing even if you roll your own.
2. **react-hot-toast or react-toastify remain fine for existing stacks.** Choose on behavioral details (in-place promise updates vs dismiss-and-recreate, styling API, bundle size) rather than demos; migrating toast call sites is cheap but the a11y behavior is what users feel.
3. **One global toaster, mounted once at the root, called via a module API.** `toast()` callable from anywhere (event handlers, query onError defaults, routers) without prop-drilling or context wiring; features that need per-component toasts are usually misusing toasts for validation feedback that belongs inline.
4. **Centralize default options per severity.** Configure once (duration, position, max visible) at the app level so feature teams cannot each pick a different corner of the screen; the fastest way to a messy UI is five teams choosing toast positions independently.
