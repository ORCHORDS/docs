# ios-live-activities-dynamic-island

**Issue:** Live Activities put your app's state on the Lock Screen, the Dynamic Island, and (since recent releases) CarPlay, paired Macs, and Apple Watch, and they are now expected UX for deliveries, rides, sports scores, and live sessions. Engineering them well is harder than the SwiftUI marketing suggests: updates can arrive via local ActivityKit calls or via push through per-activity APNs tokens that rotate mid-lifecycle, Apple enforces an opaque update budget that throttles pushes when exceeded (tightened further since iOS 18 with lower effective refresh rates), and layouts must degrade gracefully across five differently-sized surfaces. This article covers the lifecycle, token, budget, and design constraints that determine whether a Live Activity feels live or broken.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Surfaces and content model

1. **One activity, five surfaces.** The same ActivityAttributes render on Lock Screen (banners and the list), Dynamic Island (compact lead/trail pair and expanded), StandBy, CarPlay, and mirrored Mac/Watch contexts. Design content states, not layouts: define what the data looks like, then adapt per surface.
2. **ContentState must be small and Codable.** Every update serializes your ContentState through the system and over push; keep it to a handful of primitive fields, not nested view models. Large states inflate payload, slow rendering, and waste update budget.
3. **Glanceable beats complete.** Lock Screen real estate and glance time are seconds at most. Show the two values that changed (score, ETA, price) and push everything else into the expanded island view or the app itself.
4. **Pick activities with true beginnings and ends.** Activities for a delivery, a flight, or a trading session have natural lifecycles; using them as persistent widgets is a rejection and battery hazard, and stale abandoned activities are the number one source of negative reviews for Live Activity apps.

## Starting, updating, and ending

1. **Start from the foreground or a push.** Local starts via Activity.request fire instantly when the app is active; push starts (via the activity push type on your stored push-to-start token) let a server begin an activity for an event the user is not watching the app for.
2. **Always end activities explicitly.** Activities auto-end after roughly 8 hours on the Lock Screen, but that ceiling is a safety net, not a design. Call activity.end with a final ContentState so the last frame shows the outcome (delivered, finished, cancelled) instead of a stale intermediate.
3. **Use dismissal policies deliberately.** .immediate removes the ended activity at once, .after(Date) lets the final state linger briefly (good for "order delivered" receipts), and .atLeast keeps it until the user dismisses; choose per use case rather than defaulting.
4. **Handle stale activities on launch.** Enumerate Activity<YourAttributes>.activities at startup and reconcile with server truth: resume updating the ones still live, end the ones the server says finished while the app was dead.

## Push updates, tokens, and the budget

1. **Every activity has its own APNs push token.** When an activity starts, ActivityKit issues a per-activity token that your server must use to target it. Store it keyed by (user, activityId) and treat losing it as losing the ability to update that activity at all.
2. **Tokens rotate mid-lifecycle; monitoring is mandatory.** Subscribe to token updates via activityUpdates (or the async stream for token changes) and immediately push the new token to your backend. A rotated token silently invalidates the old one, and updates sent to stale tokens just stop landing, which presents in production as "Live Activity froze."
3. **Respect the update budget or get throttled.** ActivityKit push updates are rate-limited by an undisclosed budget; exceed it and the system throttles subsequent pushes. Batch related changes, update only on meaningful deltas, and never design an activity that needs second-by-second pushes (use a countdown timer in the view for time, not pushes).
4. **NSSupportsLiveActivitiesFrequentUpdates only helps at the margins.** The Info.plist flag requests a higher update allowance, but it is not unlimited and Apple tightened effective refresh behavior starting in iOS 18. Design within the default budget and treat the flag as a modest boost.
5. **Send pushes with the right priority and headers.** Live Activity updates use the activity push type with apns-priority tuned down (low-priority updates avoid waking the device aggressively) and a stale date after which the update should be dropped rather than delivered late.

## Design and rendering constraints

1. **Design the compact island pair first.** The compact Dynamic Island splits into a small leading/trailing pair; if your content does not work at that size with a single icon and two short text values, the use case is wrong for the island, and you can legitimately lock content to the Lock Screen.
2. **Animate state transitions, not time.** SwiftUI transitions and the built-in content transition helpers animate value changes; combining them with a per-second timer that is not push-driven keeps the activity live-looking without budget burn.
3. **Dark, dimmed, tinted contexts.** Lock Screen rendering applies system materials and tinting; test with colorful app branding, photos, and light-on-light color pairs that vanish in the dimmed state.
4. **Interactive buttons have limits.** Deep-link taps from activities are fully supported; heavier interactivity must open the app, so design tap targets as "open and act" rather than trying to replicate app UI on the lock screen.

## Operations and QA

1. **Instrument update delivery end to end.** Log token issuance, rotation, push sends, and ack outcomes server-side; the freeze complaints will arrive as "widget stopped" with no client-side error, and only server logs explain which token or budget failure occurred.
2. **Test long-running activities across device states.** Budget behavior, auto-end ceilings, and surface availability differ across iOS versions and hardware (island versus notch). Run a scripted overnight test: start activity, background the app, lock the screen, toggle airplane mode, and verify recovery and final end-state on reconnect.
3. **Cap concurrent activities per user.** Requesting many simultaneous activities burns budget across them and clutters the Lock Screen; most products should enforce one live activity per category per device.
