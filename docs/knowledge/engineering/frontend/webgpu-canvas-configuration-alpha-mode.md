# WebGPU Canvas Configuration and Alpha Mode

WebGPU renders to surfaces, and in a browser the surface is the canvas. The configuration step — `context.configure()` with a format, an alpha mode, and view format list — decides how your rendered pixels composite onto the page: opaque or transparent, premultiplied or not. Getting alpha mode wrong produces the two classic symptoms: everything invisible (drawing colors as if straight alpha while the compositor expects premultiplied) or dark halos around blended edges. This article covers the configuration surface, `alpha-mode` semantics (opaque, premultiplied, the legacy interplay), format selection, and reconfiguration lifecycle.

## Scope

This article addresses WebGPU canvas-context configuration in browsers: `GPUCanvasContext.configure()` options (device, format, alphaMode, viewFormats), alpha compositing modes (`opaque` and `premultiplied`), preferred canvas format selection, configuration lifecycle (configure/unconfigure/reconfigure), and interaction with CSS compositing of the canvas element. It covers rendering correctness for 2D and 3D content compositing into pages. It does not cover WebGPU pipeline/shader authoring, MSAA, or readback paths beyond `copyExternalImageToTexture`/texture usage notes.

## Workflow or implementation guidance

The canvas is acquired and configured:

```js
const canvas = document.querySelector('canvas');
const context = canvas.getContext('webgpu');
const format = navigator.gpu.getPreferredCanvasFormat();
context.configure({
  device,
  format,
  alphaMode: 'opaque',   // or 'premultiplied'
});
```

The decisions inside `configure()`:

1. **Format.** `navigator.gpu.getPreferredCanvasFormat()` returns what the platform composites natively (`'bgra8unorm'` on most, `'rgba8unorm'` elsewhere). Use it rather than hardcoding — a mismatch with the display's preference costs an internal conversion. The format must match what your render pipelines output (or you add a conversion pass).
2. **Alpha mode — the compositing contract.**
   - `opaque`: the canvas is treated as fully opaque; the alpha channel of your output is ignored for compositing. Use this when the page background behind the canvas is irrelevant — the common case for full-viewport renderers. It also lets the browser skip blending work.
   - `premultiplied`: each pixel's RGB must already be multiplied by its alpha (a 50%-transparent red pixel is stored as (0.5, 0, 0, 0.5), not (1, 0, 0, 0.5)). The compositor blends the canvas over the page using these values. Choose this when the canvas must show page content through it — HUD overlays, effects layers, rounded-video frames.
   - The browser implementation history matters: the WebGPU spec removed the non-premultiplied mode that early drafts and the WebGL world (`alpha: true` with `premultipliedAlpha: false` in WebGL contexts) carried — in WebGPU the choice is exactly `opaque` or `premultiplied`. Teams porting WebGL code that relied on straight-alpha blending must either premultiply in their render pass or insert a conversion in a final blit shader.
3. **The premultiplication bug class.** If your pipeline writes straight-alpha colors while configured `premultiplied`, colors bleed: semi-transparent edges render brighter than intended and the whole layer can look blown out; fully transparent pixels carry random RGB ("color fringing" on edges) because the compositor trusts garbage RGB under zero alpha. The fix belongs in the shader: output `color.rgb *= color.a` as the final step, or configure your blend state so targets store premultiplied results consistently. Document the contract at the pipeline level (a `// outputs premultiplied alpha` note on the final pass) so future passes don't silently break the invariant.
4. **`viewFormats`.** If you need `getCurrentTexture().createView()` with a format other than the configured one (rare; e.g., resolving to sRGB variants), list it in `viewFormats` at configure time; creating views with unlisted formats is an error. Most apps pass none.
5. **Reconfiguration lifecycle.** `configure()` may be called again (device lost and recreated, format change); the previous configuration is replaced. `unconfigure()` removes the association (canvas goes back to blank). After device loss, reconfigure with the new device before next frame. Resizing the canvas (CSS or attribute) does not require reconfiguration — `getCurrentTexture()` each frame yields a texture sized to the canvas; just re-render.
6. **Clear color and alpha mode interplay.** With `premultiplied`, a clear to fully transparent is `(0,0,0,0)`; a clear that *looks* like "background color at 100% opacity through the layer" must be expressed premultiplied: `bg.rgb * bg.a` in the clear color. A clear of `(0.2, 0.4, 0.6, 0.5)`-as-straight yields a wrong composite; the correct premultiplied clear is `(0.1, 0.2, 0.3, 0.5)`.
7. **CSS on the canvas element.** The canvas composites as a normal element: `opacity`, `mix-blend-mode`, and CSS transforms apply *after* WebGPU compositing. If you need the canvas itself half-transparent over the page, `alphaMode: 'opaque'` plus CSS `opacity: 0.5` is often simpler and cheaper than premultiplied rendering — decide at the design level which layer owns transparency.

