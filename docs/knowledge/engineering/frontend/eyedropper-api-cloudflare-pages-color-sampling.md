# EyeDropper API — Screen Color Sampling on Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A design tool or image editor hosted on Cloudflare Pages needs a color picker that
can sample any pixel on screen — including content outside the browser window.
`<input type="color">` offers a native system picker but provides no screen-sampling
mode across all browsers. Canvas `getImageData` is confined to same-origin pixels.
Users expect the crosshair eyedropper cursor they find in Figma, the OS color picker,
or CSS-editing tools — and closing the page to use a third-party dropper is not an
acceptable workflow.

## Context

`EyeDropper` opens a system-level screen-sampling cursor. The user clicks any pixel
anywhere on screen; the API resolves a Promise with a hex color string. It requires
a transient user activation (a real click or key press) and operates only in secure
contexts — Cloudflare Pages satisfies the HTTPS requirement by default.

Browser support: Chrome 95+, Edge 95+. Firefox and Safari do not implement it as
of 2025. Feature-detect on `'EyeDropper' in window` and provide a hex input
fallback for unsupported environments.

There is no server component for the pick itself. Cloudflare Workers KV or D1 is
useful only if you persist palettes across sessions.

---

## 1. TypeScript Declarations

The API is not yet in lib.dom.d.ts on all TypeScript releases. Augment globals once.

```typescript
interface ColorSelectionResult {
  sRGBHex: string; // always lowercase 7-char hex: "#aabbcc"
}

interface EyeDropperConstructor {
  new (): EyeDropper;
}

interface EyeDropper {
  open(options?: { signal?: AbortSignal }): Promise<ColorSelectionResult>;
}

declare global {
  interface Window {
    EyeDropper?: EyeDropperConstructor;
  }
}

function supportsEyeDropper(): boolean {
  return typeof window !== 'undefined' && 'EyeDropper' in window;
}
```

---

## 2. Core Pick Function

```typescript
async function pickColorFromScreen(
  signal?: AbortSignal
): Promise<string | null> {
  if (!supportsEyeDropper()) return null;

  const dropper = new window.EyeDropper!();

  try {
    const result = await dropper.open({ signal });
    return result.sRGBHex;
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      // User pressed Escape or caller aborted
      return null;
    }
    throw err;
  }
}
```

The Promise rejects with `AbortError` when the user presses Escape or the provided
`AbortSignal` fires. Any other rejection is an unexpected error; surface it to the
UI rather than swallowing it silently.

---

## 3. Abort on Component Unmount (React)

If the component unmounts while the dropper is open the orphaned promise may later
call `setState` on a dead component. Cancel via `AbortController`.

```typescript
import { useCallback, useEffect, useRef } from 'react';

function useEyeDropper() {
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  const pick = useCallback(async (): Promise<string | null> => {
    controllerRef.current?.abort();
    controllerRef.current = new AbortController();
    return pickColorFromScreen(controllerRef.current.signal);
  }, []);

  return { pick, supported: supportsEyeDropper() };
}
```

---

## 4. Color Format Utilities

The API always returns lowercase 6-digit hex. Convert to other formats as needed
without adding a library dependency.

```typescript
function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

function hexToHsl(hex: string): [number, number, number] {
  const [r, g, b] = hexToRgb(hex).map(x => x / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0, s = 0;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }

  return [Math.round(h * 360), Math.round(s * 100), Math.round(l * 100)];
}

function hexToCssHsl(hex: string): string {
  const [h, s, l] = hexToHsl(hex);
  return `hsl(${h} ${s}% ${l}%)`;
}

// Normalize picked color to uppercase for display
function normalizePick(hex: string): string {
  return hex.toUpperCase();
}
```

---

## 5. Persisting a User Palette to Cloudflare Workers KV

```typescript
// workers/palette.ts
interface PaletteEntry {
  hex: string;
  label?: string;
  pickedAt: number;
}

interface Env {
  PALETTE_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // Identify user via Cloudflare Access header
    const userId = request.headers.get('Cf-Access-Authenticated-User-Email') ?? 'anon';

    if (request.method === 'POST' && url.pathname === '/palette') {
      const body = await request.json<{ hex: string; label?: string }>();
      if (!/^#[0-9a-f]{6}$/i.test(body.hex)) {
        return new Response('Invalid hex', { status: 422 });
      }
      const entry: PaletteEntry = {
        hex:      body.hex.toLowerCase(),
        label:    body.label?.slice(0, 80),
        pickedAt: Date.now(),
      };
      await env.PALETTE_KV.put(
        `${userId}:${entry.hex}`,
        JSON.stringify(entry),
        { expirationTtl: 60 * 60 * 24 * 90 }
      );
      return Response.json({ ok: true }, { status: 201 });
    }

    if (request.method === 'GET' && url.pathname === '/palette') {
      const list = await env.PALETTE_KV.list({ prefix: `${userId}:` });
      const entries = await Promise.all(
        list.keys.map(k => env.PALETTE_KV.get<PaletteEntry>(k.name, 'json'))
      );
      return Response.json(entries.filter(Boolean));
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- Calling `dropper.open()` outside a user gesture. The Promise rejects with
  `NotAllowedError` — the transient activation requirement is enforced by the
  browser, not negotiable.
- Not providing an `AbortSignal`. Orphaned promises after unmount set state on dead
  components in React and leak the dropper cursor on navigation.
- Rendering the eyedropper button unconditionally in Firefox and Safari. Gate the
  button on `supportsEyeDropper()` and show a plain `<input type="text">` hex
  fallback.
- Assuming the returned hex is uppercase. The spec mandates lowercase; normalize
  before storing or comparing colors.
- Storing the hex without input-validating it on the server. A malicious client
  could POST arbitrary strings; validate the `#[0-9a-f]{6}` pattern in Workers.

## Gotchas

- `sRGBHex` is always exactly 7 characters (`#` + 6 hex digits). There is no alpha
  channel; the API cannot sample transparency.
- On HDR or wide-gamut displays, the sampled color is clamped to sRGB. The pixel
  the user sees may be perceptually different from the hex value returned.
- The dropper cannot be opened inside a sandboxed iframe unless `allow-same-origin`
  is present and the `eyedropper` permission policy grants access.
- Chrome on Android does not implement `EyeDropper` as of mid-2025; the API is
  desktop-only in practice.
- Opening `EyeDropper` while DevTools is focused fails in some Chrome builds because
  the dropper canvas cannot composite over the DevTools panel.

## Verification

```typescript
// In DevTools console on an HTTPS page (not localhost):
const d = new EyeDropper();
d.open()
  .then(r => console.log('Picked:', r.sRGBHex))
  .catch(e => console.warn('Error:', e.name, e.message));
// Click any pixel; lowercase hex should appear in console
```

Verify format: the returned value must match `/^#[0-9a-f]{6}$/`. Test the Escape
key cancellation path and confirm `null` is returned without throwing in your UI.

## Related

- `browser-clipboard-api.md`
- `css-custom-properties-theming.md`
- `browser-file-system-access.md`

## Sources

- WICG EyeDropper API — https://wicg.github.io/eyedropper-api/
- MDN EyeDropper — https://developer.mozilla.org/en-US/docs/Web/API/EyeDropper
- Chrome Platform Status — https://chromestatus.com/feature/6304275594477568
