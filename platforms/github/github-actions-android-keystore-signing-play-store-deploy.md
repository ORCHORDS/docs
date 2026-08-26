# GitHub Actions Android Keystore Signing and Play Store Deployment
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Android release builds in CI fail with "keystore not found" or "signing config not specified"
errors. Alternatively, release builds work locally but the keystore file was committed to the
repository (a critical security issue), or it lives on a single developer's machine, blocking
automated Play Store uploads. You want a reproducible, secret-safe Android signing pipeline in
GitHub Actions that publishes to Google Play and integrates with your existing Cloudflare Workers
API release workflow.

## Context

Android release builds require a keystore file (`.jks` or `.keystore`) containing the signing
key. Google Play requires that all updates to an app are signed with the same key — once you
publish with a key, that key cannot be changed (without Google Play App Signing migration).

Key concepts:
- **Keystore**: Java KeyStore file containing one or more key aliases. Encrypted with a
  store password. Each alias has its own key password.
- **`signingConfigs`** in Gradle: named signing configurations referenced by `buildTypes`.
- **Google Play App Signing**: Google holds the upload key; you sign APKs/AABs with an upload
  key, and Google re-signs with the distribution key. Migration from self-managed signing to
  App Signing is the recommended approach for new apps.
- **Google Play Developer API**: accepts AAB/APK uploads via service account credentials.
  Fastlane Supply wraps this API.

Two approaches:
1. **EAS Submit** (Expo / React Native) — covered in `github-actions-expo-eas-build-submit-pipeline.md`.
2. **Native Gradle + Fastlane** — covered in this article for native Android or React Native
   projects using a local Gradle build.

## Approach: Gradle build with keystore from GitHub Secrets

### Prepare the keystore secret

```bash
# On a machine with the keystore
base64 -w 0 orchords-upload.jks > keystore.b64
# Copy the output into the ANDROID_KEYSTORE_BASE64 GitHub secret
```

### Gradle signing configuration (`android/app/build.gradle`)

```groovy
android {
    signingConfigs {
        release {
            storeFile file(System.getenv("ANDROID_KEYSTORE_PATH") ?: "debug.keystore")
            storePassword System.getenv("ANDROID_KEY_STORE_PASSWORD") ?: "android"
            keyAlias System.getenv("ANDROID_KEY_ALIAS") ?: "androiddebugkey"
            keyPassword System.getenv("ANDROID_KEY_PASSWORD") ?: "android"
        }
    }

    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
}
```

### GitHub Actions workflow

