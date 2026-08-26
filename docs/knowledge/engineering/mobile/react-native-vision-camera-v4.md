# React Native Vision Camera v4

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

`react-native-camera` is unmaintained and crashes on iOS 17+. The built-in `expo-camera` API
does not expose frame data for real-time processing (QR detection, barcode scanning, filter
overlays, ML inference). You need a camera component that offers frame processors — JavaScript
worklets that run on every camera frame on a native thread without bridging overhead.

## Context

Vision Camera v4 (by Marc Rousavy) is a complete rewrite that targets the React Native New
Architecture (JSI). It exposes:

- `<Camera>` component with photo/video capture
- Frame Processors: JavaScript worklets via `react-native-worklets-core` that execute on the
  camera thread at 60 fps without React re-renders
- Plugin system: native Swift/Kotlin plugins that extend the frame processor (e.g. MLKit,
  VisionKit, custom Metal shaders)
- Photo/video output with codec control, zoom gestures, and torch management

v4 requires React Native 0.73+ and the New Architecture enabled. Expo SDK 52+ ships with a
compatible managed config plugin.

---

## 1. Installation

```bash
npm install react-native-vision-camera react-native-worklets-core
npx pod-install   # iOS
```

`app.json` (Expo managed):

```json
{
  "expo": {
    "plugins": [
      [
        "react-native-vision-camera",
        {
          "cameraPermissionText": "Orchords needs camera access to scan QR codes.",
          "enableMicrophonePermission": true,
          "microphonePermissionText": "Orchords needs microphone access to record video."
        }
      ]
    ]
  }
}
```

`babel.config.js` — add the worklets plugin so frame processor closures are compiled:

```js
module.exports = {
  presets: ["babel-preset-expo"],
  plugins: ["react-native-worklets-core/plugin"],
};
```

`metro.config.js` — ensure JS extension resolution includes the worklets transform:

```js
const { getDefaultConfig } = require("expo/metro-config");
const config = getDefaultConfig(__dirname);
config.resolver.sourceExts.push("cjs");
module.exports = config;
```

---

## 2. Basic Camera Component with Photo Capture

```tsx
import React, { useEffect, useRef, useState } from "react";
import { StyleSheet, Pressable, View, Text } from "react-native";
import {
    Camera,
    useCameraDevice,
    useCameraPermission,
    PhotoFile,
} from "react-native-vision-camera";

export function CameraScreen() {
    const { hasPermission, requestPermission } = useCameraPermission();
    const device = useCameraDevice("back");
    const camera = useRef<Camera>(null);
    const [lastPhoto, setLastPhoto] = useState<PhotoFile | null>(null);

    useEffect(() => {
        if (!hasPermission) requestPermission();
    }, [hasPermission, requestPermission]);

    if (!hasPermission) return <Text>Camera permission required</Text>;
    if (!device) return <Text>No camera device found</Text>;

    const capturePhoto = async () => {
        const photo = await camera.current?.takePhoto({
            flash: "auto",
            enableShutterSound: false,
        });
        if (photo) setLastPhoto(photo);
    };

    return (
        <View style={styles.container}>
            <Camera
                ref={camera}
                style={StyleSheet.absoluteFill}
                device={device}
                isActive
                photo
            />
            <Pressable
                style={styles.captureButton}
                onPress={capturePhoto}
                testID="capture-button"
            >
                <View style={styles.captureInner} />
            </Pressable>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: "black" },
    captureButton: {
        position: "absolute",
        bottom: 48,
        alignSelf: "center",
        width: 72,
        height: 72,
        borderRadius: 36,
        borderWidth: 4,
        borderColor: "white",
        justifyContent: "center",
        alignItems: "center",
    },
    captureInner: {
        width: 56,
        height: 56,
        borderRadius: 28,
        backgroundColor: "white",
    },
});
```

---

## 3. Frame Processors for Real-time QR Scanning

Frame processors run as worklets on the camera thread. They must use `'worklet'` directive and
call only synchronous, worklet-compatible functions. Use the `useFrameProcessor` hook.

```tsx
import {
    Camera,
    useCameraDevice,
    useFrameProcessor,
} from "react-native-vision-camera";
import { scanBarcodes, BarcodeFormat } from "vision-camera-code-scanner";
import { runOnJS } from "react-native-reanimated";

function QRScannerScreen({ onCodeScanned }: { onCodeScanned: (value: string) => void }) {
    const device = useCameraDevice("back");

    const frameProcessor = useFrameProcessor((frame) => {
        "worklet";
        const barcodes = scanBarcodes(frame, [BarcodeFormat.QR_CODE]);
        if (barcodes.length > 0 && barcodes[0].content.data) {
            runOnJS(onCodeScanned)(String(barcodes[0].content.data));
        }
    }, []);

    if (!device) return null;

    return (
        <Camera
            style={StyleSheet.absoluteFill}
            device={device}
            isActive
            frameProcessor={frameProcessor}
            pixelFormat="yuv"          // faster than rgb for ML
        />
    );
}
```

`vision-camera-code-scanner` wraps Google MLKit Barcode Scanning (Android) and VisionKit
(iOS). Install it separately:

```bash
npm install vision-camera-code-scanner
npx pod-install
```

### Throttling the frame processor

Running inference on every frame wastes CPU. Use `useSkipFrame` or throttle manually:

```tsx
import { useFrameProcessor, useSkipFrame } from "react-native-vision-camera";

const frameProcessor = useFrameProcessor((frame) => {
    "worklet";
    // Only process every 3rd frame
    if (frame.timestamp % 3 !== 0) return;
    const barcodes = scanBarcodes(frame, [BarcodeFormat.QR_CODE]);
    // ...
}, []);
```

Or use the official `useSkipFrame` utility:

```tsx
const throttledProcessor = useSkipFrame({
    frameProcessor,
    every: 3,      // skip 2, process 1
});
```

---

## 4. Video Recording and Custom Output

```tsx
import { useRef } from "react";
import { Camera, VideoFile } from "react-native-vision-camera";

function VideoRecorder() {
    const camera = useRef<Camera>(null);
    const [recording, setRecording] = useState(false);

    const startRecording = () => {
        camera.current?.startRecording({
            videoCodec: "h265",          // HEVC for smaller files on iOS
            fileType: "mp4",
            onRecordingFinished: (video: VideoFile) => {
                console.log("Saved to:", video.path);
                uploadToR2(video.path);
            },
            onRecordingError: (err) => console.error(err),
        });
        setRecording(true);
    };

    const stopRecording = async () => {
        await camera.current?.stopRecording();
        setRecording(false);
    };

    return (
        <Camera
            ref={camera}
            device={device}
            isActive
            video
            audio
        />
    );
}

async function uploadToR2(filePath: string) {
    const RNFS = await import("react-native-fs");
    const base64 = await RNFS.readFile(filePath, "base64");
    const res = await fetch("https://api.example.com/upload/video", {
        method: "POST",
        headers: {
            "Content-Type": "video/mp4",
            "Content-Transfer-Encoding": "base64",
        },
        body: base64,
    });
    return res.json();
}
```

---

## 5. Zoom, Torch, and Device Switching

```tsx
import {
    Camera,
    useCameraDevice,
    useCameraDevices,
    CameraDevice,
} from "react-native-vision-camera";
import Animated, {
    useSharedValue,
    useAnimatedProps,
} from "react-native-reanimated";
import { Gesture, GestureDetector } from "react-native-gesture-handler";

const AnimatedCamera = Animated.createAnimatedComponent(Camera);

function AdvancedCamera() {
    const devices = useCameraDevices();
    const [facing, setFacing] = useState<"front" | "back">("back");
    const device = useCameraDevice(facing);
    const [torch, setTorch] = useState<"on" | "off">("off");
    const zoom = useSharedValue(device?.neutralZoom ?? 1);

    const pinchGesture = Gesture.Pinch().onUpdate((e) => {
        const newZoom = zoom.value * e.scale;
        zoom.value = Math.min(
            Math.max(newZoom, device?.minZoom ?? 1),
            device?.maxZoom ?? 10
        );
    });

    const animatedProps = useAnimatedProps(() => ({
        zoom: zoom.value,
    }));

    return (
        <GestureDetector gesture={pinchGesture}>
            <AnimatedCamera
                style={StyleSheet.absoluteFill}
                device={device!}
                isActive
                animatedProps={animatedProps}
                torch={torch}
            />
        </GestureDetector>
    );
}
```

