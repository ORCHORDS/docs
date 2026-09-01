# WebGL Context Loss Handling And Restore

## Scope

Handling the `webglcontextlost` and `webglcontextrestored` events on an HTML canvas WebGL context: preventing the default loss behavior, rebuilding all GPU resources after restore, the `WEBGL_lose_context` extension for testing, the `webglcontextcreationerror` path, and preemption triggers (GPU resets, driver crashes, resource pressure, backgrounding). Covers application-side resource ledger design; excludes WebGL rendering technique and the WebGPU device-lost model, which is a different contract covered by the WebGPU canvas article in this leaf.

## Workflow or implementation guidance

A WebGL context is a process-wide GPU resource lease, and the browser can revoke it at any time: a driver reset, too many live contexts in the page (each tab gets a small budget), an out-of-memory in a texture upload, or background-tab reclamation under memory pressure. When that happens the context object stays alive but every GPU-backed object it created — buffers, textures, programs, framebuffers — is invalidated at once, and all GL calls become no-ops that log warnings. Nothing throws; without handlers the app shows a frozen frame or black canvas forever.

The first line of defense is small and mandatory:

```js
canvas.addEventListener('webglcontextlost', (e) => {
  e.preventDefault();                 // required: signals you will handle restore
  setRenderState('suspended');        // stop the rAF loop; GL calls are now no-ops
  showRecoveryUI();
}, false);

canvas.addEventListener('webglcontextrestored', () => {
  rebuildEverything();                // full GPU resource reconstruction
  setRenderState('running');          // resume rAF
}, false);
```

`e.preventDefault()` on the loss event is what makes restoration possible: per the WebGL spec, canceling the event tells the implementation you intend to reinitialize when the context is restored. Skip it and the canvas will never restore — the single most common bug in this area. The `webglcontextrestored` event fires on the same canvas when the browser has handed back a fresh context; `gl` handles, extensions, and state are all new, so restore is not "resume", it is "recreate".

The resource ledger is the architecture that makes restore tractable. Every GPU object creation goes through a registry that records how to rebuild it:

```js
const ledger = [];  // { rebuild: (gl) => void } in creation order

function createProgramFromSources(gl, vsSrc, fsSrc) {
  const entry = { program: null, rebuild() {
    entry.program = compileAndLink(gl, vsSrc, fsSrc);
  }};
  entry.rebuild();
  ledger.push(entry);
  return entry.program;
}
```

On restore, reset `gl = canvas.getContext('webgl2')` properties you cached (extensions must be re-requested: `gl.getExtension('EXT_color_buffer_float')` again), then run the ledger in order — programs before the textures/framebuffers that attach them — then re-upload any CPU-resident data (vertex arrays, image bitmaps) that never lived on the GPU. Data that only existed GPU-side (render-to-texture results, transform feedback buffers) is gone and must be recomputed; design the pipeline so the expensive stage can re-run from a CPU copy.

Keep the render loop gated on a state flag. During suspension the loop must not issue GL work (no-op calls hide bugs and mask the restore), and immediately after restore the first frame should re-establish global state you set at init time (viewport, clear color, enabled capabilities) because default state returned.

Test the whole path deterministically with the `WEBGL_lose_context` extension — it exists precisely for this:

```js
const lose = gl.getExtension('WEBGL_lose_context');
lose.loseContext();      // fires webglcontextlost asynchronously
// later
lose.restoreContext();   // fires webglcontextrestored
```

Losing and restoring in automated tests and a dev-only keyboard shortcut exercises the ledger on every commit, catching "works only on first init" regressions (state set outside the ledger is the usual culprit).

Context creation itself can fail — `canvas.getContext('webgl2')` returning `null` — and `webglcontextcreationerror` (on the canvas, with `statusMessage`) explains why (blocklisted driver, too many contexts). Treat creation failure as the same UX path as loss: a fallback renderer or an explanatory screen, not a crash.

## Controls

- `preventDefault()` on `webglcontextlost`; without it restore never happens — enforce with a lint/grep check on the handler.
- All GPU object creation flows through the rebuild ledger; no bare `gl.createTexture()` calls at call sites outside the registry.
- rAF loop gated on render state; zero GL calls between loss and restore-complete.
- Extensions re-acquired inside the restore path, never cached across a loss event.
- `WEBGL_lose_context` wired to a dev hotkey and included in the automated test suite, so the ledger runs against every change.
- CPU-side source data (mesh arrays, image sources) retained as long as their GPU counterparts, so rebuild never depends on re-fetching assets.

## Validation evidence

- Automated restore test: build the scene, force `loseContext()`, assert the loss handler suspended the loop and the UI surfaced; then `restoreContext()`, assert the ledger rebuilt every entry (count matches creation count) and the next rendered frame passes a pixel-diff against the pre-loss frame within tolerance.
- Repeated-loss soak: run lose/restore 20 times consecutively; assert no memory growth (GPU memory via `performance.memory`/about:gpu style probes or instrumented sizes) and no missing-ledger-entry errors.
- Multi-context pressure test: open the app in enough tabs/canvases to trip the browser's context budget; assert the oldest hidden canvas's loss is handled by suspension (not a crash) and restores when the tab is foregrounded.
- Creation-failure test: stub `getContext` to return `null` and dispatch `webglcontextcreationerror`; assert the fallback UI renders with the event's `statusMessage` logged.

## Failure modes and correction

- Canvas stays black forever after a driver reset: no `webglcontextlost` listener (or missing `preventDefault()`). Add the handler pair; the browser logs "Cannot restore context" when the event wasn't canceled.
- App restores but renders garbage or invisible geometry: state set during init outside the ledger (viewport, `enable(DEPTH_TEST)`, sampler bindings) was never re-applied; move all init into ledger-ordered or post-restore functions.
- "Object is from a different (or lost) context" console errors: cached GL objects were reused after restore; all object references must be invalidated at loss and re-fetched from the ledger.
- Restore test passes locally but production restore fails: shaders compiled with driver-specific extensions or float-texture paths that need re-requested extensions; re-acquire every extension inside restore and assert their presence.
- Contexts lost too readily: too many canvases or oversized textures/FBOs on the page; consolidate render targets, downscale allocations, or release contexts (`WEBGL_lose_context.loseContext()` without restore) for thumbnails no longer visible.
- Loss during a texture upload loop: the upload loop kept issuing no-op calls after loss and the UI appeared to hang; gate every loop iteration on the render state flag.

## Limitations

- The spec gives no guarantee of when or whether a lost context is restored; `preventDefault` is necessary but the restore can still be indefinitely delayed by a permanently reset GPU.
- GPU-only data (render targets, feedback buffers) is unrecoverable by definition; the pipeline must tolerate recompute.
- `WEBGL_lose_context` simulates loss only; it cannot reproduce driver-specific partial-reset behaviors.
- Context budget thresholds and backgrounding policies are browser- and platform-specific and change between versions; treat "too many contexts" empirically.
- WebGL 1 vs 2 availability differs (and creation can fail entirely on blocklisted drivers); the `webglcontextcreationerror` + null-context path must ship alongside the WebGL2 assumption.

## Canonical sources

- Khronos Group, WebGL Specification, context loss and restore: https://registry.khronos.org/webgl/specs/latest/1.0/#5.15.2
- Khronos Group, WebGL Specification, The Context Lost Event: https://registry.khronos.org/webgl/specs/latest/1.0/#CONTEXT_LOST
- MDN, `webglcontextlost` event: https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/webglcontextlost_event
- MDN, `WEBGL_lose_context` extension: https://developer.mozilla.org/en-US/docs/Web/API/WEBGL_lose_context
