# android-network-security-config

**Issue:** Android network_security_config.xml — cleartext, cert pinning, Play Store requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom
Your Android app is rejected from Google Play with:
> "Your app transmits data in cleartext (unencrypted HTTP) to
> [domain]. This practice leaves users vulnerable to eavesdropping."
Or: your debug certificate pin works but the production pin fails
after a cert rotation and users can't log in.

## Root cause
**Android 9+ blocks cleartext (HTTP) traffic by default**, but older
Capacitor/React Native templates override this with
`android:usesCleartextTraffic="true"` in `AndroidManifest.xml` or a
permissive `network_security_config.xml`. Google Play Protect scans
for this and flags it.

**Source:** Android Network Security Configuration:
https://developer.android.com/training/articles/security-config

**Source:** Google Play — Prominent Disclosure requirements:
https://support.google.com/googleplay/android-developer/answer/9888076

## Minimal production config (no cleartext)

```xml
<!-- android/app/src/main/res/xml/network_security_config.xml -->
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>

  <!-- Base config: deny cleartext everywhere -->
  <base-config cleartextTrafficPermitted="false">
    <trust-anchors>
      <!-- Trust system CAs only (default) -->
      <certificates />
    </trust-anchors>
  </base-config>

  <!-- Production API: pin the certificate -->
  <domain-config cleartextTrafficPermitted="false">
    <domain includeSubdomains="false">api.example.com</domain>
    <pin-set expiration="2027-01-01">
      <!-- SPKI SHA-256 of current cert -->
      <pin digest="SHA-256">BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=</pin>
      <!-- Backup pin — must have at least one backup -->
      <pin digest="SHA-256">AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=</pin>
    </pin-set>
  </domain-config>

</network-security-config>
```

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<application
  android:networkSecurityConfig="@xml/network_security_config"
  android:usesCleartextTraffic="false"
  ...>
```

**Do not** set `android:usesCleartextTraffic="true"` at the
application level. If a specific domain needs it, use
`<domain-config cleartextTrafficPermitted="true">` for that domain
only and document why.

## Debug vs release config split

During development you may need to trust user-installed CA
certificates (for Proxyman / Charles Proxy). Do NOT ship this in
production.

```xml
<!-- android/app/src/main/res/xml/network_security_config.xml (production) -->
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <base-config cleartextTrafficPermitted="false">
    <trust-anchors>
      <certificates />
    </trust-anchors>
  </base-config>
  <domain-config cleartextTrafficPermitted="false">
    <domain includeSubdomains="false">api.example.com</domain>
    <pin-set expiration="2027-01-01">
      <pin digest="SHA-256">BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=</pin>
      <pin digest="SHA-256">AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=</pin>
    </pin-set>
  </domain-config>
</network-security-config>
```

```xml
<!-- android/app/src/debug/res/xml/network_security_config.xml (debug only) -->
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <base-config cleartextTrafficPermitted="false">
    <trust-anchors>
      <certificates />
      <!-- Trust user-installed certs in DEBUG ONLY for proxying -->
      <certificates />
    </trust-anchors>
  </base-config>
  <!-- No pin-set in debug — allows proxy cert -->
</network-security-config>
```

Android build system automatically picks `src/debug/` vs `src/main/`
based on the build variant. The production APK/AAB never includes the
debug config.

## Verifying the config is active

```bash
# Check AndroidManifest for networkSecurityConfig attribute
grep -r "networkSecurityConfig" android/app/src/main/AndroidManifest.xml

# Check no cleartext override at application level
grep "usesCleartextTraffic" android/app/src/main/AndroidManifest.xml
# Should output: android:usesCleartextTraffic="false"
# OR: no output (false is the default on API 28+)

# Decompile the release APK and check the merged manifest
# bundletool dump manifest --bundle=app.aab
```

## Play Store requirements (2024+)

Google Play now automatically rejects APKs that:
1. Set `cleartextTrafficPermitted="true"` globally without a
   `<domain-config>` restriction
2. Use `android:usesCleartextTraffic="true"` at the `<application>`
   level (flagged by Play Protect)
3. Trust user-installed CAs in the release build

If your app requires cleartext for a local network (e.g., connecting
to a local device via HTTP), use:

```xml
<domain-config cleartextTrafficPermitted="true">
  <domain includeSubdomains="true">192.168.0.0/24</domain>
</domain-config>
```

And declare the `android.permission.INTERNET` and local network
usage in `AndroidManifest.xml` with a privacy disclosure.

## Capacitor — checking bundled web content

Capacitor serves your web app from a local server. The
`network_security_config.xml` controls native network calls and
WebView navigations, but `fetch()` inside the WebView is also
subject to it.

```bash
# Scan your built JS for HTTP endpoints
grep -rE "http://[^'\"]" android/app/src/main/assets/public/ \
  | grep -v localhost \
  | grep -v "127.0.0.1"
```

Any `http://` URLs in your JS bundle that are not localhost will be
blocked by the network security config and cause silent failures.

## Certificate pinning expiration

The `expiration` attribute on `<pin-set>` is critical. When
the date passes, Android **stops enforcing the pin** rather than
blocking connections. This is a safety valve to prevent users being
locked out after a cert rotation, but it means your pin stops
providing protection after that date.

Procedure:
1. Set `expiration` at least 90 days past your expected cert renewal
2. Before the date, update the pin with the new cert's SPKI hash
3. Ship the update; wait for rollout
4. Renew the cert; extend the expiration date in the next release

```bash
# Generate SPKI hash for a domain
openssl s_client -connect api.example.com:443 -servername api.example.com \
  </dev/null 2>/dev/null \
  | openssl x509 -pubkey -noout \
  | openssl pkey -pubin -outform der \
  | openssl dgst -sha256 -binary \
  | openssl enc -base64
```

## Verification
- [ ] `android:usesCleartextTraffic="false"` in `AndroidManifest.xml`
- [ ] `network_security_config.xml` referenced in manifest
- [ ] No `<certificates />` in release config
- [ ] Pin-set has two pins (current + backup)
- [ ] Pin-set expiration date > current date + 90 days
- [ ] Cleartext traffic test: `adb shell` then `curl http://api.example.com` — should fail
- [ ] Charles Proxy fails to intercept release build

## Gotchas
- **Capacitor 4.x** previously defaulted to
  `android:usesCleartextTraffic="true"`. Upgrade to Capacitor 5+
  which defaults to false. Check your `AndroidManifest.xml` — old
  projects may still have the override.
- **OkHttp is separate.** The network security config applies to
  system HTTP stacks (HttpURLConnection, WebView). If you use OkHttp
  directly (e.g., via a Capacitor plugin), you must configure pinning
  there separately — see `certificate-pinning.md`.
- **React Native uses its own HTTP client** (`fetch` via Hermes), which
  does respect the network security config on Android.
- **Pin-set with no backup pin** causes Android to throw a
  `CertPathValidatorException` if the primary pin doesn't match, with
  no fallback. Always include two pins.
- **`includeSubdomains="true"` pins all subdomains.** If you pin
  `example.com` with includeSubdomains, then `cdn.example.com` must
  also present a cert whose SPKI matches — easy to miss.

## Related
- `certificate-pinning.md`
- `ios-app-transport-security.md`
- `play-integrity-attestation.md`
- Android Network Security Config: https://developer.android.com/training/articles/security-config
- Android CertificatePinner (OkHttp): https://square.github.io/okhttp/features/https/#certificate-pinning
- Google Play cleartext policy: https://support.google.com/googleplay/android-developer/answer/9888076
