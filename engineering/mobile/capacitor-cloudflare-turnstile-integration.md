# Capacitor Cloudflare Turnstile Integration

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Cloudflare Turnstile widget fails to render or execute inside a Capacitor WKWebView (iOS) or
Android WebView. The `turnstile.render()` callback never fires. On iOS, attempting to open the
Turnstile challenge in `SFSafariViewController` causes a blank page or missing JS bridge. Tokens
minted by the widget expire before the Worker can verify them (default 300 s) on slow mobile
networks. The injected JS bridge for non-interactive mode silently fails on iOS 16.

## Context

example project uses Turnstile as the anonymous-user bot gate for post creation and account initialisation
flows. In Capacitor, the WebView is a first-party in-app browser — not a full Safari instance —
which means several Turnstile assumptions break: the `window.turnstile` object must be loaded via
injected HTML, `SFSafariViewController` is unavailable from inside WKWebView, and the standard
script CDN call is blocked by the app's CSP.

## Turnstile Widget Type Selection

```
+---------------------+-------------------+---------------------------------------+
| Widget type         | User interaction  | Capacitor/WebView suitability         |
+---------------------+-------------------+---------------------------------------+
| managed (default)   | May show checkbox | Works in WKWebView if JS injected     |
| non-interactive     | None              | Best for Capacitor — silent challenge |
| invisible           | None              | Preferred; requires site allowlisting |
+---------------------+-------------------+---------------------------------------+
```

Request `invisible` or `non-interactive` in the Cloudflare dashboard for the example project app sitekey.
This avoids the checkbox UI that requires precise tap coordinates in scaled WebViews.

## iOS WKWebView: Injected JS Bridge

WKWebView blocks `<script src="https://...">` tags that weren't pre-authorised in a CSP. Inject the
Turnstile script at WebView load time via `WKUserScript`:

```swift
// ios/App/TurnstileBridge.swift
import WebKit

class TurnstileBridge: NSObject, WKScriptMessageHandler {
    weak var webView: WKWebView?

    func setup(webView: WKWebView) {
        self.webView = webView
        let config = webView.configuration

        // Inject Turnstile script before document load
        let script = WKUserScript(
            source: turnstileLoaderScript(),
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        )
        config.userContentController.addUserScript(script)

        // Message handler receives the token from JS
        config.userContentController.add(self, name: "turnstileToken")
        config.userContentController.add(self, name: "turnstileError")
    }

    private func turnstileLoaderScript() -> String {
        return """
        (function() {
          var s = document.createElement('script');
          s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=_tsOnLoad&render=explicit';
          s.async = true;
          s.defer = true;
          document.head.appendChild(s);

          window._tsOnLoad = function() {
            var container = document.getElementById('cf-turnstile');
            if (!container) return;
            turnstile.render(container, {
              sitekey: '\(TurnstileConfig.sitekey)',
              theme: 'dark',
              callback: function(token) {
                webkit.messageHandlers.turnstileToken.postMessage(token);
              },
              'error-callback': function(code) {
                webkit.messageHandlers.turnstileError.postMessage(code);
              }
            });
          };
        })();
        """
    }

    // WKScriptMessageHandler
    func userContentController(
        _ controller: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        switch message.name {
        case "turnstileToken":
            guard let token = message.body as? String else { return }
            NotificationCenter.default.post(
                name: .turnstileTokenReceived,
                object: token
            )
        case "turnstileError":
            // Handle Turnstile error — show retry UI
            break
        default: break
        }
    }
}

extension Notification.Name {
    static let turnstileTokenReceived = Notification.Name("TurnstileTokenReceived")
}
```

## Android WebView: Script Injection via Capacitor Plugin

