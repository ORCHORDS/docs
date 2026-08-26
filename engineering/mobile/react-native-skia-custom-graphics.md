# React Native Skia for Custom 2D Graphics

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your design requires visualisations that Animated API, SVG, or even Reanimated cannot express
efficiently: waveform oscilloscopes for audio tracks, custom drawing canvases, blur-behind
frosted-glass cards, particle effects, or interactive paint tools. `react-native-svg` redraws
via the bridge on every frame, causing dropped frames above 120 elements. You need a GPU-backed,
thread-safe 2D canvas that composites in the same render pipeline as the native view hierarchy.

## Context

`@shopify/react-native-skia` (version 1.x) embeds Google's Skia graphics library — the same
engine that backs Chrome, Flutter, and Android's Canvas 2D — directly into a React Native
component. Rendering happens on a dedicated Skia thread; the output is composited by the native
GPU compositor without going through the React Native bridge.

Key capabilities:
- `<Canvas>` component with a declarative child DSL: `<Path>`, `<Image>`, `<Text>`, `<Blur>`,
  `<ColorMatrix>`, `<RuntimeEffect>` (GLSL-compatible shaders)
- Animated values via `useSharedValue` from Reanimated — no JS-thread involvement on each frame
- `usePicture` for recording draw commands once and replaying cheaply
- `useImage` for GPU-side image decoding and caching
- `makeImageSnapshot` for pixel-perfect off-screen rendering and export

Minimum requirements: React Native 0.73+, New Architecture, Reanimated 3+.

---

## 1. Installation and Setup

```bash
npm install @shopify/react-native-skia
npx pod-install
```

`app.json` (Expo):

```json
{
  "expo": {
    "plugins": ["@shopify/react-native-skia"]
  }
}
```

The Skia plugin builds the Skia binary as a prebuilt `.xcframework` / `.aar`; no manual native
configuration is needed. Build time increases by ~2 minutes due to the library size (18 MB iOS,
12 MB Android).

Verify the installation:

```tsx
import { Canvas, Circle } from "@shopify/react-native-skia";

export default function SkiaTest() {
    return (
        <Canvas style={{ flex: 1 }}>
            <Circle cx={100} cy={100} r={50} color="tomato" />
        </Canvas>
    );
}
```

---

## 2. Audio Waveform Visualiser

A common use case: real-time amplitude waveform rendered at 60 fps from audio analyser data.

```tsx
import React, { useCallback, useEffect } from "react";
import { Canvas, Path, Skia, useDerivedValue } from "@shopify/react-native-skia";
import { useSharedValue, withSpring } from "react-native-reanimated";

interface WaveformProps {
    amplitudes: number[];   // values 0–1, sampled from Web Audio analyser or AVAudioNode
    width: number;
    height: number;
    color?: string;
}

export function Waveform({ amplitudes, width, height, color = "#6B4FBB" }: WaveformProps) {
    const progress = useSharedValue(0);

    // Animate in on mount
    useEffect(() => {
        progress.value = withSpring(1);
    }, []);

    const path = useDerivedValue(() => {
        const p = Skia.Path.Make();
        if (amplitudes.length === 0) return p;

        const midY = height / 2;
        const step = width / (amplitudes.length - 1);

        p.moveTo(0, midY);
        amplitudes.forEach((amp, i) => {
            const x = i * step;
            const yOffset = amp * midY * progress.value;
            if (i === 0) {
                p.lineTo(x, midY - yOffset);
            } else {
                const prevX = (i - 1) * step;
                const ctrlX = (prevX + x) / 2;
                p.cubicTo(ctrlX, midY - amplitudes[i - 1] * midY * progress.value, ctrlX, midY - yOffset, x, midY - yOffset);
            }
        });
        // Mirror for the bottom half
        for (let i = amplitudes.length - 1; i >= 0; i--) {
            const x = i * step;
            const yOffset = amplitudes[i] * midY * progress.value;
            p.lineTo(x, midY + yOffset);
        }
        p.close();
        return p;
    }, [amplitudes, height, width, progress]);

    return (
        <Canvas style={{ width, height }}>
            <Path
                path={path}
                color={color}
                style="fill"
                opacity={0.85}
            />
        </Canvas>
    );
}
```

---

## 3. Frosted Glass / Blur Behind Effect

`BackdropBlur` composites a Gaussian blur over whatever is rendered behind the Canvas.

```tsx
import {
    Canvas,
    BackdropBlur,
    RoundedRect,
    rect,
    rrect,
} from "@shopify/react-native-skia";
import { View, Text } from "react-native";

export function FrostedCard({ children }: { children: React.ReactNode }) {
    const RADIUS = 16;
    return (
        <View style={{ position: "relative" }}>
            {/* Skia canvas for the blur layer */}
            <Canvas
                style={{
                    position: "absolute",
                    top: 0, left: 0, right: 0, bottom: 0,
                    borderRadius: RADIUS,
                    overflow: "hidden",
                }}
            >
                <BackdropBlur
                    blur={12}
                    clip={rrect(
                        rect(0, 0, 340, 180),
                        RADIUS, RADIUS
                    )}
                >
                    {/* Tinted overlay on top of the blur */}
                    <RoundedRect
                        x={0} y={0} width={340} height={180}
                        r={RADIUS}
                        color="rgba(255,255,255,0.2)"
                    />
                </BackdropBlur>
            </Canvas>
            {/* Regular RN children render above */}
            <View style={{ padding: 16 }}>{children}</View>
        </View>
    );
}
```

> Note: `BackdropBlur` renders the Skia canvas as a layer on top of native views. For dynamic
> content behind it (e.g. a FlatList), wrap the list and the card in a single `<Canvas>` using
> `useImage` snapshot approach, or use the experimental `SkiaView.makeImageSnapshot()` for
> periodic captures.

---

## 4. Interactive Drawing Canvas

Drawing tool with pressure-sensitive stroke width via Gesture Handler:

```tsx
import { useRef, useState } from "react";
import { StyleSheet } from "react-native";
import {
    Canvas,
    Path,
    SkPath,
    Skia,
    useTouchHandler,
} from "@shopify/react-native-skia";
import { Gesture, GestureDetector } from "react-native-gesture-handler";

export function DrawingCanvas({ width, height }: { width: number; height: number }) {
    const [paths, setPaths] = useState<SkPath[]>([]);
    const currentPath = useRef<SkPath | null>(null);

    const touchHandler = useTouchHandler({
        onStart: ({ x, y }) => {
            const p = Skia.Path.Make();
            p.moveTo(x, y);
            currentPath.current = p;
        },
        onActive: ({ x, y }) => {
            currentPath.current?.lineTo(x, y);
            // Force re-render by replacing the array ref
            setPaths((prev) => [...prev.slice(0, -1), currentPath.current!]);
        },
        onEnd: () => {
            if (currentPath.current) {
                setPaths((prev) => [...prev, currentPath.current!]);
            }
            currentPath.current = null;
        },
    });

    return (
        <Canvas
            style={{ width, height, backgroundColor: "#0a0a0a" }}
            onTouch={touchHandler}
        >
            {paths.map((p, i) => (
                <Path
                    key={i}
                    path={p}
                    color="#9B7BFF"
                    style="stroke"
                    strokeWidth={3}
                    strokeCap="round"
                    strokeJoin="round"
                />
            ))}
        </Canvas>
    );
}
```

### Export to image

```tsx
import { makeImageFromView, Canvas } from "@shopify/react-native-skia";
import { useRef } from "react";
import { View } from "react-native";
import RNFS from "react-native-fs";

function ExportableCanvas() {
    const canvasRef = useRef<any>(null);

    const exportPNG = async () => {
        const image = await makeImageFromView(canvasRef);
        const base64 = image?.encodeToBase64();
        if (!base64) return;
        const path = `${RNFS.DocumentDirectoryPath}/drawing_${Date.now()}.png`;
        await RNFS.writeFile(path, base64, "base64");
        return path;
    };

    return <Canvas ref={canvasRef} style={{ flex: 1 }} />;
}
```

---

## 5. GLSL Runtime Shaders

Skia's `RuntimeEffect` accepts a Skia Shading Language (SkSL) program — a GLSL subset — for
fully custom per-pixel GPU effects.

