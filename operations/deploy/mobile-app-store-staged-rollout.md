# mobile-app-store-staged-rollout

**Issue:** Server deploys finish when the last pod is healthy; mobile releases finish when every device has updated — a process you control only partially, mediated by store review queues, auto-update policies, and users who never update. Teams accustomed to server-side instant rollback ship a mobile build to 100 percent on day one, discover a crash at scale, and learn that "rollback" now means shipping a new binary through review while the broken version keeps spreading. Staged rollout is the mobile counterpart of canary deployment, but its knobs, failure modes, and irreversible edges are store-specific.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Store rollout mechanics

1. **Google Play staged rollout.** In Play Console you release an update to a percentage of users (commonly ramped 1-5-20-50-100, with community guidance suggesting a 5-10 percent start) and increase it as confidence grows. The rollout can be halted before it reaches 100 percent, and the percentage can even be decreased — but devices that already received the update keep it; halting stops the spread, it does not recall the app.
2. **App Store phased release.** Apple offers a fixed 7-day automatic curve: 1, 2, 5, 10, 20, 50, then 100 percent, applying only to automatic updates (not to users who manually update from the store page, and not to first releases). You can pause for up to 30 days total or release to everyone at any moment, but you cannot choose custom percentages — the curve is Apple's.
3. **Halt semantics differ from server rollback.** On servers, rollback re-points traffic at the old version in seconds. On stores, halt freezes distribution; the remedy for a bad build is a new build. Plan for this asymmetry: the hotfix path (hotfix-branching-deployment-discipline.md) is the real mobile rollback, so the staged rollout exists to keep the bad build's population small while the fix ships.
4. **Update arrival is user-controlled.** Auto-update timing, OS restrictions, and deferred updates mean even a 100 percent rollout reaches devices over days to weeks. Any server-side compatibility surface must therefore tolerate the previous N app versions indefinitely — the mobile fleet is permanently multi-version (see api-versioning-2026.md and event-schema-compat-deploys.md).

## Gating each stage

1. **Watch the store's stability vitals.** Play Console's Android Vitals surfaces user-perceived crash rate and ANR rate per release; a spike at low rollout percentage is the halt trigger. Beyond your own threshold, poor vitals also make Google throttle the app's visibility — a commercial reason to gate, not just a reliability one. On iOS, use Xcode Organizer, App Store Connect metrics, and a third-party crash reporter (which you need because phased release metrics arrive with lag).
2. **Define numeric halt criteria before starting.** Decide in writing: halt if the new version's crash rate exceeds X times the current version's, or if ANR exceeds Y, measured over at least Z active devices. Deciding thresholds during an incident guarantees a debate instead of a halt.
3. **Gate on server-side deltas too.** The app talks to your API: compare error rates, request mixes, and payload sizes attributed to the new app version versus old via a client-version dimension on server metrics. Server logs often show a bad build misbehaving before store vitals aggregate enough users to say anything.
4. **Automate the ramp.** Tools like fastlane can drive the Play Developer API to move rollout percentages programmatically (including halting by setting the fraction to zero), so the ramp can live in CI with the same gating discipline as server progressive delivery rather than as a manual console ritual someone forgets to finish.

## Mobile-specific rollout traps

1. **Do not go to 100 percent reflexively.** Community practice (r/androiddev) is to hold at 99.x percent rather than 100, because the halt option disappears at 100. Cheap insurance when the 0.01 percent costs nothing.
2. **Review queues are part of the timeline.** A halt plus hotfix means two more review cycles (and expedited review is best-effort). The staged rollout percentage is your only real brake while the fix sits in review, which is exactly why it must not already be at 100.
3. **Backend and app must release in coordinated order.** Ship server-side support for the new app version (new endpoints, new contract fields) before the app rollout starts, and keep old endpoints alive until the fleet has drained old versions — commonly quarters, not days. A server cleanup that assumes "everyone is on the new app by Friday" is the classic mobile deploy incident.
4. **Web-shell apps (Capacitor and friends) blend the models.** A web-view shell can update its bundled web assets via store rollout, but if assets are loaded remotely, parts of the app update like a web deploy instead. Be explicit about which changes ride the store review track versus the web deploy track, and remember store review policies constrain remote-update behavior — the shell binary version is still the artifact you stage.
5. **Kill switches beat store speed.** Since you cannot recall a bad build, put risky client behaviors behind remote flags (feature-flag-deploy-coupling.md) so the staged rollout population can be protected by disabling the feature server-side while the store process grinds.

## Operating the rollout

1. **Announce and track stages.** Post the current rollout percentage and vitals summary in the deploy channel at each ramp (deployment-notification-slack.md), so halting is a visible, expected action rather than an admission of failure.
2. **Staff the watch window.** The first hours at each new percentage are when new-device-shape crashes surface. Have someone explicitly on deck to read vitals and execute the halt criteria, especially at the first stage after a big jump.
3. **Debrief version-drain after 100 percent.** After full rollout, report how long the previous version persisted in the fleet. That measured drain time is the input for deciding how many app versions back your server compatibility guarantees actually need to run.
