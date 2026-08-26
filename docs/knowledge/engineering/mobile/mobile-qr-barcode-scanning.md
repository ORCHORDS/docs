# mobile-qr-barcode-scanning

**Issue:** QR and barcode scanning shows up in onboarding, payments, device pairing, and KYC document flows, and it fails in consistent ways: scanners that take ten seconds to lock on, scanners configured to read every symbology when the product only accepts QR, permission flows that dead-end after a denial, and — increasingly a real security liability — scanners that open arbitrary URLs embedded in untrusted codes without preview. The free platform APIs (Google ML Kit, Apple VisionKit DataScannerViewController) are mature and on-device, but benchmarks show they tolerate smaller codes relative to frame size less well than commercial SDKs, so configuration and UX tuning decide whether a scan takes 300 ms or 10 s. This article covers API selection, detection tuning, UX flow, security handling of scanned payloads, and integration inside a Capacitor shell.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## API Selection

1. **ML Kit barcode scanning on Android.** ML Kit (bundled or unbundled model) scans on-device with no network dependency. Configure BarcodeScannerOptions with explicit formats; the bundled model adds ~3 MB to the app, which is the usual cost decision point.

2. **VisionKit DataScannerViewController on iOS.** DataScannerViewController gives a system-grade live scanner for codes and text. Always check DataScannerViewController.isSupported (older/iPad-class hardware can be unsupported) and isAvailable (camera entitlements) before presenting, and pick a recognition quality level rather than accepting defaults.

3. **AVCaptureMetadataOutput as the fallback.** When DataScannerViewController is unsupported, AVCaptureMetadataOutput with metadataObjectTypes gives the classic path with full control over the preview layer, at the cost of hand-rolling focus, zoom, and delegate plumbing.

4. **Commercial SDKs for hard mode.** Benchmarks (Dynamsoft's comparison of ML Kit, Apple Vision, and ZXing) show native free APIs need a larger minimum code size relative to image dimensions. For damaged, tiny, off-angle, or high-volume industrial scanning, Scandit/Dynamsoft class SDKs earn their license; for consumer QR, they rarely do.

5. **Do not scan from stills by default.** Picking an image and decoding from the gallery is a separate code path (ML Kit from InputImage / Vision from CGImage) — support it deliberately for accessibility (screen-reader users, printed codes) rather than assuming live camera only.

## Detection Tuning

1. **Constrain symbologies.** Restricting ML Kit to QR-only (or the exact set you accept) measurably improves speed and eliminates misreads from Code128 noise. Every added format is extra classifier work per frame; the same applies to VisionKit's recognizedDataTypes.

2. **Quality versus speed settings.** ML Kit exposes quality/speed hints in BarcodeScannerOptions; quality costs per-frame latency. Default to speed for continuous framing and quality only for single-shot capture from stills.

3. **Throttle the frame analyzer.** Feeding every camera frame to the detector melts battery and janks the preview. Drop to 5-10 analyzed frames per second with ImageAnalysis setTargetResolution around 1080p width; detection latency is dominated by code size and focus, not analyzer frame rate.

4. **Minimum code size and working distance.** As a rule of thumb the code should occupy at least a tenth of the frame's smaller dimension for reliable native-API detection. Guide users closer with UI (see below) instead of raising resolution, since sensor focus limits bite before resolution does.

5. **Focus and exposure lock.** Continuous autofocus hunting is the top cause of slow locks. Trigger a one-shot focus at scan start (after the first motion settles) and consider exposure lock for dark environments; on Android use CameraX tap-to-focus actions bound to the center of the viewfinder.

## UX Flow

1. **Permission pre-flight.** Check camera permission before presenting the scanner; on denial, offer a bounded explanation and a settings deep link, plus a manual-code-entry fallback. Never present a black camera view as the first failure signal.

2. **Viewfinder framing guide.** Draw a reticle matching the expected aspect ratio, dim the surroundings, and animate a subtle scan line. This simultaneously teaches working distance (fixing the minimum-size problem) and sets expectations.

3. **Torch and zoom controls.** Low-light and long-distance failures are user-fixable: surface a torch toggle that persists for the session and a pinch-to-zoom (CameraX setZoomRatio on Android, videoZoomFactor on iOS).

4. **Confirm with a second channel.** On lock, freeze the frame, show the decoded value, and confirm with haptic (see the haptics article) plus a brief sound. Silent vibration-only success leaves users re-scanning codes that already worked.

5. **Deduplicate consecutive reads.** Debounce identical payloads within a short window (1-2 s) so one code does not fire the completion flow three times before the screen dismisses.

## Security Considerations

1. **Never auto-open URLs.** Quishing (QR phishing) exploded alongside sticker-over-attack reports. Show the exact URL with domain highlighted, and require a user tap before navigating; block javascript:, intent:, and app-deep-link schemes the product does not explicitly use.

2. **Validate the payload schema.** Treat decoded strings as untrusted input: length caps, allow-listed prefixes, and parse into a typed structure before acting. A QR payload reaching a payments or KYC API unvalidated is an injection vector, same as any user text field.

3. **Provenance for compliance scans.** In KYC flows, record scan metadata (format, timestamp, device attestation status) alongside the decoded value so downstream auditors can distinguish camera-scanned from manually typed codes.

4. **Prefer scanning to typing.** Manual entry fallback should still checksum-validate (for instance Iban/ISBN-style checks) because transposition errors silently corrupt downstream flows.

## Cross-Platform Integration

1. **Native plugin over JS libraries.** In Capacitor apps, use a native plugin wrapping ML Kit and VisionKit rather than a JS decoder over getUserMedia frames; shipping frame bitmaps across the bridge destroys frame rate and battery.

2. **One bridge, two engines.** Expose scan(formats) and return { value, format } from a single plugin interface; keep symbology configuration in the web layer so product can tighten accepted formats without native releases.

3. **Test the whole funnel on device.** Print real codes at realistic sizes and lighting (matte paper, curved surfaces, sunlight) — simulator camera injection tests the pipeline but not optics. Follow the repo's screenshot-per-state protocol while testing each state: prompt, scanning, locked, error.
