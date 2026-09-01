# Camera2 Capture Session State Machine Handling

The camera2 HAL interface exposes camera control as an asynchronous state machine over `CameraDevice` and `CameraCaptureSession`. Most camera bugs in production are not algorithmic; they are state-machine violations - opening a session while another is configuring, submitting requests on a closed device, or leaking a `CameraDevice` across lifecycle boundaries. This article covers the correct transition sequence and the callbacks that drive it.

## Scope

This covers the camera2 API (`android.hardware.camera2`) directly: `CameraManager.openCamera`, `CameraDevice.StateCallback`, `createCaptureSession` (or `sessionConfiguration` on API 28+), `CameraCaptureSession.StateCallback`, and request submission via `capture`/`setRepeatingRequest`. It does not cover CameraX (which wraps and simplifies this), NDK camera access, or vendor extensions. The target surface is apps that need explicit control: manual capture pipelines, preview-plus-analysis streams, or hardware-level features unavailable through CameraX.

## Workflow or implementation guidance

Model the pipeline as five states with single-owner transitions: CLOSED -> OPENING -> OPEN -> CONFIGURING -> READY, plus FAILED and DISCONNECTED as terminal-ish states.

1. **Opening.** Check permissions first - `CAMERA` is dangerous-scope and `openCamera` throws or invokes `onError(ERROR_PERMISSION_DENIED)` without it. Get a `CameraCharacteristics` handle via `cameraManager.getCameraCharacteristics(id)` and pick the camera by lens facing and hardware level. Call `openCamera(id, stateCallback, backgroundHandler)`. Never pass the main-thread handler if any callback work touches the sensor; use a dedicated `HandlerThread` you own.
2. **OPEN.** `onOpened(camera: CameraDevice)` fires. This is the only safe place to build output targets: `Surface` objects from a `SurfaceTexture` (preview), an `ImageReader` (capture/analysis), or a `MediaCodec`/`MediaRecorder` input surface (recording). The combination must come from `characteristics.get(SCALER_STREAM_CONFIGURATION_MAP)` - every surface's size and format must appear in that map's supported output sizes for its template, or session creation fails with `ERROR_CAMERA_DEVICE`.
3. **CONFIGURING.** On API 28+ use `device.createCaptureSession(SessionConfiguration(SessionConfiguration.SESSION_REGULAR, outputs, executor, sessionStateCallback))`; on older APIs use the deprecated `createCaptureSession(outputs, stateCallback, handler)`. Build request templates via `device.createCaptureRequest(TEMPLATE_PREVIEW)` or `TEMPLATE_RECORD`/`TEMPLATE_MANUAL` and add each target surface with `builder.addTarget(surface)`.
4. **READY.** `onConfigured(session)` gives you the live session. Start preview with `session.setRepeatingRequest(request.build(), captureListener, handler)`. The per-request `CameraCaptureSession.CaptureCallback` (`onCaptureCompleted` delivering `TotalCaptureResult`) is your data path for auto-focus/exposure state; keep work on it minimal - copy the result's key fields (focus state via `LENS_FOCUS_STATE`, AE state via `CONTROL_AE_STATE`) and get off the handler thread.
5. **Reconfiguration and teardown.** Changing output surfaces requires a new session: close the old one first (`session.close()`, wait for `onClosed`), then create a new one on the same OPEN device. Teardown order matters: `session.stopRepeating()` if mid-shot, `session.close()`, then `device.close()`, and release the `ImageReader`/`SurfaceTexture` after `onClosed` arrives, not before.

Handle the error taxonomy deliberately: `ERROR_CAMERA_DEVICE` (fatal, close everything and reopen with backoff), `ERROR_CAMERA_DISABLED` (device policy - a DevicePolicyManager admin disabled the camera; surface UI, do not retry), `ERROR_CAMERA_IN_USE` / `ERROR_MAX_CAMERAS_IN_USE` (another client holds it; retry with a delay or prompt), `ERROR_CAMERA_DISCONNECTED` (transport gone), `ERROR_CAMERA_SERVICE` (fatal, in-process or reboot-level failure). On API 30+ concurrency hints exist via `CameraManager.getConcurrentCameraIds()` if you genuinely need dual-camera sessions.