```tsx
import { Canvas, Fill, Shader, Skia, vec } from "@shopify/react-native-skia";
import { useDerivedValue, useSharedValue, withRepeat, withTiming } from "react-native-reanimated";

const AURORA_SHADER = Skia.RuntimeEffect.Make(`
  uniform float time;
  uniform float2 resolution;

  half4 main(float2 fragCoord) {
    float2 uv = fragCoord / resolution;
    float wave = sin(uv.x * 6.0 + time) * 0.5 + 0.5;
    float3 col = mix(
      float3(0.4, 0.1, 0.8),
      float3(0.1, 0.7, 0.9),
      wave * uv.y
    );
    return half4(col, 1.0);
  }
`)!;

export function AuroraBackground({ width, height }: { width: number; height: number }) {
    const time = useSharedValue(0);

    // Animate time uniform
    time.value = withRepeat(withTiming(Math.PI * 2, { duration: 4000 }), -1, false);

    const uniforms = useDerivedValue(() => ({
        time: time.value,
        resolution: vec(width, height),
    }));

    return (
        <Canvas style={{ width, height }}>
            <Fill>
                <Shader source={AURORA_SHADER} uniforms={uniforms} />
            </Fill>
        </Canvas>
    );
}
```

---

## Anti-patterns

- **Recreating `Skia.Path.Make()` inside a `useDerivedValue`** — `useDerivedValue` runs on the
  UI thread as a worklet; `Skia.Path.Make()` is safe there but allocates a new object every
  frame. Cache the path and mutate it with `p.reset()` + re-draw for high-frequency updates.
- **Using Skia for simple text and icon rendering** — if your design can be expressed with
  `<Text>` and `<Image>` components, use them. Skia adds ~20 MB to your IPA/APK and should
  only be pulled in when native views cannot achieve the required visual.
- **Mixing Skia Canvas children with React Native views** — children of `<Canvas>` are Skia
  nodes, not RN views. You cannot put a `<TouchableOpacity>` inside a `<Canvas>`. Use
  `useTouchHandler` or overlay a transparent RN view for interaction.
- **Large `paths` state arrays without cleanup** — a drawing app that accumulates thousands of
  paths will exhaust memory. Periodically flatten completed strokes into a single `SkImage`
  snapshot using `makeImageSnapshot` and replace the path array.
- **Blocking the JS thread with `encodeToBase64`** — image export can stall the JS thread for
  50–200 ms on large canvases. Offload to a background thread via `InteractionManager` or Expo
  background task.

---

## Gotchas

- **New Architecture required** — Skia uses JSI and Worklets; it will crash on old architecture
  with a `TypeError: null is not an object (evaluating 'SkiaApi.MakeImageFromEncoded')`.
- **Android 64-bit only** — the Skia prebuilt `.aar` ships x86_64 and arm64-v8a slices only.
  Drop x86 from your ABI split or the build will fail.
- **Text rendering on Android** — Skia uses its own font renderer, bypassing Android's font
  stack. System emoji and CJK fallback fonts may not render; embed the required font files
  using `Skia.Font` with a bundled `.ttf`.
- **Memory on low-RAM devices** — the Skia GPU surface and texture cache can consume 40–80 MB.
  On devices with < 2 GB RAM, reduce the canvas resolution via `devicePixelRatio: 1` on the
  `<Canvas>` component.
- **Expo Go not supported** — Skia requires a native build. Use `expo-dev-client` or a
  development build; `npx expo start` with Expo Go will throw a `native module not found` error.

---

## Verification

```bash
# Render a filled circle and confirm GPU compositing (no jank at 60 fps):
# Open React Native Dev Menu → Performance Monitor
# GPU Frames should be consistently green; JS thread should idle at < 1 ms/frame

# Check Skia version and GPU backend in use:
import { Skia } from "@shopify/react-native-skia";
console.log(Skia.RuntimeEffect.Make("half4 main(float2 p) { return half4(1); }") ? "GPU OK" : "CPU fallback");
```

---

## Related

- `react-native-reanimated.md` — `useSharedValue` and worklet patterns that drive Skia animations
- `react-native-gesture-handler.md` — gesture input for interactive Skia canvases
- `react-native-new-architecture-fabric-jsi.md` — JSI prerequisites
- `mobile-performance-profiling.md` — profiling Skia render time with Systrace

## Sources

- React Native Skia docs: https://shopify.github.io/react-native-skia/
- Skia SkSL reference: https://skia.org/docs/user/sksl/
- Shopify engineering blog post on Skia: https://shopify.engineering/react-native-skia
- WWDC 2023 "Animate with springs": https://developer.apple.com/videos/play/wwdc2023/10158/
