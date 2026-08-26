# GitHub Actions iOS Code Signing and Provisioning Profile Management
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

iOS builds fail in CI with "no signing identity found" or "no provisioning profile" errors.
Alternatively, signing works locally but is never automated, causing release bottlenecks whenever
a new developer certificate or provisioning profile expires. You want a reproducible, secret-safe
code-signing setup that works in GitHub Actions for both development and production iOS builds,
whether you use Expo EAS Credentials, Fastlane Match, or manual certificate management.

## Context

iOS code signing requires three artifacts:
1. **Signing certificate** (`.p12`) — issued by Apple; tied to a developer or distribution
   identity in your Apple team.
2. **Provisioning profile** (`.mobileprovision`) — ties a certificate, an app bundle ID, and
   (for non-AppStore profiles) specific device UDIDs together.
3. **Keychain** — macOS secure store where Xcode looks for the certificate at build time.

For CI, there are three common approaches:

| Approach | Tooling | Storage | Recommended for |
|---|---|---|---|
| EAS Credentials | `eas-cli` | Expo cloud | Expo / React Native projects |
| Fastlane Match | `fastlane match` | Encrypted Git repo or S3 | Native iOS projects |
| Manual base64 | `base64`/`security` | GitHub Secrets | Small teams, no Fastlane |

This article covers all three approaches and the GitHub Actions wiring for each.

## Approach 1: EAS Credentials (Expo projects)

EAS manages certificates and profiles inside Expo's infrastructure. The runner never handles raw
credentials; it only calls `eas build` with an authenticated token.

```yaml
# Works as described in github-actions-expo-eas-build-submit-pipeline.md
- uses: expo/expo-github-action@v8
  with:
    eas-version: latest
    token: ${{ secrets.EXPO_TOKEN }}

- run: eas build --profile production --platform ios --non-interactive --wait
  working-directory: mobile
```

**No keychain setup required.** EAS handles everything on its managed macOS builders.

## Approach 2: Fastlane Match

Match stores encrypted certificates and profiles in a dedicated Git repository (or S3). Each CI
run clones the match repo, decrypts with a passphrase, and installs certs into a temporary
keychain.

### Repository layout (match repo)

```
certs/
  development/
    com.orchords.app.p12
    com.orchords.app.mobileprovision
  distribution/
    com.orchords.app.p12
    com.orchords.app.mobileprovision
```

### Matchfile

```ruby
# fastlane/Matchfile
git_url("https://github.com/example-org/example-repo")
storage_mode("git")
type("appstore")            # default; override per lane
app_identifier(["com.orchords.app"])
username("releases@example.com")
```

### Fastlane lane

```ruby
# fastlane/Fastfile
desc "Sync signing and build for CI"
lane :build_release do
  create_keychain(
    name: "build.keychain",
    password: ENV["MATCH_KEYCHAIN_PASSWORD"],
    default_keychain: true,
    unlock: true,
    timeout: 3600,
    lock_when_sleeps: false
  )

  match(
    type: "appstore",
    readonly: true,
    keychain_name: "build.keychain",
    keychain_password: ENV["MATCH_KEYCHAIN_PASSWORD"]
  )

  build_app(
    workspace: "Orchords.xcworkspace",
    scheme: "Orchords",
    export_method: "app-store",
    output_directory: "./build",
    output_name: "Orchords.ipa"
  )
end
```

### GitHub Actions workflow (Fastlane Match)

```yaml
# .github/workflows/ios-release.yml
name: iOS Release Build

on:
  push:
    branches: [main]
    paths:
      - 'ios/**'
      - 'fastlane/**'

jobs:
  build-ios:
    runs-on: macos-14    # Apple Silicon runner; required for Xcode 15+
    environment: ios-production
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Set up Ruby
        uses: ruby/setup-ruby@v1
        with:
          ruby-version: '3.3'
          bundler-cache: true

      - name: Install CocoaPods
        run: bundle exec pod install
        working-directory: ios

      - name: Build and sign
        env:
          MATCH_PASSWORD: ${{ secrets.MATCH_PASSWORD }}
          MATCH_KEYCHAIN_PASSWORD: ${{ secrets.MATCH_KEYCHAIN_PASSWORD }}
          MATCH_GIT_BASIC_AUTHORIZATION: ${{ secrets.MATCH_GIT_BASIC_AUTHORIZATION }}
          APP_STORE_CONNECT_API_KEY_KEY_ID: ${{ secrets.ASC_KEY_ID }}
          APP_STORE_CONNECT_API_KEY_ISSUER_ID: ${{ secrets.ASC_ISSUER_ID }}
          APP_STORE_CONNECT_API_KEY_KEY: ${{ secrets.ASC_PRIVATE_KEY }}
        run: bundle exec fastlane build_release

      - name: Upload IPA artifact
        uses: actions/upload-artifact@v4
        with:
          name: Orchords-${{ github.sha }}.ipa
          path: build/Orchords.ipa
          retention-days: 7
```