```yaml
# .github/workflows/android-release.yml
name: Android Release Build

on:
  push:
    branches: [main]
    paths:
      - 'android/**'
      - 'mobile/**'
      - 'package.json'
  workflow_dispatch:
    inputs:
      track:
        description: 'Play Store track (internal / alpha / beta / production)'
        required: true
        default: 'internal'
        type: choice
        options: [internal, alpha, beta, production]

jobs:
  build-and-upload:
    name: Build AAB and upload to Play Store
    runs-on: ubuntu-latest
    environment: android-production
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      # For React Native: install JS dependencies first
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install JS dependencies
        run: npm ci

      - uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'

      - name: Set up Gradle cache
        uses: actions/cache@v4
        with:
          path: |
            ~/.gradle/caches
            ~/.gradle/wrapper
          key: gradle-${{ runner.os }}-${{ hashFiles('**/*.gradle*', '**/gradle-wrapper.properties') }}
          restore-keys: |
            gradle-${{ runner.os }}-

      - name: Decode keystore
        run: |
          KEYSTORE_PATH="$RUNNER_TEMP/orchords-upload.jks"
          echo "${{ secrets.ANDROID_KEYSTORE_BASE64 }}" | base64 --decode > "$KEYSTORE_PATH"
          echo "ANDROID_KEYSTORE_PATH=$KEYSTORE_PATH" >> "$GITHUB_ENV"

      - name: Build release AAB
        working-directory: android
        env:
          ANDROID_KEY_STORE_PASSWORD: ${{ secrets.ANDROID_KEY_STORE_PASSWORD }}
          ANDROID_KEY_ALIAS: ${{ secrets.ANDROID_KEY_ALIAS }}
          ANDROID_KEY_PASSWORD: ${{ secrets.ANDROID_KEY_PASSWORD }}
        run: |
          ./gradlew bundleRelease \
            --stacktrace \
            -Dorg.gradle.daemon=false

      - name: Verify AAB signature
        run: |
          AAB_PATH="android/app/build/outputs/bundle/release/app-release.aab"
          # Extract the APK set and verify
          java -jar /opt/bundletool.jar validate --bundle="$AAB_PATH" || true
          ls -lh "$AAB_PATH"

      - name: Upload AAB artifact
        uses: actions/upload-artifact@v4
        with:
          name: app-release-${{ github.sha }}.aab
          path: android/app/build/outputs/bundle/release/app-release.aab
          retention-days: 14

      - name: Write Play Store service account key
        run: |
          echo '${{ secrets.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON }}' \
            > "$RUNNER_TEMP/play-service-account.json"

      - name: Set up Ruby for Fastlane
        uses: ruby/setup-ruby@v1
        with:
          ruby-version: '3.3'
          bundler-cache: true

      - name: Upload to Google Play (${{ inputs.track || 'internal' }})
        working-directory: android
        env:
          PLAY_STORE_JSON_KEY: ${{ runner.temp }}/play-service-account.json
          SUPPLY_TRACK: ${{ inputs.track || 'internal' }}
        run: |
          bundle exec fastlane supply \
            --aab "app/build/outputs/bundle/release/app-release.aab" \
            --json_key "$PLAY_STORE_JSON_KEY" \
            --track "$SUPPLY_TRACK" \
            --skip_upload_apk true \
            --skip_upload_metadata true \
            --skip_upload_screenshots true

      - name: Clean up secrets
        if: always()
        run: |
          rm -f "$RUNNER_TEMP/orchords-upload.jks"
          rm -f "$RUNNER_TEMP/play-service-account.json"
```

### Fastfile (Play Store upload lane)

```ruby
# android/fastlane/Fastfile
default_platform(:android)

platform :android do
  desc "Upload AAB to Google Play"
  lane :upload_play do |options|
    supply(
      aab: "app/build/outputs/bundle/release/app-release.aab",
      json_key: ENV["PLAY_STORE_JSON_KEY"],
      track: options[:track] || "internal",
      skip_upload_apk: true,
      skip_upload_metadata: true,
      skip_upload_screenshots: true,
      skip_upload_images: true,
      release_status: "completed"
    )
  end

  desc "Bump version code and build release AAB"
  lane :build_and_bump do
    current_vc = google_play_track_version_codes(
      track: "internal",
      json_key: ENV["PLAY_STORE_JSON_KEY"]
    ).max

    increment_version_code(
      gradle_file_path: "app/build.gradle",
      version_code: current_vc + 1
    )

    gradle(
      task: "bundle",
      build_type: "Release",
      properties: {
        "android.injected.signing.store.file" => ENV["ANDROID_KEYSTORE_PATH"],
        "android.injected.signing.store.password" => ENV["ANDROID_KEY_STORE_PASSWORD"],
        "android.injected.signing.key.alias" => ENV["ANDROID_KEY_ALIAS"],
        "android.injected.signing.key.password" => ENV["ANDROID_KEY_PASSWORD"],
      }
    )
  end
end
```

## Secrets required

| Secret name | Description |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | Base64-encoded `.jks` keystore file |
| `ANDROID_KEY_STORE_PASSWORD` | Keystore store password |
| `ANDROID_KEY_ALIAS` | Key alias inside the keystore |
| `ANDROID_KEY_PASSWORD` | Key password for the alias |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | Google Play Developer API service account JSON |

