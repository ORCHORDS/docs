# Local HTTPS Dev Proxy with Wrangler for WebAuthn and iOS WKWebView Testing

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

WebAuthn credential creation (`navigator.credentials.create`) silently fails on iOS
WKWebView and returns `NotAllowedError` during local development because the origin is
served over plain HTTP (`http://localhost`). WebAuthn requires a secure context
(`https://`) on all platforms. iOS Simulator additionally rejects self-signed
certificates that are not installed in the Simulator trust store, and Android Emulator
requires a proxy to route traffic from the emulator network to the host machine.

## Context

example project (example.com) implements WebAuthn passkey registration and authentication. The
Cloudflare Worker handles the WebAuthn verification RPCs (`/api/webauthn/register`,
`/api/webauthn/authenticate`). The Next.js frontend calls these endpoints.

During local development the stack runs as:

```
iOS Simulator / Android Emulator
        |
    HTTPS (port 443 / 8443)
        |
  local-https proxy (mkcert or wrangler --https)
        |
   ┌────┴──────────────────┐
   │  Next.js :3000        │  ← frontend
   │  Wrangler Worker :8787│  ← backend API
   └───────────────────────┘
```

Two approaches are documented:

1. **`wrangler dev --https`**: Wrangler's built-in TLS termination, self-signed cert
   generated automatically. Easiest for Worker-only testing.
2. **mkcert + local reverse proxy**: A locally-trusted CA cert with Caddy or `local-ssl-proxy`
   forwarding to both services. Needed when the full Next.js + Worker stack must be
   HTTPS.

Key tool versions:

| Tool            | Version  |
|-----------------|----------|
| wrangler        | 3.78.x   |
| mkcert          | 1.4.x    |
| Caddy           | 2.x      |
| local-ssl-proxy | 2.x (npm)|
| Node.js         | 20 LTS   |

## Approach 1: wrangler dev --https

Wrangler 3.78+ supports a `--https` flag that generates a self-signed certificate and
serves the Worker dev server over TLS.

```bash
pnpm wrangler dev --https --local --persist-to .wrangler/state
```

The Worker is then available at `https://localhost:8787`. Wrangler prints the
self-signed certificate fingerprint on startup.

### Trusting the cert on iOS Simulator

The iOS Simulator uses the macOS system trust store. Install the Wrangler-generated
cert into macOS Keychain:

```bash
# Wrangler stores the dev cert here
CERT_PATH="$HOME/.wrangler/local-certificate/certificate.pem"

# Add to macOS Keychain and trust for TLS
sudo security add-trusted-cert \
  -d \
  -r trustRoot \
  -k /Library/Keychains/System.keychain \
  "$CERT_PATH"
```

After installation, relaunch the iOS Simulator. Existing Simulator sessions inherit
the macOS trust store; a relaunch picks up the new cert.

Verify trust:

```bash
security verify-cert -c "$CERT_PATH" -p ssl
# Expected: ...certificate verification successful.
```

### Trusting the cert on macOS for Safari / Chrome

```bash
# Same command, already trusts for the current user
security import "$CERT_PATH" -k ~/Library/Keychains/login.keychain-db
```

## Approach 2: mkcert + local reverse proxy (recommended for Next.js + Worker)

mkcert creates a locally-trusted CA and issues certificates from it. Browsers and
simulators trust certificates signed by the local CA once the CA is installed.

### Install and configure mkcert

```bash
# macOS
brew install mkcert nss   # nss is for Firefox NSS stores

# Install the local CA into the system trust store
mkcert -install
# This also installs into iOS Simulator trust store on macOS

# Generate a cert for localhost and 127.0.0.1
mkcert localhost 127.0.0.1 ::1
# Produces: localhost+2.pem  localhost+2-key.pem
```

Move the generated files to a project-local path:

```bash
mkdir -p .local-certs
mv localhost+2.pem .local-certs/cert.pem
mv localhost+2-key.pem .local-certs/key.pem
echo ".local-certs/" >> .gitignore
```

### Reverse proxy with local-ssl-proxy (npm)

`local-ssl-proxy` is a zero-config HTTPS proxy for local dev servers.