### Secrets required (Fastlane Match)

| Secret | Description |
|---|---|
| `MATCH_PASSWORD` | Passphrase used to encrypt certs in the match repo |
| `MATCH_KEYCHAIN_PASSWORD` | Temporary keychain password for this runner session |
| `MATCH_GIT_BASIC_AUTHORIZATION` | `base64(user:token)` — PAT with read access to certs repo |
| `ASC_KEY_ID` | App Store Connect API key ID |
| `ASC_ISSUER_ID` | App Store Connect API issuer ID |
| `ASC_PRIVATE_KEY` | App Store Connect API private key (`.p8` file contents) |

## Approach 3: Manual base64 certificate injection

For teams without Fastlane who want simple certificate management via GitHub Secrets.

### Prepare secrets

```bash
# On a Mac with the certificate exported from Keychain
base64 -i Orchords_Distribution.p12 -o cert.b64
cat cert.b64   # paste into DIST_CERTIFICATE_P12 secret

base64 -i Orchords_AppStore.mobileprovision -o profile.b64
cat profile.b64  # paste into PROVISION_PROFILE_B64 secret
```

### Workflow

```yaml
# .github/workflows/ios-manual-sign.yml
name: iOS Manual Sign Build

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: macos-14
    environment: ios-production
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Install certificate and profile
        env:
          DIST_CERT_P12: ${{ secrets.DIST_CERTIFICATE_P12 }}
          DIST_CERT_PASSWORD: ${{ secrets.DIST_CERTIFICATE_PASSWORD }}
          PROVISION_PROFILE_B64: ${{ secrets.PROVISION_PROFILE_B64 }}
          KEYCHAIN_PASSWORD: ${{ secrets.KEYCHAIN_PASSWORD }}
        run: |
          CERT_PATH="$RUNNER_TEMP/dist.p12"
          PROFILE_PATH="$RUNNER_TEMP/Orchords.mobileprovision"
          KEYCHAIN_PATH="$RUNNER_TEMP/build.keychain-db"

          # Decode secrets
          echo "$DIST_CERT_P12"        | base64 --decode > "$CERT_PATH"
          echo "$PROVISION_PROFILE_B64" | base64 --decode > "$PROFILE_PATH"

          # Create keychain
          security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
          security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"
          security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"

          # Import certificate
          security import "$CERT_PATH" \
            -P "$DIST_CERT_PASSWORD" \
            -A -t cert -f pkcs12 \
            -k "$KEYCHAIN_PATH"
          security list-keychain -d user -s "$KEYCHAIN_PATH"

          # Install provisioning profile
          PP_DIR="$HOME/Library/MobileDevice/Provisioning Profiles"
          mkdir -p "$PP_DIR"
          UUID=$(grep -a -A 1 UUID "$PROFILE_PATH" | grep string | \
            sed 's/.*<string>\(.*\)<\/string>/\1/')
          cp "$PROFILE_PATH" "$PP_DIR/$UUID.mobileprovision"

          echo "PROFILE_UUID=$UUID" >> "$GITHUB_ENV"
          echo "KEYCHAIN_PATH=$KEYCHAIN_PATH" >> "$GITHUB_ENV"

      - name: Build IPA
        run: |
          xcodebuild \
            -workspace ios/Orchords.xcworkspace \
            -scheme Orchords \
            -configuration Release \
            -archivePath "$RUNNER_TEMP/Orchords.xcarchive" \
            archive \
            CODE_SIGN_STYLE=Manual \
            PROVISIONING_PROFILE="$PROFILE_UUID" \
            OTHER_CODE_SIGN_FLAGS="--keychain=$KEYCHAIN_PATH"

          xcodebuild \
            -exportArchive \
            -archivePath "$RUNNER_TEMP/Orchords.xcarchive" \
            -exportPath "$RUNNER_TEMP/export" \
            -exportOptionsPlist ios/ExportOptions.plist

      - name: Clean up keychain
        if: always()
        run: |
          security delete-keychain "$RUNNER_TEMP/build.keychain-db" 2>/dev/null || true

      - name: Upload IPA
        uses: actions/upload-artifact@v4
        with:
          name: Orchords-${{ github.sha }}.ipa
          path: ${{ runner.temp }}/export/Orchords.ipa
          retention-days: 7
```

