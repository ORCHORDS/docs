# WebHID Device Request and Permission Flow

The WebHID API lets web pages talk to Human Interface Devices the browser's built-in abstractions don't cover: macro pads, stream decks, flight-simulator panels, specialized controllers, industrial barcode scanners. The security model is deliberately narrow — nothing happens until the user picks a device from a browser-provided picker, and access is granted per-device, per-origin, persistently until revoked. For a site integrating device support, the work is structuring the request flow: when to prompt, how to handle the chooser, how to survive disconnects, and how to respect the permission lifecycle across sessions. This article covers the request/permission model, the `requestDevice` flow, connection lifecycle handling, and the access-control boundaries.

## Scope

This article addresses WebHID device access in browsers: `navigator.hid.requestDevice()` and its filters, the chooser/permission grant model, `getDevices()` for previously granted devices, connection lifecycle (`open`, `inputreport`/`outputreport` events, disconnect/reconnect handling), and the permission/persistence model including revocation. It covers application integration practice. It does not cover HID report descriptor parsing details, WebUSB, or Web Serial.

## Workflow or implementation guidance

The permission model in one paragraph: a page cannot enumerate arbitrary HID devices. It can only (a) call `requestDevice()` — which requires a user gesture and shows a browser-owned chooser listing matching devices — and (b) once the user selects a device, that origin permanently gains access to that specific device (visible in site permissions), retrievable on later visits via `navigator.hid.getDevices()` without any prompt. Revocation happens through browser settings (site permissions → HID devices). This is stricter than a native app and stricter than WebUSB's early iterations; the design goal is that device access is always a per-device, user-witnessed decision.

The integration flow:

1. **Trigger from a real user gesture.** `requestDevice()` must be called from an event handler (click); calling it programmatically on page load throws. UI: a "Connect device" button, disabled or hidden until context suggests a device is expected.
2. **Filter honestly.** `requestDevice({ filters: [{ vendorId: 0x1234, productId: 0x5678 }] })` narrows the chooser to your supported devices. Coarser filters (`usagePage`/`usage` for HID interface classes) serve "any gamepad-shaped thing" cases. An empty filter list shows *all* HID devices — technically allowed with `requestDevice({ filters: [] })`-style calls per spec rules (browser-dependent) but a hostile UX and a red flag in review; filter to what you actually speak. Filters carry protocol weight too: choosing a device the page cannot actually drive wastes the user's grant.
3. **Handle the cancel path.** If the user dismisses the chooser, `requestDevice()` rejects (e.g., `NotAllowedError`); the UI must return to a calm "not connected" state, not an error page. A retry is fine; badgering loops are not.
4. **Open and claim.** The granted `HIDDevice` needs `device.open()` before I/O. `open()` fails if the device is already claimed by another application (native software holding exclusive access) — surface that distinctly ("device busy; close its native app") because users will otherwise blame the site.
5. **Wire the event model.** `device.addEventListener('inputreport', …)` receives parsed input reports; `sendReport`/`sendFeatureReport` do output. Reports carry `reportId` matching the device's descriptor; your protocol layer maps report IDs to parsed structures per-device-firmware — version your protocol handling (devices ship firmware revisions with changed report layouts).
6. **Reconnect logic.** `navigator.hid.addEventListener('connect'/'disconnect', …)` fires for device (un)plugging. Persist device identity (vendor/product/serial where present) in app state; on `connect`, check `getDevices()` — if the reattached device was previously granted, re-open transparently. On `disconnect`, pause and show "reconnect the device" rather than crashing the session. Sessions spanning unplug/replug are the norm for USB-HID hardware, not the edge case.
7. **Cold session restore.** On page load, `getDevices()` returns previously granted devices with no prompt — silently opening them is acceptable (the user already granted) but the UI should announce state ("Macro pad connected") since the user may have forgotten the grant exists.

Security and hygiene notes that belong in design:

