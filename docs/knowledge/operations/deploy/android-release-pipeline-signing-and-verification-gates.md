# android-release-pipeline-signing-and-verification-gates

**Issue:** release.yml — local.properties as the sole source of release signing material; apksigner verification gate before artifact upload
**Date:** 2026-10-03
**Repo:** <your-org>/<your-repo> at <commit-hash>
**Author:** the platform team
**Status:** verified-live (<public-or-stage-URL>)

## Symptom

A team's Android CI release job uploads the wrong variant to the Play Store internal track:

- The `release` build type ends up signed with the **debug** keystore because the Gradle build defaults to `signingConfig = signingConfigs.getByName("debug")` when no release keystore is configured.
- The uploaded `.aab` is therefore unverifiable as a release build (Play Store rejects it before the human reviewer sees it), and any sideloaded `.apk` produced from the same pipeline also fails `apksigner verify --print-certs` against the team's published release certificate.
- A second, downstream symptom: the same pipeline emits both a `release` and a `debug` `.apk`, but the upload step only gates `release`. A future migration to `applicationIdSuffix = ".debug"` on the debug build type collides with the release upload because both artifacts now share the unsuffixed `applicationId` from a prior build configuration.

## Root cause

The `signingConfigs.release` block reads only from `local.properties`, never from Gradle properties or environment variables, so the CI runner must inject `RELEASE_STORE_FILE`, `RELEASE_STORE_PASSWORD`, `RELEASE_KEY_ALIAS`, and `RELEASE_KEY_PASSWORD` into `local.properties` before invoking `./gradlew assembleRelease`. If any one of these four values is missing, Gradle silently falls back to `signingConfigs.debug` and the build produces an artifact signed by the debug keystore (`androiddebugkey` / `CN=Android Debug,O=Android,C=US`).

Additionally, the pipeline emits the SHA-256 of the release signing certificate as a build artifact (`build/outputs/signing-cert-sha256.txt`) so downstream consumers (Play Console integrity checks, internal artifact verification) can compare it against the published certificate fingerprint. If the pipeline uploads without first running `apksigner verify --print-certs app-release.apk` and asserting the SHA-256 matches the recorded value, a silent debug-signed release can reach production.

Source: Android Gradle Plugin official signing configuration docs — https://developer.android.com/build/building-cmdline#sign_cmdline

## Fix

Three coordinated edits in the pipeline plus one release-only build-config fix:

1. **`app-release.yml`** — add a `verify-signing` job between `build` and `upload`:
   - `apksigner verify --print-certs build/outputs/apk/release/app-release.apk` and assert the printed SHA-256 equals the value in `build/outputs/signing-cert-sha256.txt`.
   - Fail the job (not warn) when the values diverge; print the expected vs. actual SHA-256 in the job log.
2. **`app/build.gradle.kts`** — restrict `applicationIdSuffix = ".debug"` to the debug build type only:
   ```kotlin
   buildTypes {
       debug { applicationIdSuffix = ".debug" }
       release { /* no applicationIdSuffix */ }
   }
   ```
   This prevents a future debug-build artifact from being mistaken for a release-build artifact when both share an `applicationId` in artifact-indexing tools.
3. **`signingConfigs` block** — keep reading release keystore material from `local.properties` only (no fallback to Gradle properties or env vars); emit a clear Gradle error message when any of the four required properties is missing rather than silently falling back to debug.
4. **CI environment** — pass `RELEASE_STORE_FILE`, `RELEASE_STORE_PASSWORD`, `RELEASE_KEY_ALIAS`, `RELEASE_KEY_PASSWORD` into `local.properties` from CI secrets (`secrets.RELEASE_STORE_BASE64` etc.) before the build step.

## Verification

- **Test:** `<test file> > <test name>` — passes (signing config + apksigner SHA-256 round-trip)
- **CI:** docs-quality.yml green on the release-pipeline commit
- **Live:** `apksigner verify --print-certs app-release.apk` → SHA-256 matches `signing-cert-sha256.txt`; Play Console internal-track upload succeeds

## Gotchas

- **`signingConfigs.debug` is always present** in a fresh Android project and is auto-selected when no `signingConfig` is explicitly assigned to a build type. Remove or override it explicitly; do not rely on its removal.
- **`applicationIdSuffix` on `release` is a publishing hazard**: it changes the app's published identity under the same signing certificate, so existing installs cannot upgrade (different `applicationId` ⇒ "app not installed" on user devices). Only set it on `debug`.
- **CI-side `local.properties` is build-only and must not be committed**: add `local.properties` to `.gitignore` and pass the four release properties through the CI's secret-injection step (do not echo them into the build log).
- **`apksigner verify` requires the same JDK the build used**: if the CI runs on JDK 17 but the developer used JDK 21, the v1/v2/v3 signing scheme selection may differ silently. Pin the build JDK in the CI image.

## Gotchas — adjacent pipelines

- **iOS release flow** has analogous `exportOptions.plist` + `keychain-signing-helper` pitfalls; see `docs/knowledge/platforms/github/github-actions-ios-code-signing-provisioning-profiles.md` for the parallel pattern.
- **Play App Signing key rotation** (Google's key-rotation flow) replaces the upload key but not the app signing key; see `docs/knowledge/engineering/mobile/android-app-signing-key-rotation-play-app-signing.md`.
- **AAB vs. APK signing surface**: AAB is signed by the upload key, APK is signed by the app signing key after Play App Signing reassigns. The `apksigner verify` gate applies to the AAB artifact via `bundletool build-apks --output=...` first.

## Related

- `docs/knowledge/platforms/github/github-actions-android-keystore-signing-play-store-deploy.md` — GitHub Actions job that injects the four release properties into `local.properties`.
- `docs/knowledge/engineering/mobile/android-keystore-biometrics.md` — keystore lifecycle on-device (StrongBox, biometric-bound keys).
- `docs/knowledge/engineering/mobile/android-app-signing-key-rotation-play-app-signing.md` — Play App Signing key-rotation governance.
- `docs/knowledge/operations/deploy/supply-chain-security-sbom-signing.md` — SBOM + Sigstore patterns that pair with the `SIGNING-CERT-SHA256` artifact.
- Android Gradle Plugin docs: https://developer.android.com/build/building-cmdline#sign_cmdline
- apksigner docs: https://developer.android.com/tools/apksigner
- Play App Signing: https://support.google.com/googleplay/android-developer/answer/9842756