### ExportOptions.plist

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key>
  <string>app-store</string>
  <key>teamID</key>
  <string>XXXXXXXXXX</string>
  <key>signingStyle</key>
  <string>manual</string>
  <key>uploadSymbols</key>
  <true/>
</dict>
</plist>
```

## Certificate rotation

Certificates expire annually. Add a Dependabot-style reminder via scheduled workflow:

```yaml
# .github/workflows/cert-expiry-check.yml
name: iOS Certificate Expiry Check
on:
  schedule:
    - cron: '0 9 * * 1'   # Every Monday at 09:00 UTC

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check cert expiry (Fastlane Match)
        env:
          MATCH_PASSWORD: ${{ secrets.MATCH_PASSWORD }}
          MATCH_GIT_BASIC_AUTHORIZATION: ${{ secrets.MATCH_GIT_BASIC_AUTHORIZATION }}
        run: |
          bundle exec fastlane run match type:appstore readonly:true \
            skip_provisioning_profiles:true 2>&1 | \
            grep -i "expires" || echo "No expiry info found"
```

## Anti-patterns

- **Committing `.p12` or `.mobileprovision` files** to any repository, even private. Use
  base64-encoded GitHub Secrets or Fastlane Match encryption.
- **Storing `MATCH_PASSWORD` in the match repo** itself. It must be a GitHub Secret.
- **Using the system keychain** instead of a temporary one. System keychain persists across
  jobs on self-hosted runners; a temporary keychain is cleaned up and never leaks to other jobs.
- **Skipping `security delete-keychain` in the cleanup step**: use `if: always()` to ensure
  certificates are wiped even when the build step fails.
- **Using macOS 12 or 13 runners with Xcode 15**: Apple Silicon targets require macOS 14+
  runners (`macos-14`) for correct arm64 simulator and native build support.

## Gotchas

- App Store Connect API keys (used by Fastlane Deliver / TestFlight upload) are separate from
  the distribution certificate. Both are needed for a full CI submit pipeline.
- Fastlane Match `readonly: true` is required in CI so the job does not try to regenerate
  certificates (which requires an interactive Apple ID session).
- `MATCH_GIT_BASIC_AUTHORIZATION` must be `base64("username:github_pat")` — the colon and
  base64 encoding are both mandatory.
- On Apple Silicon (`macos-14`) runners, `security` commands must unlock the keychain before
  importing. The `set-keychain-settings -lut` timeout prevents auto-lock mid-build.
- Provisioning profiles installed via file copy to `~/Library/MobileDevice/Provisioning
  Profiles/` must be named `<UUID>.mobileprovision`; Xcode resolves them by UUID, not filename.

## Verification

1. Trigger the workflow manually via `workflow_dispatch`.
2. Confirm the IPA artifact appears in the Actions run summary.
3. Use `altool` or Transporter to validate the IPA before submitting to App Review.
4. Run `security find-identity -v -p codesigning` in a build step (temporarily) to confirm
   the certificate is visible in the keychain.

## Related

- `github-actions-expo-eas-build-submit-pipeline.md`
- `github-actions-environment-protection.md`
- `github-actions-secrets-management.md`
- `github-actions-security-hardening.md`

## Sources

- https://docs.github.com/en/actions/deployment/deploying-xcode-applications/installing-an-apple-certificate-on-macos-runners-for-xcode-development
- https://docs.fastlane.tools/actions/match/
- https://developer.apple.com/documentation/appstoreconnectapi
