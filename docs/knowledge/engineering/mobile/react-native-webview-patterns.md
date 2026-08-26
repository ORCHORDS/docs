# react-native-webview-patterns

**Issue:** Embedding web content in React Native and communicating between JS bridge and web page
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The deprecated built-in WebView was removed in RN 0.60; apps using `react-native-webview` need bidirectional message passing and security hardening.

## Pattern / Solution
```sh
npm install react-native-webview
npx pod-install
```

```jsx
import { useRef } from 'react';
import { WebView } from 'react-native-webview';

const webviewRef = useRef(null);

// Send message TO web page
webviewRef.current.postMessage(JSON.stringify({ type: 'TOKEN', value: token }));

// Receive message FROM web page
function onMessage(event) {
  const data = JSON.parse(event.nativeEvent.data);
  if (data.type === 'NAVIGATE') navigation.navigate(data.route);
}

<WebView
  ref={webviewRef}
  source={{ uri: 'https://app.example.com' }}
  onMessage={onMessage}
  // inject JS into loaded page
  injectedJavaScript={`
    window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'READY' }));
  `}
  javaScriptEnabled
  domStorageEnabled
  originWhitelist={['https://app.example.com']}
/>
```

## Gotchas
- `injectedJavaScript` must end with `true;` in older versions or it silently fails
- `originWhitelist` defaults to `['*']` — restrict it to your domain to prevent open redirect attacks
- Avoid `allowFileAccess` + `allowUniversalAccessFromFileURLs` together — allows XSS via `file://`
- `onShouldStartLoadWithRequest` runs on every navigation; return `false` to block third-party URLs

## Related
- `webview-security.md`
- `mobile-network-resilience.md`