---

## Anti-patterns

- **Calling async functions inside a frame processor** — worklets are synchronous; async calls
  will crash or produce undefined behaviour. Use `runOnJS` to bridge back to the JS thread for
  state updates.
- **Running heavy ML models on every frame without throttling** — on an iPhone 13 mini, a
  TFLite model at 30 fps pegs CPU at 95 %, heats the device, and triggers thermal throttling
  within 90 seconds. Always throttle or use the native `VisionFrameProcessorPlugin` with
  `AVCaptureVideoDataOutput` frame dropping.
- **Using `'rgb'` pixel format for ML models trained on YUV** — convert in the native plugin,
  not in the worklet; pixel format conversion in JS is CPU-prohibitive.
- **Enabling `photo` and `video` simultaneously without explicit output configuration** — on
  some Android devices this causes `CAMERA_ERROR: Too many outputs`. Enable only the outputs
  you need per screen.
- **Not calling `camera.current?.stopRecording()` on unmount** — leaves a dangling recording
  session that blocks the camera on Android until the process restarts.

---

## Gotchas

- **New Architecture required** — Vision Camera v4 will throw `VisionCamera is not enabled with
  the new architecture` on RN 0.72 and below. Enable Fabric in `android/gradle.properties`
  (`newArchEnabled=true`) and in the Podfile (`use_frameworks! :linkage => :static`).
- **Simulator limitations** — the iOS Simulator provides a fake camera feed (a spinning colour
  square). Frame processors run but receive synthetic frames; test barcode scanning only on
  physical devices.
- **Background camera access** — iOS terminates camera sessions when the app backgrounds.
  Re-set `isActive` to `false` in `AppState.change` to `"background"` and `true` on foreground
  to avoid the "Camera is already in use" error on re-activation.
- **Android camera2 vs. camera1** — Vision Camera v4 uses Camera2 exclusively. Devices running
  Android 5.0 (API 21) with `LEGACY` hardware level do not support concurrent streams; drop
  support below API 24.
- **Privacy manifest** — on iOS 17+, add `NSCameraUsageDescription` and
  `NSMicrophoneUsageDescription` to `PrivacyInfo.xcprivacy` as required reason APIs.

---

## Verification

```bash
# Check camera device list
npx react-native-vision-camera diagnose

# Log all available devices in JS
import { Camera } from "react-native-vision-camera";
Camera.getAvailableCameraDevices().then(console.log);
```

On a physical device with a QR code in frame, the frame processor should call `onCodeScanned`
within 150 ms at 30 fps. Verify via:

```ts
const start = performance.now();
// inside frameProcessor after decode:
runOnJS(console.log)(performance.now() - start, "ms decode");
```

Expected: < 50 ms per frame at 1080p on iPhone 13 and Pixel 7.

---

## Related

- `react-native-image-picker.md` — gallery picker without live camera
- `react-native-camera-permissions.md` — permission request flow, rationale dialogs
- `mobile-qr-barcode-scanning.md` — QR flow UX patterns and edge cases
- `react-native-new-architecture-fabric-jsi.md` — New Architecture prerequisites

## Sources

- Vision Camera v4 docs: https://react-native-vision-camera.com/docs/guides
- react-native-worklets-core: https://github.com/margelo/react-native-worklets-core
- vision-camera-code-scanner: https://github.com/rodgacki/vision-camera-code-scanner
- Apple privacy manifest: https://developer.apple.com/documentation/bundleresources/privacy_manifest_files