```typescript
// android/app/src/main/java/app/example project/example project/TurnstilePlugin.java
package app.example project.example project;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "Turnstile")
public class TurnstilePlugin extends Plugin {

    @PluginMethod
    public void getToken(PluginCall call) {
        // Evaluate JS in the WebView to trigger Turnstile and get the token
        getBridge().getWebView().evaluateJavascript(
            "window.turnstile ? turnstile.getResponse() : null",
            value -> {
                if (value != null && !value.equals("null")) {
                    call.resolve(new com.getcapacitor.JSObject().put("token", value.replace("\"", "")));
                } else {
                    call.reject("No Turnstile token available");
                }
            }
        );
    }
}
```

TypeScript side of the Capacitor plugin:

```typescript
// src/plugins/turnstile.ts
import { registerPlugin } from "@capacitor/core";

export interface TurnstilePlugin {
  getToken(): Promise<{ token: string }>;
}

export const Turnstile = registerPlugin<TurnstilePlugin>("Turnstile");
```

## React Component: Turnstile Widget in Capacitor WebView

```tsx
// src/components/TurnstileWidget.tsx
import React, { useEffect, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { Turnstile } from "../plugins/turnstile";

interface Props {
  onToken: (token: string) => void;
  onError?: (code: string) => void;
}

export function TurnstileWidget({ onToken, onError }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [rendered, setRendered] = useState(false);

  useEffect(() => {
    if (!containerRef.current || rendered) return;

    const isNative = Capacitor.isNativePlatform();

    if (isNative) {
      // Token is pushed via native bridge on iOS; use polling on Android
      if (Capacitor.getPlatform() === "android") {
        const poll = setInterval(async () => {
          try {
            const { token } = await Turnstile.getToken();
            if (token) {
              clearInterval(poll);
              onToken(token);
            }
          } catch {}
        }, 500);
        return () => clearInterval(poll);
      } else {
        // iOS: listen for native notification
        const handler = (event: CustomEvent<string>) => onToken(event.detail);
        window.addEventListener("turnstile:token" as any, handler);
        return () => window.removeEventListener("turnstile:token" as any, handler);
      }
    } else {
      // Web / PWA: use standard Turnstile JS API
      if (typeof window.turnstile !== "undefined") {
        window.turnstile.render(containerRef.current, {
          sitekey: process.env.EXPO_PUBLIC_TURNSTILE_SITEKEY!,
          theme: "dark",
          callback: onToken,
          "error-callback": onError,
        });
        setRendered(true);
      }
    }
  }, [onToken, onError, rendered]);

  return <div id="cf-turnstile" ref={containerRef} />;
}
```

## Worker: Token Verification with TTL Extension

```typescript
// worker/src/auth/turnstile.ts
const VERIFY_ENDPOINT =
  "https://challenges.cloudflare.com/turnstile/v0/siteverify";

export async function verifyTurnstileToken(
  token: string,
  env: Env,
  remoteIp?: string
): Promise<{ success: boolean; errorCodes: string[] }> {
  const body = new FormData();
  body.append("secret", env.TURNSTILE_SECRET_KEY);
  body.append("response", token);
  if (remoteIp) body.append("remoteip", remoteIp);

  const res = await fetch(VERIFY_ENDPOINT, { method: "POST", body });
  const result = await res.json<{
    success: boolean;
    "error-codes": string[];
    challenge_ts: string;
  }>();

  if (!result.success) {
    return { success: false, errorCodes: result["error-codes"] };
  }

  // Token lifetime is 300s; check challenge timestamp for slow mobile connections
  const challengeAge =
    Date.now() - new Date(result.challenge_ts).getTime();
  if (challengeAge > 270_000) {
    // Within 30 s of expiry — log but accept; client should refresh soon
    console.warn(`Turnstile token near expiry: ${challengeAge}ms old`);
  }

  return { success: true, errorCodes: [] };
}
```

## Token Lifetime vs Mobile Network Latency