## Controls

- Exactly one component owns the camera lifecycle; bind it to a lifecycle scope that survives rotation or explicitly handle configuration changes with `android:configChanges` and manual session teardown/rebuild.
- Always pair `openCamera` success with an eventual `close()`; wrap usage in a `try/finally` that closes the device when callbacks stop arriving within a timeout.
- Validate every surface size against `StreamConfigurationMap.getOutputSizes(surfaceClass/format)` before session creation; log the exact triple (width, height, format) on failure so field reports are actionable.
- Use `SessionConfiguration` with an `Executor` on API 28+ so callback dispatch does not depend on a `Handler` you might quit.
- Treat `onCaptureFailed(CaptureFailure)` as a normal event for burst/still-capture work; check `failure.getReason()` (for example `REASON_ERROR`) and re-issue the request.
- Register a `CameraManager.AvailabilityCallback` (or use `registerAvailabilityCallback`) to avoid opening a camera another high-priority client (Chrome tab, system QR scanner) already claimed.

## Validation evidence

Exercise the machine with an instrumentation test matrix on at least two physical devices (different HAL levels - a LEGACY-level and a FULL-level camera): open-from-cold, close-then-reopen 50 times in a loop (leak check via `dumpsys media.camera | grep -c "Device .* is open"`), background/foreground cycle while recording, and permission revoke mid-session (expect `onError` with `ERROR_CAMERA_DEVICE` or immediate security exception on next request). Assert `onClosed` fires within a bounded window (for example 500 ms) after `close()` in unit tests with a mock `CameraDevice`. Log every state transition in debug builds with timestamps; a healthy trace alternates onOpened -> onConfigured -> (capture stream) -> onClosed with no interleaved onOpened pairs.

## Failure modes and correction

- `CameraAccessException: MAX_CAMERAS_IN_USE` on second open: a previous session leaked. The correction is the teardown order above plus an `AvailabilityCallback`-driven gate; `adb shell dumpsys media.camera` shows which client holds the device.
- `onConfigured` never fires: your output surface combination is unsupported, or a surface was already connected to another session/API. Rebuild surfaces fresh for each session; do not reuse an `ImageReader` surface across two sessions concurrently.
- Preview freezes after switching modes (for example photo to video): you reused the session with different targets. Sessions are immutable in their output set; close and recreate.
- Crash "BufferQueue has been abandoned": you released the `SurfaceTexture`/`Surface` before `session.close()` completed. Defer surface release to `onClosed`.
- Black frames on LEGACY-level devices: these support limited combos and often only `TEMPLATE_PREVIEW` reliably; consult `INFO_SUPPORTED_HARDWARE_LEVEL` and degrade features accordingly.
- Rotation artifacts: the sensor orientation from `SENSOR_ORIENTATION` is not the display rotation; compose the two explicitly rather than assuming 90 degrees.

## Limitations

camera2's callback graph varies by HAL implementation; timing behaviors (how quickly `onClosed` fires, when AE converges) are device-tuned and not contractually fixed. High-speed, reprocessable (ZSL), and constrained high-speed sessions have additional setup paths not covered here. For most product work, CameraX removes this entire class of bugs; choose camera2 only when you need capabilities CameraX does not expose.

## Canonical sources

- Android Developers - `CameraCaptureSession` reference (session state and request APIs): https://developer.android.com/reference/android/hardware/camera2/CameraCaptureSession (verified HTTP 200)
- Android Developers - `CameraDevice` reference (`StateCallback` error codes): https://developer.android.com/reference/android/hardware/camera2/CameraDevice (verified HTTP 200)
- Android Developers - `CameraCaptureSession.StateCallback` reference (configure/closed transitions): https://developer.android.com/reference/android/hardware/camera2/CameraCaptureSession.StateCallback (verified HTTP 200)
