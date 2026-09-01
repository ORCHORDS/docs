# iOS Pasteboard Privacy, UTIs, and Automatic Paste Prompts

The system pasteboard is iOS's most exposed shared channel: every app can read what any app copied. iOS hardened this progressively — per-pasteboard paste notification (iOS 14: apps reading the pasteboard trigger a banner), the UIPasteControl paste button (iOS 16: user-initiated pastes with no prompt), and typed paste APIs that access only what the user pasted. Building a paste experience that respects these mechanisms means understanding uniform type identifiers (UTIs) for filtering, choosing between automatic detection and explicit paste buttons, and avoiding the privacy anti-patterns (background polling) that the platform now surfaces to users as warnings. This article covers the pasteboard privacy model, UTI-based content negotiation, the API set per iOS generation, and correct UX patterns.

## Scope

This article addresses iOS pasteboard (`UIPasteboard`/`UIPasteControl`) privacy and mechanics: system/general pasteboards, item providers and UTI filtering, `detectedPatterns`/`detectedValues` (iOS 16+ pattern APIs that don't trigger the paste prompt), the `UIPasteControl` button, `pasteConfiguration` acceptance rules, expiration and local-only options, and the user-visible privacy behaviors. It covers client-side paste UX and privacy. It does not cover drag-and-drop, share extensions' broader data flow, or clipboard managers on macOS.

## Workflow or implementation guidance

The privacy timeline that defines today's rules:

- **Before iOS 14**, any app could read `UIPasteboard.general` at any time silently.
- **iOS 14+**: reading general pasteboard content triggers the system banner "X pasted from Y" — every actual read is user-visible. This single change ended background clipboard sniffing as a covert practice.
- **iOS 16+**: two escape hatches that do *not* trigger the prompt: `UIPasteControl` (a system-rendered paste button; the user taps it, the app receives the paste — consent is the tap) and pattern detection (`detectedPatterns`/`detectedValues`), which lets the app ask "does the pasteboard contain a URL/number/etc.?" and receive matches without reading full content or notifying.

The API decision tree for a paste surface:

1. **Default: explicit paste affordance with `UIPasteControl`.** Where UX allows a button ("Paste" in a toolbar or inline), use it: `UIPasteControl(pasteConfiguration: config)` with the view controller conforming to `UIPasteConfigurationSupporting`/implementing `paste(itemProviders:)`. The system button renders with the paste glyph, the user's tap is the consent, no prompt fires. Configure the `UIPasteConfiguration` with acceptable UTIs (`acceptableTypeIdentifiers` or convenience initializers like `init(forAccepting: UIImage.self)`).
2. **Field-targeted paste with typed access.** Text fields get system paste support for free. For custom views, adopt `pasteConfiguration` on the responder so the system paste menu targets it; typed paste (the edit menu's Paste on a first responder) delivers content without the banner — user-initiated via the menu.
3. **Smart detection without reading: `detectedPatterns`.** To show "Paste link" only when a URL is present, query `UIPasteboard.general.detectedPatterns` (or `detectedPatterns(for: [.probableWebURL, .number])`) — the system returns matched patterns without exposing content and without notifying. `detectedValues` returns actual values for supported types with the same no-prompt property when used from paste-user interactions; read the current documentation for exact notification semantics per iOS release, and design so the worst case (a prompt) is acceptable UX.
4. **Avoid programmatic general-pasteboard reads on view load.** `UIPasteboard.general.string` in `viewDidLoad` fires the banner every time the screen opens — users read this as surveillance (and App Review may too). Move reads behind explicit user action or detection APIs.
5. **UTIs define what you accept.** Paste negotiation is type-driven: item providers on the pasteboard advertise conformant UTIs (`public.url`, `public.utf8-plain-text`, `public.jpeg`, your app's exported UTI). `pasteConfiguration.acceptableTypeIdentifiers` filters what the paste control/menu delivers; declaring an app-specific UTI (exported in the Info.plist `UTExportedTypeDeclarations`) enables rich paste of your document type between your app's surfaces with no fragile format sniffing.

Writing to the pasteboard — the sender's obligations:

- **Write the richest correct representation**: set `string` for text, or `setItemProviders`/`addItems` with multiple representations (plain text + your document UTI + URL) so receiving apps negotiate properly.
- **`expirationDate` and `localOnly`.** Sensitive content (one-time codes, passwords) should set `localOnly = true` (not handed off to other devices' nearby-paste mechanisms) and an `expirationDate` (seconds-scale for OTPs) — sender-side hygiene that costs nothing and prevents stale secrets lingering system-wide.
- **Named pasteboards for intra-app handoff** (`UIPasteboard(name:create:)` with your own identifier) avoid polluting the user's general clipboard; they persist per persistence rules but are invisible to other apps by name.

Behavior details that decide correctness:

- The banner's trigger is *content access*, not pasteboard object use: `hasStrings`, `hasURLs`, and `detectedPatterns` are non-prompt queries; `string`, `items`, `data(forPasteboardType:)` read content and prompt (the has-queries' exact prompt behavior has shifted between releases — verify per your minimum iOS version; design so detection-only checks drive UI and actual reads happen strictly on user action).
- `UIPasteControl` requires the supporting responder chain: the control finds its paste target by walking up; misplaced controls (no supporting ancestor) do nothing — a wiring bug that shows as "the button taps but nothing pastes."
- Pattern detection returns probabilities for some categories (`.probableWebSearch`, `.probableWebURL`); treat them as UI hints (enabling a "Paste Link" chip), never as validated data — the actual paste still goes through the consented read.

A worked example: a browser app shows an address-bar "Paste and Go" chip. Implementation: `detectedPatterns(for: [.probableWebURL])` gates chip visibility (no prompt, no content read); tapping the chip uses `UIPasteControl`-style consent or the user taps the system Paste button targeting the field; the receiving path validates the string as a URL and navigates. Users see the banner zero times for the detection step and only the expected consent path for the read — versus the anti-pattern (`general.string` polled on every keyboard appearance) that ships a banner and a App Review privacy question.

## Controls

- Code review rule: no reads of `UIPasteboard.general` content properties outside user-initiated action paths; static grep for `.general.string`/`.items`/`data(forPasteboardType` in view-lifecycle code is a cheap automated guard.
- Paste-receiving surfaces declare `UIPasteConfiguration` with explicit UTI allowlists (never wildcard acceptance); custom document types are exported UTIs with versioned identifiers.
- Sensitive senders set `localOnly` and short `expirationDate`; a lint or helper API (`copySecret(_:)`) makes the safe path the default for one-time-code copy features.
- UI tests cover: paste control wiring (tap → content delivered), UTI filtering (rejected type does nothing graceful), and detection gating (chip appears only when pattern present) — the three failure surfaces of paste UX.
- Release privacy review walks every pasteboard touchpoint against the "user-visible consent" model; App Review notes the banner behavior in review of clipboard-touching apps.

## Validation evidence

- Paste-privacy behaviors (the user notification on general-pasteboard content access, non-prompting `has*`/detection queries, `UIPasteControl` consent semantics), `UIPasteConfiguration`/UTI acceptance, expiration and local-only options, and named pasteboards are specified in Apple's `UIPasteboard` and `UIPasteControl` documentation on developer.apple.com, with the privacy model described in the platform privacy documentation and release notes for iOS 14 and 16.
- Uniform Type Identifiers (UTI conformance and declaration) are documented in Apple's Uniform Type Identifiers framework reference and conceptual documentation.
- A reproducible UX validation: on a physical device, run three flows — (1) app reads `general.string` on appear: observe the system banner (demonstrating visibility of reads); (2) same screen using only `detectedPatterns`: observe no banner; (3) tap a `UIPasteControl`: observe content delivery without banner — the three-way behavior comparison confirming your implementation sits on the intended side of the privacy model.

## Failure modes and correction

- **Banner on every screen open.** Cause: programmatic reads in lifecycle code. Correct by detection-gated UI + user-initiated reads.
- **Paste button taps do nothing.** Cause: missing supporting responder / misplaced control. Correct by wiring the paste target up the responder chain; covered by the paste-wiring UI test.
- **Weird content accepted into rich fields.** Cause: UTI allowlist missing or wildcard. Correct by explicit `acceptableTypeIdentifiers`.
- **Stale secrets on shared pasteboard.** Cause: senders not setting expiration/localOnly. Correct by the safe-copy helper.
- **Detection treated as validation.** Cause: probable-pattern results used as data. Correct by detection-for-UI-only policy; the consented paste validates.

## Limitations

- The privacy model's exact prompt triggers for `has*`/detection queries have shifted between iOS releases; verify per minimum-supported version rather than assuming a fixed contract.
- `UIPasteControl` rendering is system-styled; heavily custom paste UX may not fit the control and falls back to menu/prompt paths.
- Cross-device paste (Universal Clipboard) moves content outside the local pasteboard's lifecycle; `localOnly` is the sender's opt-out, not a default.
- Third-party pasteboard-manager ecosystems on iOS are constrained by these same privacy rules; there is no supported background clipboard-history on-device.

## Canonical sources

- Apple, UIPasteboard — pasteboard privacy, detection APIs, expiration, local-only: https://developer.apple.com/documentation/uikit/uipasteboard
- Apple, UIPasteControl and UIPasteConfiguration — consented paste button and UTI acceptance: https://developer.apple.com/documentation/uikit/uipastecontrol
