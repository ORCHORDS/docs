# mobile-clipboard-privacy

**Issue:** The system clipboard is a shared, unauthenticated data bus: any foreground app can read whatever the user last copied — often a password from a manager, an OTP, a crypto seed phrase, or a private message. Both platforms have reacted: iOS shows an "Allow Paste?" prompt and blocks silent background reads, while Android 13 toasts on every clipboard read by an app and lets content be flagged sensitive; Android 14 tightens preview redaction. Apps that programmatically sniff the clipboard on foreground (a once-common "paste detected" pattern) now trigger scary-looking system prompts that tank trust and draw App/Play Store privacy scrutiny. Clipboard handling must be redesigned around explicit user action, sensitive-content flagging, and shortened retention — including inside WebViews where none of the native APIs apply directly.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Platform privacy model

1. **iOS paste prompts.** Since iOS 16, reading UIPasteboard without clear user intent (a Paste button tap or the keyboard Paste action) triggers the system "Allow Paste?" alert for cross-app content. Frequent prompts are a top App Store review complaint and a reliable one-star driver.
2. **UIPasteControl removes the prompt.** iOS 16+ provides UIPasteControl (and SwiftUI's PasteButton): a system-rendered button that grants one-shot paste access with no prompt. Use it for "paste from clipboard" affordances instead of reading the pasteboard in code.
3. **Android 13 read notifications.** Android 13 shows a toast identifying the app whenever it reads clipboard content not authored by that app. Users notice; make sure every read in your app is something the user just asked for.
4. **Sensitive flag and auto-clear.** Android 13+ lets you mark clipboard content as sensitive (via ClipDescription extras) so the clipboard preview redacts it, and the system hides preview content after a short window (Android 14). iOS similarly redacts OTP/password-class content from paste suggestions.
5. **Background reads are gone.** Both platforms now gate clipboard reads to the foreground with user context; any code path that reads in background services, widgets, or on app launch is dead or prompt-spamming.

## Writing to the clipboard safely

1. **Flag sensitive copies.** When copying passwords, tokens, recovery codes, or keys, set the sensitive flag (ClipData with EXTRA_IS_SENSITIVE on Android) so the preview UI shows redacted content instead of the secret in plain sight on the lock screen overlay.
2. **Consider expiring the copy.** For high-value secrets, prefer in-app display over clipboard where possible, or clear the clipboard after a timeout (your own re-copy of a placeholder) — Android 14's preview auto-clear helps, but other apps can still read until the user copies something else.
3. **Label your clips.** Set a descriptive ClipDescription label so password managers and other readers can identify the content type; unlabeled blobs defeat downstream redaction heuristics.
4. **Never auto-copy secrets on the user's behalf.** Copying an OTP to the clipboard automatically exposes it to every other app; show it in-app and let the user choose to copy.

## Reading the clipboard responsibly

1. **Only on explicit user action.** Read in direct response to a Paste button, text-field paste, or a "recover from clipboard" tap. Reading on viewDidAppear, app foreground, or focus change is the anti-pattern behind both iOS prompt-spam and Android toast-spam.
2. **Do not poll or sniff.** Continuous pasteboard change checks (the old "clipboard manager" pattern) burn battery on iOS (pasteboard timestamps) and surface system warnings; use UIPasteControl or documentPickerController instead.
3. **Validate what you accept.** Treat pasted content as untrusted input: length checks, format checks, and stripping before it reaches parsing or rendering. Pasting is a free fuzzing channel into your parsers.
4. **Handle denial gracefully.** On iOS the user may deny the paste prompt; fall back to manual entry rather than retrying the read in a loop, which re-prompts and escalates.

## Attack vectors to design against

1. **Overlay-induced paste phishing.** Research on Android 14 shows SYSTEM_ALERT_WINDOW overlays can fake a focus target and trick users into pasting secrets into an attacker's field; never rely on clipboard content being private from the user's next tap, and warn users when pasting credential-class data.
2. **Clipboard leakage through screenshots and previews.** The Android clipboard overlay preview shows the last copy on screen; sensitive flagging is the mitigation, so wire it into every secret-copy feature.
3. **Cross-device clipboard sync.** Universal Clipboard (Apple) and cross-device sync features move secrets between a user's devices; your threat model should not assume the copy stayed on the phone.
4. **WebView defaults differ.** In Capacitor/React Native WebView shells, clipboard access follows web APIs (navigator.clipboard) gated by permission prompts; audit web code that calls readText on load — it inherits all the same problems with none of the native APIs.

## Compliance and review posture

1. **Declare and justify.** App privacy declarations (App Store privacy nutrition labels, Play Data safety) should reflect clipboard access; unjustified clipboard reads are flagged in platform audits and third-party privacy scans.
2. **Test the prompts.** On iOS, verify your flows never trigger Allow Paste without a preceding user tap; on Android 13+, watch for unexpected read toasts during QA passes — any toast the user did not cause is a bug.
3. **Educate with microcopy.** Where users must paste secrets, a one-line explanation ("Paste your recovery phrase — it never leaves this device") measurably reduces abandonment and phishing susceptibility.
