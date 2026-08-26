# React Native Cloudflare Turnstile Integration

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

example project requires Cloudflare Turnstile to gate anonymous
post creation and voting, preventing bot-driven content
manipulation. The Turnstile widget renders inside a
WebView in React Native. On iOS, the widget loads but the
token callback is never fired. On Android, the invisible
widget silently fails on first render and requires a
manual retry. After a Turnstile challenge failure (user
interaction required), the token is invalid but the app
still sends it to the Worker, receiving a 403 in response.

## Context

Cloudflare Turnstile is a CAPTCHA alternative that runs
a JavaScript widget. In React Native there is no DOM, so
Turnstile must render inside `react-native-webview`. The
widget posts the solved token via a JavaScript callback;
the token is then extracted via `WebView.onMessage` and
sent to a Cloudflare Worker for server-side verification.
Turnstile tokens expire after 5 minutes and are
single-use — failed Worker verification invalidates them.

---

## 1. Widget Mode Comparison

```
┌─────────────────────────────────────────────────────────────┐
│ Mode       │ UX         │ Solve time │ Best for example project    │
│────────────│────────────│────────────│──────────────────────│
│ Managed    │ Checkbox   │ ~1–3 s     │ Post creation (seen) │
│            │ or nonce   │            │ - user expects check │
│ Invisible  │ None       │ ~0.5–2 s   │ Vote / like flows    │
│            │            │            │ - no UX friction     │
│ Non-intr.  │ None       │ ~0.1–0.5 s │ Background sessions  │
│ (explicit) │            │            │ - programmatic only  │
└─────────────────────────────────────────────────────────────┘
```

Use managed mode when the user consciously submits a form.
Use invisible mode for ambient actions (vote, follow) where
a visible challenge would feel jarring.

---

## 2. WebView HTML Harness

Create a minimal HTML page that hosts the Turnstile widget
and uses `window.ReactNativeWebView.postMessage` to send
the token back:

```ts
// src/turnstile/turnstileHtml.ts

export function buildTurnstileHtml(opts: {
  siteKey: string;
  mode:    'managed' | 'invisible' | 'non-interactive';
  theme?:  'light' | 'dark' | 'auto';
}): string {
  const { siteKey, mode, theme = 'auto' } = opts;

  return `<!DOCTYPE html>
<html>
<head>
  <meta name="viewport"
    content="width=device-width, initial-scale=1.0">
  <style>
    body { margin: 0; background: transparent; }
    #widget { display: flex; justify-content: center;
               padding-top: 8px; }
  </style>
</head>
<body>
  <div id="widget"></div>
  <script src=
    "https://challenges.cloudflare.com/turnstile/v0/api.js"
    async defer></script>
  <script>
    function onTurnstileSuccess(token) {
      window.ReactNativeWebView.postMessage(
        JSON.stringify({ type: 'TURNSTILE_TOKEN', token })
      );
    }
    function onTurnstileError(code) {
      window.ReactNativeWebView.postMessage(
        JSON.stringify({ type: 'TURNSTILE_ERROR', code })
      );
    }
    function onTurnstileExpired() {
      window.ReactNativeWebView.postMessage(
        JSON.stringify({ type: 'TURNSTILE_EXPIRED' })
      );
    }
    window.addEventListener('load', () => {
      if (window.turnstile) {
        window.turnstile.render('#widget', {
          sitekey:  '${siteKey}',
          callback: onTurnstileSuccess,
          'error-callback':   onTurnstileError,
          'expired-callback': onTurnstileExpired,
          execution: '${mode === 'managed' ? 'render' : 'execute'}',
          appearance:'${mode === 'managed' ? 'always' : 'interaction-only'}',
          theme: '${theme}',
        });
        ${mode === 'invisible' || mode === 'non-interactive'
          ? "window.turnstile.execute('#widget');" : ''}
      }
    });
  </script>
</body>
</html>`;
}
```

---

## 3. React Native Component

```tsx
// src/turnstile/TurnstileView.tsx
import React, { useRef, useState, useCallback } from 'react';
import { View, StyleSheet } from 'react-native';
import WebView, { WebViewMessageEvent }
  from 'react-native-webview';
import { buildTurnstileHtml } from './turnstileHtml';
import { TURNSTILE_SITE_KEY } from '../config/env';

interface Props {
  mode?:   'managed' | 'invisible' | 'non-interactive';
  theme?:  'light' | 'dark' | 'auto';
  onToken: (token: string) => void;
  onError: (code: string) => void;
}

export function TurnstileView({
  mode    = 'invisible',
  theme   = 'auto',
  onToken,
  onError,
}: Props) {
  const webRef = useRef<WebView>(null);
  const [height, setHeight] = useState(
    mode === 'managed' ? 65 : 1
  );

  const html = buildTurnstileHtml({
    siteKey: TURNSTILE_SITE_KEY,
    mode,
    theme,
  });

  const onMessage = useCallback((e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data);
      if (msg.type === 'TURNSTILE_TOKEN') {
        onToken(msg.token);
      } else if (msg.type === 'TURNSTILE_ERROR') {
        onError(msg.code ?? 'unknown');
      } else if (msg.type === 'TURNSTILE_EXPIRED') {
        // Widget will auto-refresh; wait for new token
        onError('expired');
      }
    } catch {
      onError('parse_error');
    }
  }, [onToken, onError]);

  return (
    <View style={[styles.container, { height }]}>
      <WebView
        ref={webRef}
        source={{ html }}
        originWhitelist={['*']}
        onMessage={onMessage}
        javaScriptEnabled
        // iOS: required for postMessage to work
        allowsInlineMediaPlayback
        // Android: required for Turnstile JS
        domStorageEnabled
        // Prevent scroll bounce on the widget
        scrollEnabled={false}
        bounces={false}
        style={styles.webview}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { width: '100%', overflow: 'hidden' },
  webview:   { backgroundColor: 'transparent' },
});
```

