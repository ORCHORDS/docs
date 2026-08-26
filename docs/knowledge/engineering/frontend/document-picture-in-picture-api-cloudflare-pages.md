# Document Picture-in-Picture API — Cloudflare Pages Floating UI

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You want a floating, always-on-top window — a media player, a live-score widget, a
video-call controls bar — that persists while the user navigates your SPA hosted on
Cloudflare Pages. The native `<video>` PiP only works for video elements; Document PiP
lets you put arbitrary HTML into that floating window.

## Context

The Document Picture-in-Picture API (`window.documentPictureInPicture`) landed in
Chrome 116 and Edge 116. Safari and Firefox do not yet implement it (2026-08). The API
requires a user gesture, runs the floating window in a separate browsing context (its
own `Window` object, same origin), and closes automatically when the opener navigates
away or calls `close()`.

Cloudflare Pages has no special server-side requirements — the API is pure client-side.
The only hosting concern is the `Permissions-Policy` header, which must not block
`picture-in-picture`.

## Feature Detection and Progressive Enhancement

```typescript
// lib/pip.ts
export const supportsDocumentPiP =
  typeof window !== 'undefined' &&
  'documentPictureInPicture' in window;

export async function openDocumentPiP(
  width = 400,
  height = 300,
): Promise<Window | null> {
  if (!supportsDocumentPiP) return null;
  try {
    const pipWindow = await window.documentPictureInPicture.requestWindow({
      width,
      height,
      disallowReturnToOpener: false,
    });
    return pipWindow;
  } catch (err) {
    // User denied or gesture missing
    console.warn('Document PiP failed:', err);
    return null;
  }
}
```

Always gate behind the feature check. On unsupported browsers fall back to a
fixed-position overlay (`position: fixed; z-index: 9999`).

## Moving DOM Nodes into the PiP Window

The PiP window is a real `Document`. You can `appendChild` existing DOM nodes into it.
The node is *moved*, not cloned — event listeners travel with it.

```typescript
// components/PlayerPiP.tsx  (React 19)
import { useRef, useState, useCallback } from 'react';
import { openDocumentPiP, supportsDocumentPiP } from '../lib/pip';

export function PlayerPiP({ children }: { children: React.ReactNode }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pipWindowRef = useRef<Window | null>(null);
  const [inPiP, setInPiP] = useState(false);

  const enter = useCallback(async () => {
    const pipWin = await openDocumentPiP(480, 270);
    if (!pipWin || !containerRef.current) return;

    // Mirror stylesheets from the opener into the PiP document
    for (const link of document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')) {
      const cloned = pipWin.document.createElement('link');
      cloned.rel = 'stylesheet';
      cloned.href = link.href;
      pipWin.document.head.appendChild(cloned);
    }

    pipWin.document.body.style.margin = '0';
    pipWin.document.body.appendChild(containerRef.current);
    pipWindowRef.current = pipWin;
    setInPiP(true);

    pipWin.addEventListener('pagehide', () => {
      // Node returns automatically when PiP closes — re-attach to opener
      document.getElementById('player-slot')?.appendChild(containerRef.current!);
      pipWindowRef.current = null;
      setInPiP(false);
    });
  }, []);

  const exit = useCallback(() => {
    pipWindowRef.current?.close();
  }, []);

  return (
    <div>
      <div id="player-slot">
        <div ref={containerRef}>{children}</div>
      </div>
      {supportsDocumentPiP && (
        <button onClick={inPiP ? exit : enter}>
          {inPiP ? 'Close floating player' : 'Open floating player'}
        </button>
      )}
    </div>
  );
}
```

## Syncing State Between Opener and PiP Window

The PiP browsing context shares the same origin, so `BroadcastChannel` and
`localStorage` events work across it. For real-time playback state prefer
`BroadcastChannel`.

```typescript
// lib/pip-sync.ts
const CHANNEL = 'pip-player';

export function createPiPSync() {
  const bc = new BroadcastChannel(CHANNEL);

  function send(msg: { type: string; payload?: unknown }) {
    bc.postMessage(msg);
  }

  function onMessage(handler: (msg: { type: string; payload?: unknown }) => void) {
    bc.addEventListener('message', (e) => handler(e.data));
    return () => bc.close();
  }

  return { send, onMessage };
}

// In PiP window — listen for seek events from opener controls
const sync = createPiPSync();
sync.onMessage(({ type, payload }) => {
  if (type === 'SEEK' && typeof payload === 'number') {
    videoEl.currentTime = payload;
  }
});
```

## Cloudflare Pages Headers Configuration

Add to `public/_headers` to ensure `Permissions-Policy` does not accidentally block PiP
and to set a tight CSP that still allows same-origin scripts in the floating window:

```
/*
  Permissions-Policy: picture-in-picture=*
  Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'
```

The PiP document inherits the opener's CSP; inline styles are often needed for quick
resets (hence `'unsafe-inline'` on `style-src`, or use nonces if your build supports it).

## Anti-patterns

- **Cloning instead of moving nodes.** `cloneNode(true)` duplicates elements but drops
  framework state (React fiber, Vue instance). Always move the real node.
- **Not mirroring stylesheets.** The PiP document starts blank. Without your CSS the
  floating window looks unstyled.
- **Forgetting the `pagehide` handler.** If the user closes the PiP window manually the
  node is detached and your opener UI shows a hole.
- **Opening PiP without a user gesture.** The browser will reject the promise with a
  `NotAllowedError`. Never call `requestWindow` in `useEffect` on mount.

## Gotchas

- The PiP window **cannot** be resized by the user on all platforms; pass a sensible
  initial `width`/`height`.
- `disallowReturnToOpener: true` removes the "return to tab" button in the OS chrome —
  only use it if you provide your own close affordance inside the PiP window.
- The floating window closes when the **opener tab is closed**, not just navigated.
  Persist playback position to `sessionStorage` before `beforeunload`.
- Stylesheet CORS: if your CSS is served from a different origin (CDN) set
  `crossorigin="anonymous"` on the `<link>` before appending it to the PiP document.
- TypeScript: `window.documentPictureInPicture` is not yet in `lib.dom.d.ts` for all TS
  versions. Add a local declaration file:

```typescript
// types/pip.d.ts
interface DocumentPictureInPicture {
  requestWindow(options?: { width?: number; height?: number; disallowReturnToOpener?: boolean }): Promise<Window>;
  readonly window: Window | null;
}
interface Window {
  readonly documentPictureInPicture: DocumentPictureInPicture;
}
```

## Verification

1. Open Chrome DevTools → Application → Picture-in-Picture; the floating window appears
   as a separate entry.
2. Check that clicking a button inside the PiP window fires React/Svelte handlers (state
   sync confirms the node was moved, not cloned).
3. Close the PiP window; verify the node re-attaches to the opener and the opener UI
   renders correctly.
4. Check `_headers` response in Network tab; `Permissions-Policy` must contain
   `picture-in-picture`.
5. Test with `prefers-reduced-motion: reduce` — if you use CSS transitions in the PiP
   content they should respect the media query.

## Related

- `broadcastchannel-cross-tab-coordination.md`
- `browser-share-api.md`
- `view-transitions-api-page-navigation.md`
- `pwa-service-worker-cloudflare-pages.md`
- `cloudflare-pages-headers-csp-mobile.md`

## Sources

- https://developer.chrome.com/docs/web-platform/document-picture-in-picture
- https://w3c.github.io/document-picture-in-picture/
- https://developer.mozilla.org/en-US/docs/Web/API/Document_Picture-in-Picture_API
- https://developers.cloudflare.com/pages/configuration/headers/