```bash
pnpm add -Dw local-ssl-proxy
```

```json
// package.json scripts (workspace root)
{
  "scripts": {
    "dev:https": "run-p dev:worker dev:web dev:proxy",
    "dev:worker": "pnpm --filter @example project/worker wrangler dev --local --persist-to .wrangler/state",
    "dev:web": "pnpm --filter @example project/web dev",
    "dev:proxy:web": "local-ssl-proxy --source 3443 --target 3000 --cert .local-certs/cert.pem --key .local-certs/key.pem",
    "dev:proxy:worker": "local-ssl-proxy --source 8443 --target 8787 --cert .local-certs/cert.pem --key .local-certs/key.pem"
  }
}
```

This maps:
- `https://localhost:3443` → Next.js at `http://localhost:3000`
- `https://localhost:8443` → Wrangler Worker at `http://localhost:8787`

### Port mapping summary

| Service           | HTTP port | HTTPS port | Used by                  |
|-------------------|-----------|------------|--------------------------|
| Next.js           | 3000      | 3443       | Browser, iOS Simulator   |
| Wrangler Worker   | 8787      | 8443       | Next.js rewrites, mobile |
| Caddy (optional)  | —         | 443        | Single-port HTTPS entry  |

### Caddy alternative (single entry point)

If all traffic must go through port 443:

```
# Caddyfile (local dev only)
localhost {
  tls .local-certs/cert.pem .local-certs/key.pem

  handle /api/worker/* {
    reverse_proxy localhost:8787 {
      header_up Host {upstream_hostport}
    }
  }

  handle {
    reverse_proxy localhost:3000
  }
}
```

```bash
caddy run --config Caddyfile
```

The Next.js dev server and Worker are both reachable at `https://localhost/`.

## iOS Simulator Proxy Configuration

The iOS Simulator network routes through macOS. Services on `localhost` (127.0.0.1)
are reachable from the Simulator at `localhost` or `127.0.0.1` without extra proxy
setup, as long as the app uses the correct port.

For WKWebView to access `https://localhost:3443`, set the base URL in the Swift code:

```swift
let url = URL(string: "https://localhost:3443")!
let request = URLRequest(url: url)
webView.load(request)
```

If the Simulator reports SSL errors after mkcert install, reset the Simulator trust:

```bash
xcrun simctl keychain booted reset
mkcert -install   # reinstalls CA into Simulator trust store
```

Then restart the Simulator app.

## Android Emulator Proxy Configuration

The Android Emulator uses `10.0.2.2` as the host machine's loopback alias (not
`localhost`). The HTTPS proxy must bind to `0.0.0.0` and the cert must include a SAN
for `10.0.2.2`.

### Generate a cert with Android SAN

```bash
mkcert localhost 127.0.0.1 ::1 10.0.2.2
mv localhost+3.pem .local-certs/cert.pem
mv localhost+3-key.pem .local-certs/key.pem
```

### Install mkcert CA on Android Emulator

```bash
# Export the mkcert root CA
CAROOT=$(mkcert -CAROOT)
cp "$CAROOT/rootCA.pem" ./rootCA.pem

# Push to Android emulator (requires running emulator and adb)
adb root
adb push rootCA.pem /data/local/tmp/rootCA.pem

# Convert to DER format and install as system CA (API 29+ requires system partition)
adb shell "openssl x509 -in /data/local/tmp/rootCA.pem -inform PEM -out /data/local/tmp/rootCA.der -outform DER"
adb shell "su 0 mv /data/local/tmp/rootCA.der /system/etc/security/cacerts/$(openssl x509 -inform DER -subject_hash_old -in /data/local/tmp/rootCA.der | head -1).0"
adb shell "su 0 chmod 644 /system/etc/security/cacerts/$(ls /system/etc/security/cacerts/ | tail -1)"
adb reboot
```

This works only on emulators with writable `/system` (use `-writable-system` flag when
starting the AVD):

```bash
emulator -avd Pixel_8_API_35 -writable-system
```

### Android WebView URL

In the Android app, set the WebView URL to use the host alias:

```kotlin
webView.loadUrl("https://10.0.2.2:3443")
```

## WebAuthn rpId Configuration