---

## 4. Passing the Token to a Cloudflare Worker

```ts
// src/api/createPost.ts
import { fetchWithBackoff } from '../network/fetchWithBackoff';

export async function createPost(opts: {
  body:          string;
  turnstileToken: string;
}): Promise<{ postId: string }> {
  return fetchWithBackoff(
    'https://api.example.com/v1/posts',
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        body:             opts.body,
        'cf-turnstile-response': opts.turnstileToken,
      }),
    },
    { maxAttempts: 1 }  // Do NOT retry — token is single-use
  );
}
```

Worker-side verification:

```ts
// workers/src/middleware/turnstile.ts
export async function verifyTurnstile(
  token: string,
  ip:    string,
  env:   { TURNSTILE_SECRET: string }
): Promise<boolean> {
  const form = new FormData();
  form.append('secret',   env.TURNSTILE_SECRET);
  form.append('response', token);
  form.append('remoteip', ip);

  const res  = await fetch(
    'https://challenges.cloudflare.com/turnstile/v0/siteverify',
    { method: 'POST', body: form }
  );
  const data = await res.json<{ success: boolean }>();
  return data.success;
}
```

---

## 5. iOS vs Android WebView Quirks

```
┌────────────────────────────────────────────────────────────┐
│ Quirk                  │ iOS (WKWebView) │ Android WebView │
│────────────────────────│─────────────────│─────────────────│
│ postMessage delivery   │ Needs           │ Works OOTB      │
│                        │ allowsInline    │                 │
│                        │ MediaPlayback   │                 │
│ Transparent background │ Set             │ Set             │
│                        │ backgroundColor │ setBackground   │
│                        │ clear in Swift  │ Color(0x00…)    │
│ JS injection timing    │ After DOMContent│ After load      │
│                        │ Loaded event    │ event           │
│ localStorage           │ Wiped on low    │ Persistent      │
│                        │ memory warning  │                 │
│ Third-party cookies    │ Blocked by ITP  │ Blocked on ≥15  │
│ (Turnstile internal)   │                 │                 │
└────────────────────────────────────────────────────────────┘
```

On iOS, if `window.ReactNativeWebView` is undefined in the
Turnstile callback, the `onMessage` event is not wired.
Ensure `source={{ html }}` not `source={{ uri }}` — remote
URIs lose the injected `ReactNativeWebView` bridge.

---

## 6. Turnstile Refresh on Challenge Failure

When Turnstile issues a challenge (interactive checkbox)
and the user fails or the token expires, reset the widget:

```tsx
// In the TurnstileView component's onError handler:
const onError = useCallback((code: string) => {
  if (code === 'expired' || code === '110200') {
    // 110200 = interactive challenge failed
    webRef.current?.injectJavaScript(`
      if (window.turnstile) {
        window.turnstile.reset();
        window.turnstile.execute('#widget');
      }
      true;
    `);
  }
  parentOnError(code);
}, [parentOnError]);
```

Avoid auto-retrying more than 3 times without user
interaction — Cloudflare may escalate the challenge mode.

---

## Anti-patterns

- Retrying the API call with the same Turnstile token
  after a 403. Tokens are single-use; the retry will also
  fail. Re-render the widget to get a fresh token.
- Using `source={{ uri }}` pointing to a hosted HTML file
  for the WebView. The `ReactNativeWebView` message bridge
  is injected only into inline HTML; remote URIs require
  `injectedJavaScript` to manually add the bridge.
- Logging or caching Turnstile tokens for debugging. They
  are credentials; treat them as such.
- Using the same Turnstile site key for sandbox and
  production. Cloudflare provides dedicated test keys for
  CI environments (`1x00000000000000000000AA` always passes;
  `2x00000000000000000000AB` always blocks).

## Gotchas

- The Turnstile JS bundle (~100 kB) is loaded from
  `challenges.cloudflare.com`. If the device is offline
  during widget load, the WebView renders blank and no
  error callback fires. Add a `onError` handler on the
  WebView itself to catch navigation failures.
- On Android WebView < Chromium 87, the Turnstile widget
  may render but the invisible mode solve never completes.
  Update the minimum WebView version requirement in your
  Play Store listing to Chromium 87+ (ships with Android
  9 devices updated after 2021).
- Turnstile tokens returned from `siteverify` include an
  `error-codes` array even on success for partial signals.
  Only check the `success` boolean for pass/fail.

## Verification

```bash
# Use Cloudflare's always-pass test site key in CI
TURNSTILE_SITE_KEY=1x00000000000000000000AA
TURNSTILE_SECRET=1x0000000000000000000000000000000AA

# Verify a test token
curl -X POST \
  https://challenges.cloudflare.com/turnstile/v0/siteverify \
  -F "secret=$TURNSTILE_SECRET" \
  -F "response=XXXX.DUMMY.TOKEN.XXXX"
# Expected: {"success":true,"error-codes":[]}
```

## Related

- `react-native-webview-patterns.md`
- `webview-security.md`
- `ios-wkwebview-cloudflare-cookies.md`
- `android-webview-cloudflare-security-headers.md`
- `mobile-auth-oauth-pkce.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/turnstile/
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://developers.cloudflare.com/turnstile/reference/testing/
- https://github.com/react-native-webview/react-native-webview
- https://developers.cloudflare.com/turnstile/concepts/widget-types/