```
+---------------------------+------------------+------------------------------+
| Scenario                  | Challenge age    | Recommendation               |
+---------------------------+------------------+------------------------------+
| Wi-Fi, fast submission    | < 10 s           | Verify immediately           |
| LTE, normal usage         | 10–120 s         | Verify; token valid          |
| Slow 3G or CGNAT          | 120–270 s        | Verify; log warning          |
| Network switch mid-flow   | 270–300 s        | Accept + prompt re-challenge |
| Offline queue flush       | > 300 s          | REJECT; re-challenge required|
+---------------------------+------------------+------------------------------+
```

## SFSafariViewController vs WKWebView

`SFSafariViewController` cannot be spawned from inside a WKWebView (Capacitor shell) — iOS
sandboxes the view hierarchy. Turnstile's interactive challenge does NOT open an external browser;
it runs inside the existing WKWebView via an iframe. Do NOT attempt to detect and redirect to
`SFSafariViewController` for Turnstile — use the `non-interactive` or `invisible` widget type and
the WKUserScript injection pattern above.

## Anti-patterns

- Loading `https://challenges.cloudflare.com/turnstile/v0/api.js` via a `<script>` tag in the
  HTML bundle — blocked by WKWebView CSP unless the origin is explicitly whitelisted.
- Using `SameSite=Strict` on the Turnstile verification result cookie — Turnstile's own iframe
  post-message flow treats the result as cross-site and the cookie is stripped.
- Storing the Turnstile token in AsyncStorage and replaying it after a network switch — tokens
  expire at 300 s from challenge issuance, not from submission.
- Calling `turnstile.reset()` inside the WKUserScript injection without first checking that
  `window.turnstile` exists — throws a ReferenceError that silently kills the injection.
- Passing `execution: 'execute'` mode without also handling the `before-interactive-callback` —
  the widget enters an indefinite "processing" state on iOS if the callback is absent.

## Gotchas

- WKWebView on iOS 16 ignores `WKUserScript` injected at `atDocumentStart` for cross-origin
  iframes; the Turnstile iframe receives the injected token handler but cannot post back across
  the frame boundary. Use `postMessage` interception at the main frame level instead.
- Cloudflare Turnstile `non-interactive` mode still loads ~250 KB of JS; pre-warm by injecting
  the script on app start, not at form display time.
- The `sitekey` for the iOS app should be a separate Turnstile site with allowed domains set to
  `*` (since Capacitor apps do not have a real domain). Set allowed hostnames to `localhost` or
  your Capacitor custom scheme in the Turnstile dashboard.
- Android WebView before Chromium 124 may block `challenges.cloudflare.com` if the app's
  `network_security_config.xml` restricts cleartext traffic — ensure the config allows HTTPS to
  Cloudflare endpoints.
- Turnstile `error-callback` with code `110200` means the sitekey domain does not match; always
  add `capacitor://localhost` and `http://localhost` to the Turnstile site's allowed domains.

## Verification

```bash
# Test token verification directly against Cloudflare
curl -s https://challenges.cloudflare.com/turnstile/v0/siteverify \
  -F secret="${TURNSTILE_SECRET_KEY}" \
  -F response="${TOKEN_FROM_WIDGET}" | jq .

# Confirm WKUserScript injection fired (via Safari Web Inspector on iOS)
# Open Safari > Develop > Simulator > App WebView > Console
# Should see: "[Turnstile] script injected" if you log in the script

# Android: check WebView console via chrome://inspect
# Navigate to the post-creation flow and confirm cf-turnstile div is rendered
```

## Related

- `react-native-cloudflare-turnstile-integration.md`
- `capacitor-native-bridge-plugin-development.md`
- `mobile-safari-itp-cookie-partitioning.md`
- `webview-security.md`
- `mobile-auth-oauth-pkce.md`

## Sources

- https://developers.cloudflare.com/turnstile/
- https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/
- https://developer.apple.com/documentation/webkit/wkuserscript
- https://developer.apple.com/documentation/webkit/wkscriptmessagehandler
- https://capacitorjs.com/docs/plugins/creating-plugins