- Device input is untrusted input: a malicious or malfunctioning device can emit malformed report payloads. Parse defensively (bounds-check offsets/lengths against the actual `data` buffer; never trust `reportId` implies a length).
- Grants are per-device and persist: build a "Manage devices" surface listing `getDevices()` with instructions to revoke via browser settings; users deserve a visible inventory of what the site can touch.
- Never request devices as a login/anti-fraud gate ("prove you own hardware X") — the permission model isn't designed for it and users on shared machines get trapped.
- Enterprise/managed contexts: browsers expose HID permissions policy controls (Permissions-Policy `hid` directive controls iframe access); if embedding device features in iframes cross-origin, the embedder must delegate `hid=(self "https://embed.example")` or the nested context's calls fail closed.

A worked example: a web-based control surface for a stream-deck-style macro pad. The page offers "Connect your pad" (gesture), filters by the pad's vendor/product IDs, user picks in the chooser, site opens the device and binds `inputreport` handlers mapping key presses to actions. Unplugging mid-session fires `disconnect`: the UI dims to "pad offline", actions queue or pause. Replug fires `connect`, and because the grant persisted, the site re-opens and resumes — no chooser, no gesture needed, because the user's original selection covers the device permanently until revoked.

## Controls

- Request devices only from explicit user gestures with filters matching the supported device matrix; code review rejects unfiltered requests and programmatic (non-gesture) calls.
- Parse input reports defensively: validate lengths/offsets before reads, isolate parsing from application state; fuzz the parser with truncated/malformed buffers in tests (it is the boundary between hardware and your logic).
- Implement disconnect/reconnect as first-class states with UI affordances and tests (simulate via device disconnect in a hardware-in-harness test or mock the event surface).
- Provide a visible device inventory ("this site can access: …") with revocation instructions; audit `getDevices()` on app start and reconcile with UI state.
- If embedded in third-party iframes, document the Permissions-Policy `hid` delegation requirement in the integration guide and fail with guidance (not a blank screen) when delegation is missing.

## Validation evidence

- The `requestDevice` gesture requirement, chooser-driven grant model, filters (vendor/product/usage), `getDevices()` persistence semantics, `connect`/`disconnect` events, report I/O methods, and the Permissions-Policy integration are specified in the WebHID specification published by the W3C WebApps Working Group (formerly WICG incubation), which also documents the security and privacy considerations underlying the per-device grant model.
- Browser site-permission surfaces (per-origin HID device lists with revoke) implement this model and are described in vendor documentation of the browser's permissions UI.
- A reproducible integration test: with a supported device attached, run the flow — gesture → `requestDevice` (filtered) → user selects → `open()` → emit input → assert handler fired; unplug → assert `disconnect` fired and UI entered offline state; replug → assert silent re-open via `getDevices()` — the full lifecycle validated against real hardware or a faithful mock.

## Failure modes and correction

- **Chooser-cancel crashes flow.** Symptom: unhandled rejection leaves broken UI. Correct by treating cancellation as a normal return state.
- **Device busy on open.** Symptom: `open()` fails intermittently. Correct by distinct messaging for already-claimed devices and retry guidance.
- **Protocol drift across firmware.** Symptom: garbage parsing after firmware update. Correct by versioned report handling keyed on product/version identifiers in descriptors.
- **Silent death on disconnect.** Symptom: page frozen waiting on reports. Correct by the connect/disconnect state machine as a designed feature.
- **Unfiltered requests.** Symptom: users grant access to keyboards pointing at the site's inability to use them; trust erodes. Correct by honest filters and review policy.

## Limitations

- Some platforms classify keyboards/pointers as protected interfaces — the browser excludes system-critical HIDs from WebHID regardless of filters.
- Feature availability varies by browser and platform; capability-detect (`'hid' in navigator`) and degrade gracefully.
- Exclusive-access conflicts with native software are inherent: only one holder at a time on several operating systems.
- Physical-layer debugging (descriptor anomalies, flaky cables) remains outside the API's visibility — correlate with OS-level tools when hardware misbehaves.

## Canonical sources

- W3C, WebHID Specification (W3C Editor's Draft / WICG) — requestDevice, permissions, lifecycle, Permissions-Policy: https://wicg.github.io/webhid/
- W3C, WebHID repository and explainer (security model rationale): https://github.com/WICG/webhid