A worked example: a video-effects demo overlays WebGPU-processed frames with soft rounded corners over page content. Pipeline: render pass writes processed RGBA; final blit shader applies the corner mask and outputs `rgb *= a`; context configured `alphaMode: 'premultiplied'`. The overlay composites cleanly. An initial port from WebGL shipped straight-alpha output with `premultiplied` configured — edges glowed; the one-line premultiply in the final shader fixed it. The same demo's fullscreen mode switches the same canvas to `opaque` (nothing behind it) by reconfiguring, saving the compositor blending work.

## Controls

- Assert the configured format equals `getPreferredCanvasFormat()` output in dev builds; hardcoding drift shows up as subtle perf loss or errors on other platforms.
- Encode the alpha contract in one place: final-pass shaders declare their output convention in comments and a unit-style render test (render a known semi-transparent quad over a known background, read back via `copyTextureToBuffer`, assert the composited-equivalent values) catches straight-vs-premultiplied regressions that visual review misses on subtle content.
- Handle `device.lost` with reconfigure-on-reacquire; a smoke test that simulates loss (dev-only device destroy) verifies the reconfiguration path works before production does it for you.
- Keep exactly one configure site in the app (the renderer owns it); ad hoc reconfigures from feature code create format/alpha-mode races that manifest as one-frame flicker.
- Test compositing against non-trivial page backgrounds (gradients, images) — transparent-canvas bugs are invisible against white pages.

## Validation evidence

- `GPUCanvasContext.configure` options (device, format, alphaMode, viewFormats), the `opaque` and `premultiplied` alpha mode semantics, `getPreferredCanvasFormat()`, and configuration/reconfiguration lifecycle are specified in the WebGPU specification published by the W3C (WebGPU Working Group), including the normative compositing behavior for each alpha mode.
- The premultiplied-alpha compositing model the modes reference is the long-standing model documented across W3C/WHATWG compositing specifications and implemented by browser compositors.
- A reproducible check: configure two identical canvases one `opaque`, one `premultiplied`; render the same straight-alpha gradient; the `premultiplied` canvas shows the characteristic over-bright bleed; add the premultiply in the final shader and the two match (except where alpha < 1 shows the page through) — the contract demonstrated in a before/after screenshot pair.

## Failure modes and correction

- **Straight-alpha output with premultiplied mode.** Symptom: blown-out semi-transparent regions, glowing edges. Correct by premultiplying in the final pass (or converting in the blit).
- **Garbage RGB under zero alpha.** Symptom: fringes around cutouts. Correct by clearing to (0,0,0,0) and keeping RGB premultiplied throughout.
- **Hardcoded format.** Symptom: conversion cost or validation errors on other platforms. Correct by `getPreferredCanvasFormat()`.
- **Stale configuration after device loss.** Symptom: canvas blank after GPU reset. Correct by reconfigure-on-reacquire in the loss handler.
- **Reconfigure races.** Symptom: intermittent one-frame wrong compositing. Correct by single-owner configuration.

## Limitations

- WebGPU's alpha modes are the two specified; no straight-alpha compositing mode exists — conversion is the app's responsibility where legacy assets assume it.
- Canvas compositing details (color management, HDR canvases) continue to evolve in the specification; pin behavior checks to engine versions and re-verify on browser updates.
- `getCurrentTexture()` textures have usage and lifetime constraints (valid for the frame, cannot be reused); readback requires staging textures — plan validation around those rules.
- Very large canvases on low-memory devices have platform ceilings unrelated to configuration correctness.

## Canonical sources

- W3C WebGPU Working Group, WebGPU Specification — canvas configuration and alpha compositing: https://www.w3.org/TR/webgpu/
- W3C WebGPU Community Group, gpuweb — WebGPU specification development repository (editor's drafts and issues): https://gpuweb.github.io/gpuweb/
