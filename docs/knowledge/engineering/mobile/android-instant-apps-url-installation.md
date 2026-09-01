# Instant Apps URL-First Entry and Install Handoff

Instant apps let users run an app from a URL or Play listing without a store install. The engineering contract is unusual: the instant experience must be reachable from a deep link, start inside strict size and permission limits, and hand off cleanly to the installed app without losing state. This article covers URL-first entry, the install-handoff API, and the instant/installed boundary.

## Scope

Covered: instant-enabled App Bundle modules (`dist:instant="true"`), URL routing into the instant experience, `PackageManager` instant-app detection, the install prompt via Play Core's `SplitInstallManager`/Instant API surface (`InstantSessionClient` and the `setShowInstallPrompt` pattern), and cookie/state transfer at handoff. Not covered: dynamic feature architecture generally (`android-dynamic-feature-module-architecture.md`) or Play Feature Delivery install states (`android-play-feature-delivery-install-states.md`).

## Workflow or implementation guidance

1. **Package the instant module.** An instant-enabled app is an App Bundle where one module carries `dist:instant="true"` and serves as the default activity entry. Base-module size is the hard constraint: the instant experience must stay within Play's instant size ceiling (historically 10 MB for the base instant module download on the 2017-era program, later relaxed; treat single-digit MB as the design budget and verify the current limit in Console warnings). A separate small instant module that depends on a trimmed feature set, rather than exposing the full app, is the standard shape.
2. **Declare URL entry.** The instant module's launcher activity must handle an `https` intent (App Links), because instant launch from search or messaging is URL-driven. `<intent-filter android:autoVerify="true">` with `VIEW`/`BROWSABLE`/`DEFAULT` categories on `https://yourdomain/path`. Run and re-run App Links verification: unverified links launch instant experiences via the Play front-end interceptor on some surfaces but break others. Keep the instant entry path separate from installed-app deep links via distinct path prefixes (for example `/try/`) when the experiences differ.
3. **Gate features on instant state.** At runtime, `packageManager.isInstantApp` (API 26+) or `InstantSessionClient.isInstantApp` determines the mode. Assume: no access to APIs unavailable to instant apps (some background services, and anything requiring excluded permissions), no persistent local storage beyond the session (files vanish after the instant session ends), and no access to device identifiers. Design the instant flow as a session: bounded progress, server-backed state keyed by an ephemeral token, and no writes that must survive.
4. **State transfer at install.** Before triggering install, persist handoff state where the installed app can read it after first launch. The documented mechanism is the instant-app cookie API (`InstantCookies`/`setInstantAppCookie` in Play Core): a small byte payload readable by the installed app immediately after install. Write the session token/user progress into the cookie, then call the install prompt: `InstantSessionClient.setShowInstallPrompt(activity, intent, REQUEST_CODE, referrer)` shows Google Play's install prompt; alternatively a `PostInstallPrompt` can be launched from the installed app to surface an in-context continue prompt.
5. **Installed-side resume.** On installed first launch, read the cookie (`instantClient.instantAppCookie` or the Play Core equivalent), restore state, then clear the cookie. If the cookie is empty (user installed later from the store without the prompt), fall back to link-based resume: the original URL plus a server-side session keyed by token.

Testing without Play: use `adb shell` with the instant-app SDK's development settings or `bundletool` with `--mode=instant` in `build-apks` to produce and install instant-mode APK sets locally; this validates URL routing and size limits before a Play upload.

## Controls

- Keep the instant module's compressed download under the Play instant size limit; wire the bundle build to fail on budget breach (track via `bundletool get-size total` against a threshold).
- Verify App Links (`assetlinks.json` at `https://domain/.well-known/`) in CI with a link-checker and after every domain migration; instant entry silently degrades to "open in browser" when verification lapses.
- Never call install-restricted APIs without an `isInstantApp` guard; wrap them behind a capability interface so the instant build has a safe no-op implementation.
- Treat the instant cookie as untrusted input on the installed side: validate and expire server-issued tokens it carries; a malicious user can write arbitrary bytes via their own instant session.
- Audit the instant manifest for excluded permissions - permissions that instant apps cannot hold cause Console rejection, not runtime failure.
- Instrument funnel: URL open, instant session start, key completion event, install-prompt shown, install completed, installed-app resume-with-state. The last number measures whether handoff actually preserves user value.

## Validation evidence

Local: `bundletool build-apks --mode=instant --bundle=app.aab --output=instant.apks` followed by `bundletool install-apks --apks=instant.apks` on an API 33+ device, then `adb shell am start -a android.intent.action.VIEW -d "https://yourdomain/try/entry"` must open the instant experience. Confirm installed/instant differentiation with a debug overlay showing `isInstantApp`. Verify the handoff by completing the instant flow, accepting the install prompt, and asserting the installed first run resumes from the cookie payload. On Play: internal-testing track instant rollout, open the URL from Messages/Chrome on a physical device, and repeat the handoff. Evidence basis: the procedures follow Google's instant-enabled App Bundle documentation and Play Core instant API documentation cited below.

## Failure modes and correction

- Instant URL opens the website instead of the app: App Links verification failed. Re-check `assetlinks.json` package/sha256 fingerprints against the current signing cert (note Play App Signing uses Google-held keys - the JSON must carry the app signing cert fingerprint, not your upload cert).
- Install prompt shown but state lost after install: cookie not written before prompt, cookie exceeded size limit, or installed app read it too late. Write early, keep payloads under a few KB (token only, not content), and read at first launch only.
- Console rejects with "feature uses unsupported permission": move the capability behind the installed boundary; instant apps cannot request it.
- Instant session resets mid-flow: backgrounding can end the session and wipe storage. Keep all durable state server-side keyed by a token in the URL/cookie, and re-enter from the URL rather than a task-stack restore.
- Oversized instant module: Console shows a limit error at upload. Move heavy code/resources into on-demand DFM modules for the installed experience and keep the instant module minimal.

## Limitations

Instant app availability, entry surfaces, and prompts are Play-controlled and vary by device, region, and app status; behavior on a given device cannot be fully replicated locally. The cookie API has a small payload ceiling and version-specific availability. Some Play surfaces route instant opens through the Play Store app itself, so first-run latency includes Play's own pipeline. This article reflects the instant-programs architecture built on App Bundles; teams should re-verify current size limits and surface behavior in the Play Console before each release.

## Canonical sources

- Android Developers - "Get started with instant-enabled app bundles": https://developer.android.com/topic/google-play-instant/getting-started/instant-enabled-app-bundle (verified HTTP 200)
- Android Developers - "Google Play Instant overview": https://developer.android.com/topic/google-play-instant/overview (verified HTTP 200)
- Android Developers - bundletool (instant-mode APK set generation for local testing): https://developer.android.com/tools/bundletool (verified HTTP 200)
