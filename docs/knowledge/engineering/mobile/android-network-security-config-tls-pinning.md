# Android Network Security Configuration: TLS Pinning and Trust Anchors

Android's network security configuration moves TLS trust decisions out of code and into a declarative XML resource: which connections trust the system CAs, which trust user-added CAs, which domains get certificate pinning, which get cleartext forbidden. For apps that talk to their own infrastructure, it is the platform mechanism for enforcing TLS policy — including certificate pinning — without shipping custom trust managers or third-party pinning libraries. Misconfiguring it is also a reliable way to break your app in the field (pinned cert rotation without a backup pin bricks connectivity until an app update). This article covers the configuration surface, pin-set design for safe rotation, debug-only trust overrides, and the release-gate discipline that keeps pins from becoming outages.

## Scope

This article addresses Android's `networkSecurityConfig` XML: base config (cleartext policy, system/user trust anchors), domain configs (per-domain overrides), `<pin-set>` certificate pinning (digest algorithms, expiration, backup pins), debug overrides (`<debug-overrides>`), and interaction with `android:usesCleartextTraffic` and WebView. It covers configuration design and release process. It does not cover TLS implementation libraries, certificate transparency on Android, or backend cert management.

## Workflow or implementation guidance

The config is declared in the manifest (`android:networkSecurityConfig="@xml/network_security_config"`) and lives in `res/xml/`. Structure:

```xml
<network-security-config>
  <base-config cleartextTrafficPermitted="false">
    <trust-anchors>
      <certificates src="system" />
    </trust-anchors>
  </base-config>
  <domain-config cleartextTrafficPermitted="false">
    <domain includeSubdomains="true">api.example.com</domain>
    <pin-set expiration="2027-03-01">
      <pin digest="SHA-256">kXN5jGyfRfZ…base64==</pin>   <!-- current leaf/intermediate -->
      <pin digest="SHA-256">Yl3cV7pQ0mT…base64==</pin>   <!-- backup: different key -->
    </pin-set>
  </domain-config>
  <debug-overrides>
    <trust-anchors>
      <certificates src="user" />
    </trust-anchors>
  </debug-overrides>
</network-security-config>
```

Design decisions, in the order they bite:

1. **Base config first.** Android's default for apps targeting modern API levels already forbids cleartext and trusts only system CAs. Make the base explicit anyway (`cleartextTrafficPermitted="false"`, system anchors only) so behavior is legible and version-proof; every override from it is then visible as a deliberate exception.
2. **Pins pin public-key hashes, not certificates.** The `<pin>` digest is the SHA-256 of the subject public key info of the certificate you choose to pin — the leaf, or (recommended) an intermediate or your own CA-operated issuing key, since pinning higher in your chain survives leaf renewals. Compute with your provider's tooling or `openssl x509 -pubkey … | openssl pinoat`-style public-key extraction; verify the pin against the live chain before shipping (an invalid pin is an instant outage for that domain).
3. **Always ship a backup pin on a different key.** The backup is a public key you control but is not currently deployed (a spare CSR/key held offline, or your CA's alternate intermediate). When the deployed key must rotate (compromise, provider change), the app still trusts the backup key's chain: deploy a cert under the backup key, clients with the old pin-set keep working. One-pin configurations turn every certificate event into an app-update-or-outage decision.
4. **Set `expiration` on pin-sets.** The expiration date is the platform's escape hatch: after it passes, pinning stops being enforced and normal CA validation resumes. Choose a horizon that forces you to re-evaluate (6–12 months), aligned with your certificate lifecycle. An expiring pin-set degrades to base trust — recoverable without an app update — which is precisely the property that makes the failure mode safe.
5. **Scope domain configs tightly.** Pin only domains you operate end-to-end. Third-party CDNs and APIs whose certificate management you don't control will rotate their keys on their schedule, not yours; if you must pin a third party, pin their documented stable intermediates, monitor their cert-transparency updates, and set short expirations. `includeSubdomains` is a big hammer — apply where you actually own the subtree.
6. **Debug overrides are for debug builds only.** `<debug-overrides>` (trusting user CAs for Charles/mitmproxy-style inspection) applies only to `debuggable` builds; release builds ignore it. Never solve a release-networking bug by weakening the base config — that path ships. For release inspection needs, use instrumentation in QA builds, not trust-anchor changes.
7. **WebView and third-party libraries.** The config governs the platform TLS stack (OkHttp on Android via its default `Platform`, `HttpsURLConnection`); some stacks honor it via platform SSLSocket, and WebView uses its own network process honoring the same config for cleartext but not pins in older versions. Audit your HTTP clients: a library bundling its own Conscrypt-bypassing trust path ignores the config entirely.
8. **Cleartext exceptions, if legacy forces them.** Permit cleartext per-domain only (`domain-config cleartextTrafficPermitted="true"` for `legacy-device.local`), never in base; each exception gets an issue number in review and an expiry plan. `android:usesCleartextTraffic="true"` in the manifest is the legacy blanket — if both exist, the XML config wins; remove the manifest flag to avoid confusion.

Rotation runbook (the operation that outages mismanage): deploy the new key/cert alongside the old (both valid); ship an app update adding the new pin while the old remains; wait for adoption (watch your min-version metrics); retire the old key server-side; remove the old pin in the next update. Two live pins plus staggered deployment is the whole trick — the config's pin-set is designed for exactly this overlap.

A worked example: an app pins `api.example.com` to its intermediate with a 2027 expiration and a backup pin on an offline key. The provider rotates the intermediate unexpectedly. Clients still validate (pin-set now mismatched on primary but — if the provider's new intermediate isn't the backup — this is the outage case that monitor-and-expiration catches: connectivity degrades at worst until expiration, and the emergency path is deploying a cert under the backup key). The team's postmortem adds cert-transparency monitoring alerts so unexpected rotations page them before users notice.

## Controls

- CI validation step: parse the config XML in the release pipeline, extract pins, and validate each against the live chain for its domain (fail the build on a pin matching nothing in the served chain or expiring within 30 days).
- Every pin-set must contain ≥2 pins on distinct keys and a future `expiration`; a lint rule in CI enforces both structurally.
- Monitor certificate transparency logs for all pinned domains; unexpected chain changes page the owning team — the pin is only as safe as your awareness of the chain behind it.
- Review rule: no cleartext exceptions without an attached issue and removal date; no trust-anchor additions to base-config ever.
- Test matrix: release-build network tests exercising each pinned domain (a nightly job catching rotation-induced breakage before users do), plus a negative test that a wrong-pinned staging domain fails closed.

## Validation evidence

- The `network-security-config` XML schema (base/domain configs, cleartext flags, trust anchors system/user, pin-set with digest and expiration, debug-overrides), its manifest wiring, precedence over `usesCleartextTraffic`, and platform behavior details are specified in the Android Developers network security configuration guide published by Google.
- Certificate pinning semantics (public-key digest validation, failure behavior, expiration fallback to standard validation) are documented in the same guide and the `OkHttp`/platform TLS documentation that consumes the config.
- A reproducible check: run a release build against a staging host with the pin-set deliberately containing only a digest of the wrong key; observe the TLS handshake failing closed; then add the correct digest and observe success — proof the pins are enforced in your actual build config, not silently ignored (the config-not-applied miswiring fails this test).

## Failure modes and correction

- **Single-pin rotation outage.** Symptom: mass connection failures after a cert change. Correct by backup pins + CT monitoring + expiration fallback; recover by deploying backup-key certs.
- **Config not applied.** Symptom: pins seem to have no effect. Cause: manifest attribute missing/wrong resource name, or an HTTP stack that bypasses platform TLS. Correct by wiring verification (the negative test above) into CI and auditing client stacks.
- **Pinning a third party's leaf.** Symptom: periodic breakage on their renewal schedule. Correct by pinning documented stable intermediates or not pinning at all.
- **Debug trust leaking to release.** Symptom: QA inspection works on release builds (it shouldn't) — or worse, user-CA trust in production. Correct by `<debug-overrides>`-only policy and a release scan of the merged manifest.
- **Expired pins misread as outage.** Symptom: after expiration, connections succeed unpinned and a team believes pinning "still protects". Correct by expiration alerts that force pin renewal, not silent lapse.

## Limitations

- Pinning protects against CA compromise and misissuance, not against compromise of your own server keys or client device; it is one layer, not a substitute for secure key operations.
- Non-platform TLS stacks in bundled libraries may ignore the configuration; coverage is per-network-stack.
- Expiration-based fallback means protection has a time horizon — long expirations trade safety for pin-decay risk.
- Enterprise MITM proxies (corporate networks) break pinned apps by design; document a support stance rather than weakening pins.

## Canonical sources

- Google, Android Developers — Network security configuration: https://developer.android.com/privacy-and-security/security-config
- Google, Android Developers — Security with HTTPS and SSL (trust model context): https://developer.android.com/privacy-and-security/security-ssl
