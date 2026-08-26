# Remote Debugging Mobile & Remote Web (Chrome DevTools, Safari, Flipper)

> Inspecting web content running on a phone, in a WebView, or on a remote
> machine — where the page is not in your local browser. Essential for
> Capacitor/Cordova hybrid apps, mobile Safari, and embedded WebViews.

---

## When to use this

- Debugging a Capacitor/Cordova app's web layer on a physical Android or iOS device.
- A bug only reproduces on mobile Safari (iOS) but not desktop Chrome.
- Inspecting a page served from a remote machine (staging box, dev board, IoT).
- A third-party WebView (Facebook in-app browser, WeChat) renders differently.

## Symptom

"The page works on my laptop but is broken on the phone" — and `console.log`
output from the device is invisible because there's no devtools window attached
to the device's browser.

## Android (Chrome / WebView / Capacitor)

### 1. Enable USB debugging on the device

Settings → About phone → tap Build number 7× → Developer options → enable
USB debugging. Plug in, authorize the host on the prompt.

### 2. Forward and inspect

```bash
# Verify device is visible
adb devices

# Chrome / system WebView pages
adb forward tcp:9222 localabstract:webview_devtools_remote_*
# Then open chrome://inspect in desktop Chrome → "Configure..." → add localhost:9222
```

For Capacitor apps the WebView shows up under `chrome://inspect` once
`WebView.setWebContentsDebuggingEnabled(true)` is set in `MainActivity` (it's
on by default in debug builds, off in release — a frequent source of confusion).

### 3. Read device logs alongside the web console

```bash
adb logcat -v time | grep -iE "chromium|console|capacitor"
```

JS `console.log` from the WebView is mirrored to logcat tagged `chromium` or
`Console`. Don't forget to also watch the native side (`adb logcat | grep -i
capacitor`) — many "JS bugs" are actually native plugin errors.

## iOS (Safari / WKWebView)

### 1. Enable Web Inspector on the device

Settings → Safari → Advanced → Web Inspector ON. Plug in over USB, trust
the computer.

### 2. Connect from macOS Safari

Safari → Develop menu → [Your iPhone] → [Page title].

If the Develop menu is missing: Safari → Settings → Advanced → Show features
for web developers.

### 3. WKWebView in a Capacitor/Cordova app

WKWebView debuggability follows Safari's setting in debug builds. In release
builds it's disabled — there is no runtime toggle (unlike Android). To debug a
TestFlight build you must ship a debug-config build.

## Remote page (not on a phone, just on another machine)

### Option A: SSH port-forward + Chrome

```bash
ssh -L 9222:localhost:9222 user@remote-host
# On the remote, launch Chrome with:
#   chrome --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0
# Then visit chrome://inspect on your laptop → Configure → localhost:9222
```

### Option B: `chrome://inspect` over the network

Only works if `--remote-debugging-address=0.0.0.0` was set AND the port is
reachable. Chrome blocks remote debugging on non-loopback by default for
security — do not leave this on in production.

## Gotchas

- **`chrome://inspect` shows nothing**: 90% of the time `adb forward` wasn't run,
  the port was wrong, or the app's WebView debugging is disabled. Check
  `adb shell cat /proc/net/unix | grep webview` to confirm a devtools socket exists.
- **iOS 17+ cable trust expires**: re-trust periodically; the device silently
  disappears from Safari's Develop menu. Replug and re-approve.
- **Service Worker / Workbox invisibility**: SW state on the device doesn't
  reflect desktop. Use `chrome://inspect/#service-workers` (Android) or
  Safari's Storage tab to unregister a stuck SW that desktop hard-refresh can't fix.
- **In-app browsers (Instagram, Facebook, WeChat, LinkedIn)**: these use the
  system WebView but block remote inspection entirely. Use a User-Agent switcher
  in desktop Chrome to reproduce; debugging the live in-app session is usually
  impossible without a jailbreak.
- **Source maps over USB are slow**: the device re-fetches the source map from
  its own origin, not your laptop's. If your staging bundle points at
  `localhost:xxxx` for maps, the device can't resolve it. Upload maps to the
  same origin as the bundle, or use a sentry-style symbolication pipeline.
- **Cookies / localStorage divergence**: third-party cookie blocking is stricter
  on iOS Safari than desktop. A login that "just works" on desktop can fail in
  WKWebView because of ITP. Inspect via Storage tab, not Network tab.
- **`vConsole` / `eruda` as a fallback**: when remote inspection isn't possible
  (in-app browsers, customer devices), inject a floating in-page console.
  They can't set breakpoints but they surface `console.*` and XHRs.
- **Flipper (React Native / native)**: for RN apps, Flipper is the equivalent
  tool — network inspector, layout inspector, AsyncStorage browser. It coexists
  with Chrome DevTools for the JS bridge but is the only way to inspect native
  layout.
- **WebSocket frames missing**: Chrome's Network tab only shows WS frames while
  the panel is OPEN. Open the WS connection after opening the panel, or you'll
  see zero frames.

## Quick triage checklist

- [ ] Device visible to `adb devices` / appearing in Safari Develop menu?
- [ ] WebView debugging enabled (Android) / debug build (iOS)?
- [ ] `adb forward` running for the right socket name?
- [ ] Source maps reachable from the device's network, not just your laptop?
- [ ] Native logs (`adb logcat` / Console.app) checked for non-JS errors?

## See also

- `chrome-devtools-2026.md` — desktop DevTools features
- `charles-proxy-debugging.md` — intercept mobile HTTPS traffic
- `vscode-remote-containers.md` — debugging code on a remote dev box