The WebAuthn Relying Party ID must match the HTTPS origin exactly. Update the Worker
and frontend for local dev:

```typescript
// packages/worker/src/webauthn.ts
const RP_ID = process.env.NODE_ENV === "production"
  ? "example.com"
  : "localhost";

const RP_ORIGIN = process.env.NODE_ENV === "production"
  ? "https://example.com"
  : "https://localhost:3443";
```

The `.dev.vars` for local dev:

```
RP_ID=localhost
RP_ORIGIN=https://localhost:3443
```

## Anti-patterns

- **Using plain HTTP and trusting `--disable-web-security` in the browser**: this
  bypasses all browser security checks, masks real-world bugs, and is not available
  in WKWebView or Android WebView at all.
- **Regenerating the mkcert CA on every developer's machine**: the CA is per-machine.
  Each developer must run `mkcert -install` themselves. Do not commit the CA private key.
- **Putting `localhost` in the WebAuthn `allowCredentials` domain without HTTPS**: even
  if WebAuthn allows `localhost` without TLS in some browser builds, iOS WKWebView and
  Android WebView do not. Always use HTTPS.
- **Forgetting to add `10.0.2.2` to the mkcert SAN list**: a cert without the
  Android emulator host SAN causes `ERR_CERT_COMMON_NAME_INVALID` on Android.

## Gotchas

- **mkcert `-install` on macOS requires sudo for the system keychain**: a user-only
  install (no sudo) works for browsers but not for the iOS Simulator system trust store.
- **Rebooting the iOS Simulator is required after cert installation**: the trust store
  is read at boot. A `simctl shutdown all && simctl boot` is sufficient.
- **Wrangler `--https` self-signed cert is ephemeral**: it is regenerated on each
  `wrangler dev` restart. The iOS Simulator trust step must be repeated each time
  unless you switch to mkcert (which issues a stable cert from a persistent CA).
- **Node.js does not trust mkcert CA by default**: when the Worker or Node.js test
  runner makes `fetch()` calls to the HTTPS proxy, add the CA to `NODE_EXTRA_CA_CERTS`:

```bash
CAROOT=$(mkcert -CAROOT)
export NODE_EXTRA_CA_CERTS="$CAROOT/rootCA.pem"
pnpm wrangler dev --local
```

- **Chrome on Android uses the OS trust store**: if the mkcert CA is installed at the
  system level, Chrome trusts it. Firefox on Android uses its own cert store — install
  the CA via Firefox's certificate manager settings.

## Verification

```bash
# 1. Confirm mkcert CA is installed
mkcert -CAROOT
ls "$(mkcert -CAROOT)"
# Expected: rootCA.pem  rootCA-key.pem

# 2. Confirm cert covers required SANs
openssl x509 -in .local-certs/cert.pem -text -noout | grep -A5 "Subject Alternative Name"
# Expected: DNS:localhost, IP Address:127.0.0.1, IP Address:::1, IP Address:10.0.2.2

# 3. Test HTTPS Worker
curl --cacert "$(mkcert -CAROOT)/rootCA.pem" https://localhost:8443/health
# Expected: HTTP 200

# 4. Test HTTPS Next.js
curl --cacert "$(mkcert -CAROOT)/rootCA.pem" https://localhost:3443/
# Expected: HTTP 200 with HTML

# 5. Confirm WebAuthn context (browser console)
# Open https://localhost:3443 in Safari > Developer Console:
# window.isSecureContext
# Expected: true
```

## Related

- `local-https-mkcert.md` — mkcert fundamentals without the Worker context
- `cloudflare-tunnel-dev.md` — expose local dev server to real iOS devices over internet
- `wrangler-dev-local-d1-r2-testing.md` — local Worker development with D1 + R2
- `remote-debugging-mobile-web.md` — Safari inspector and Chrome remote DevTools
- `charles-proxy-debugging.md` — intercepting HTTPS traffic from mobile devices

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://github.com/FiloSottile/mkcert
- https://web.dev/articles/webauthn-discoverable-credentials
- https://developer.apple.com/documentation/webkit/wkwebview
- https://developer.android.com/studio/run/emulator-networking
