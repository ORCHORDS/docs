# mobile-screen-capture-prevention

**Issue:** Finance, KYC, health, and enterprise apps must keep sensitive screens out of screenshots, screen recordings, and the app-switcher thumbnail — both for regulatory reasons and as a defense against social-engineering support scams. The two platforms could not differ more. Android's FLAG_SECURE actually blocks capture system-wide, and Android 14 added explicit screen-recording callbacks; iOS provides no blocking whatsoever — only after-the-fact detection via UIScreen.isCaptured, capturedDidChangeNotification, and user screenshot notifications — so an iOS "prevention" feature is really a detect-and-respond design. Engineering must implement both strategies without wrecking legitimate UX (users screenshot receipts and support flows constantly), and must never assume blocking alone is a security boundary, since a second phone defeats every software control.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Platform Capabilities

1. **Android FLAG_SECURE blocks outright.** Setting FLAG_SECURE on a window blanks it in screenshots, screen recordings, and the recents/app-switcher snapshot on non-secure displays. It is the only true capture-block either platform offers; there is no iOS equivalent.

2. **Android 14 screen-recording callbacks.** Activity.addScreenRecordingCallback (API 34+) notifies your app when a recording of it starts and stops, letting you react (blur, watermark, exit) even when FLAG_SECURE is off. Older versions require inferring from MediaProjection heuristics, which are unreliable and best avoided.

3. **iOS cannot block.** UIScreen.isCaptured tells you a capture (AirPlay, Mirroring, QuickTime, ReplayKit) is in progress, and capturedDidChangeNotification fires on change — but by definition after capture begins, and it does not fire for plain user screenshots at all.

4. **User screenshots on iOS are detect-only.** userDidTakeScreenshotNotification fires after the shot lands in Photos. There is no pre-capture hook; the only mitigations are reactive overlays or accepting it and redacting what is on screen in the first place.

5. **WebView shells need bridging.** In a Capacitor app, the web layer cannot set window flags or observe UIKit notifications; both must be exposed through a small native plugin (a SecureScreen plugin with enable/disable and onRecordingChange events).

## Implementation Patterns

1. **Flag per screen, not per-app.** Apply FLAG_SECURE only on genuinely sensitive screens (KYC document view, card numbers, seed phrases). Setting it app-wide breaks recents thumbnails everywhere and annoys users screenshotting benign screens — the classic over-flagged banking-app complaint.

2. **Detect-then-respond on iOS.** On capturedDidChange to true, apply your response: blur PII, or better, invert to a watermark overlay containing the user ID and a timestamp. Watermarks convert recordings from an exfiltration channel into an audit trail — a screenshot of the app now identifies its origin.

3. **Redact the app-switcher snapshot.** On backgrounding, cover sensitive content before the system grabs the snapshot (Android 14+ also respects a secure snapshot when flagged; iOS requires an overlay in sceneWillResignActive). Otherwise the switcher thumbnail leaks full account data even when in-app screens are careful.

4. **Cross-platform abstraction.** Define one SecureScreen interface with enter/exit and a capability descriptor (canBlock, canDetectRecording, canDetectScreenshot) so product code can degrade: block on Android, watermark on iOS, and log the difference in analytics.

5. **Pair with screenshot detection analytics.** Log userDidTakeScreenshotNotification events (anonymized) on sensitive screens; a spike is an early signal of both fraud coaching and legitimate "users need to keep this" product needs (exportable statements).

## UX and Policy Tradeoffs

1. **FLAG_SECURE disables recents thumbnails.** Users lose quick multitasking context for the flagged screen; some launchers also block legitimate assist/screenshot features. Document this in release notes when you first flag a screen, or expect support tickets.

2. **Do not block support flows.** Receipts, transaction confirmations, and error states should remain screenshot-friendly; a user asked to "send a screenshot of the error" who cannot is a support-cost multiplier. Keep blocking scoped to credentials and regulated data.

3. **Blocking is not a security boundary.** A second device's camera defeats FLAG_SECURE and every iOS overlay. Treat capture controls as compliance and friction-reduction layers; the actual controls are short-lived data, server-side redaction, and session limits on sensitive views.

4. **Align with MASVS expectations.** OWASP MASVS-PRIVACY/STORAGE review checklists ask whether sensitive data could leak via the switcher, screenshots, and logs — a good pre-submission audit list for this feature.

## Testing and Evidence

1. **Test the full capture matrix.** For each sensitive screen verify: user screenshot, OS screen recorder, third-party recorder, cast/Smart-View, QuickTime/iPhone Mirroring, and the app switcher. Capture screenshots of each attempt as evidence per the repo's testing protocol.

2. **Keep debug builds exempt.** FLAG_SECURE blocks adb screencap, which the testing methodology relies on for evidence capture. Apply the flag only in release/signed builds or behind a debug toggle, or your own test protocol goes blind.

3. **Automate detection checks in UI tests.** On Android, assert window flags via Window.getAttributes in instrumentation tests per screen; on iOS, unit-test that the overlay state machine responds to the captured-change notification. Manual matrix testing still runs quarterly, since OS behavior shifts (Android's callback APIs, iOS Mirroring changes) arrive without notice.