All five secrets should be scoped to the `android-production` GitHub Environment, not the
repository level, so they require environment approval before use.

## Google Play service account setup

1. Create a service account in Google Cloud Console in the project linked to your Play Console.
2. Grant the service account **Release manager** role in Play Console
   (Settings → Users and permissions → Service accounts).
3. Download the JSON key and store as `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`.

Minimum permissions needed:
- `androidpublisher.apks.upload`
- `androidpublisher.edits.commit`
- `androidpublisher.edits.delete`
- `androidpublisher.edits.get`
- `androidpublisher.edits.tracks.update`

## Coordinating with Cloudflare Workers API deploy

For mobile apps with a versioned API, gate Android submission after Workers deploy:

```yaml
jobs:
  deploy-api:
    uses: ./.github/workflows/deploy-workers.yml
    secrets: inherit

  build-android:
    needs: deploy-api
    uses: ./.github/workflows/android-release.yml
    secrets: inherit
    with:
      track: internal
```

## Version code automation

Google Play rejects a version code that is not strictly greater than all previously uploaded
codes. Automate version code from CI run number:

```groovy
// android/app/build.gradle
android {
    defaultConfig {
        versionCode System.getenv("GITHUB_RUN_NUMBER")?.toInteger() ?: 1
        versionName "1.0.${System.getenv('GITHUB_RUN_NUMBER') ?: '0'}"
    }
}
```

## Anti-patterns

- **Committing the keystore**: even in a private repo, the keystore must never be committed.
  A leaked keystore combined with the passwords allows anyone to sign apps as your publisher.
- **Using repository-level secrets instead of environment secrets**: anyone with write access to
  the repo can trigger a build and access the secrets. Use a protected `android-production`
  environment with required reviewers for production tracks.
- **Storing the service account JSON as a file in the repo**: same risk as the keystore.
  Always write from a secret and clean up with `if: always()`.
- **Not cleaning up `ANDROID_KEYSTORE_PATH`**: on self-hosted runners the file persists across
  jobs. Always delete in the `if: always()` cleanup step.
- **Uploading to `production` track automatically**: internal → alpha → beta → production should
  involve human promotion decisions. Use `workflow_dispatch` with track as a required input for
  anything beyond internal.

## Gotchas

- The Google Play API rejects uploads where `versionCode` is not strictly greater than any
  existing build on any track, including drafts. Check all tracks before incrementing.
- AAB files (`.aab`) are required for new apps since August 2021; APK uploads are only
  permitted for existing apps and some special categories.
- `gradlew bundleRelease` requires `JAVA_HOME` to be set; `actions/setup-java@v4` does this
  automatically. Do not rely on pre-installed JVM versions on ubuntu runners.
- Fastlane Supply `--release_status completed` immediately makes the build available on the
  selected track. Use `draft` to hold for manual promotion.
- Google Play API service accounts have a per-day quota on edit API calls. High-frequency CI
  (multiple uploads per day) is fine; thousands per day may require quota increases.

## Verification

1. Run the workflow via `workflow_dispatch` targeting the `internal` track.
2. Confirm the AAB artifact appears in the Actions run summary.
3. Check Google Play Console under Testing → Internal Testing for the new build.
4. Confirm the cleanup step removes the keystore and service account files.
5. Confirm the workflow is blocked by the `android-production` environment approval gate.

## Related

- `github-actions-expo-eas-build-submit-pipeline.md`
- `github-actions-ios-code-signing-provisioning-profiles.md`
- `github-actions-environment-protection.md`
- `github-actions-secrets-management.md`
- `github-actions-cloudflare-deploy-workflow.md`

## Sources

- https://developer.android.com/build/building-cmdline
- https://docs.fastlane.tools/actions/supply/
- https://developers.google.com/android-publisher/api-ref/rest
- https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect
