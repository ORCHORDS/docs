# GitHub Actions EAS Update OTA Deployment with Cloudflare Workers API Versioning
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You want to ship JavaScript-only bug fixes and feature changes to your React Native / Expo app
without going through the App Store or Play Store review cycle. EAS Update (Over-The-Air updates)
lets you push a new JS bundle directly to installed app instances, but coordinating OTA updates
with your Cloudflare Workers API releases is manual and error-prone. You want a CI pipeline that:
- Publishes an OTA update when JS-only changes land on `main`
- Gates OTA updates behind the matching Workers API deploy
- Rolls back the OTA update if the API deploy fails
- Tags OTA updates with the commit SHA and API Worker version for traceability

## Context

EAS Update publishes new JS bundles (the "update") to Expo's CDN. Installed apps check for
updates on launch and download them in the background. The next app launch runs the new bundle.

Key concepts:
- **Channel**: a named stream of updates (e.g. `production`, `preview`, `staging`). Each
  build is linked to a channel at build time; it can only receive updates from that channel.
- **Branch**: a named sequence of updates. Channels are mapped to branches; the mapping can
  be changed without rebuilding.
- **Runtime version**: must match between the native build and the update. A JS change that
  requires a native module bump cannot be shipped as an OTA update.
- **`eas update --branch`**: publishes a new update to a branch.
- **`eas channel:edit`**: re-maps a channel to a different branch (blue/green-style promotion).

## Architecture

```
Push to main
      │
      ├── Changed: Workers API code
      │         └─► Deploy Workers API (get version tag)
      │
      ├── Changed: mobile JS (no native changes)
      │         └─► eas update --branch main
      │                    └─► tag update with API version
      │
      └── Changed: mobile native (podfile, build.gradle, etc.)
                └─► Full EAS Build (covered separately)
```

## Repository structure

```
/
├── workers/          Cloudflare Workers API
├── mobile/           Expo React Native app
│   ├── app.json
│   └── eas.json
└── .github/
    └── workflows/
        ├── deploy-workers.yml
        └── eas-ota-update.yml
```

## `eas.json` update channels

```json
{
  "build": {
    "production": {
      "channel": "production",
      "runtimeVersion": {
        "policy": "nativeVersion"
      }
    },
    "staging": {
      "channel": "staging",
      "runtimeVersion": {
        "policy": "nativeVersion"
      }
    }
  },
  "update": {
    "production": {
      "branch": "production"
    },
    "staging": {
      "branch": "staging"
    }
  }
}
```

## Workflow: coordinated API deploy + OTA update

```yaml
# .github/workflows/deploy-and-ota.yml
name: Deploy API and OTA Update

on:
  push:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    outputs:
      workers_changed: ${{ steps.filter.outputs.workers }}
      mobile_js_changed: ${{ steps.filter.outputs.mobile_js }}
      mobile_native_changed: ${{ steps.filter.outputs.mobile_native }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2

      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            workers:
              - 'workers/**'
              - 'wrangler.toml'
            mobile_js:
              - 'mobile/app/**'
              - 'mobile/components/**'
              - 'mobile/hooks/**'
              - 'mobile/screens/**'
              - 'mobile/package.json'
            mobile_native:
              - 'mobile/ios/**'
              - 'mobile/android/**'
              - 'mobile/app.json'

  deploy-workers:
    needs: detect-changes
    if: needs.detect-changes.outputs.workers_changed == 'true'
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    outputs:
      worker_version: ${{ steps.deploy.outputs.worker_version }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Deploy Cloudflare Worker
        id: deploy
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          command: deploy --env production

      - name: Extract Worker deployment version
        id: version
        run: |
          # Use commit SHA as version identifier
          echo "worker_version=${{ github.sha }}" >> "$GITHUB_OUTPUT"

  publish-ota-update:
    needs: [detect-changes, deploy-workers]
    # Run if JS changed; if Workers also changed, wait for deploy to succeed first
    if: |
      needs.detect-changes.outputs.mobile_js_changed == 'true' &&
      (needs.detect-changes.outputs.workers_changed != 'true' ||
       needs.deploy-workers.result == 'success')
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install mobile dependencies
        run: npm ci
        working-directory: mobile

      - uses: expo/expo-github-action@v8
        with:
          eas-version: latest
          token: ${{ secrets.EXPO_TOKEN }}

      - name: Publish OTA update
        id: update
        working-directory: mobile
        env:
          # Pass API version as update metadata
          EXPO_PUBLIC_API_VERSION: ${{ needs.deploy-workers.outputs.worker_version || 'unchanged' }}
        run: |
          UPDATE_OUTPUT=$(eas update \
            --branch production \
            --message "Deploy ${{ github.sha }} (API: $EXPO_PUBLIC_API_VERSION)" \
            --non-interactive \
            --json 2>/dev/null)

          UPDATE_ID=$(echo "$UPDATE_OUTPUT" | jq -r '.[0].id // empty')
          UPDATE_GROUP=$(echo "$UPDATE_OUTPUT" | jq -r '.[0].group // empty')
          echo "update_id=$UPDATE_ID"     >> "$GITHUB_OUTPUT"
          echo "update_group=$UPDATE_GROUP" >> "$GITHUB_OUTPUT"

      - name: Tag update in Expo dashboard
        working-directory: mobile
        run: |
          echo "Update ID: ${{ steps.update.outputs.update_id }}"
          echo "Update Group: ${{ steps.update.outputs.update_group }}"
          echo "Published to channel: production"

  # Native-change detection triggers full EAS Build (not OTA)
  trigger-full-build:
    needs: detect-changes
    if: needs.detect-changes.outputs.mobile_native_changed == 'true'
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Notify native change detected
        run: |
          echo "Native changes detected. Full EAS Build required."
          echo "Trigger the EAS Build workflow manually or set up auto-trigger."
          echo "OTA update NOT published for native changes."
```

## Blue/green channel promotion

For staged rollouts, maintain two branches (`production-canary` and `production`) and promote
the canary branch to the production channel after validation:

```yaml
# .github/workflows/promote-ota.yml
name: Promote OTA Canary to Production

on:
  workflow_dispatch:
    inputs:
      confirm:
        description: 'Type "promote" to confirm'
        required: true

jobs:
  promote:
    if: inputs.confirm == 'promote'
    runs-on: ubuntu-latest
    environment: production

    steps:
      - uses: expo/expo-github-action@v8
        with:
          eas-version: latest
          token: ${{ secrets.EXPO_TOKEN }}

      - name: Remap production channel to canary branch
        run: |
          eas channel:edit production --branch production-canary --non-interactive

      - name: Verify channel mapping
        run: |
          eas channel:view production --non-interactive
```

## Rollback workflow

```yaml
# .github/workflows/rollback-ota.yml
name: Rollback OTA Update

on:
  workflow_dispatch:
    inputs:
      update_group_id:
        description: 'Update group ID to roll back to (from Expo dashboard)'
        required: true

jobs:
  rollback:
    runs-on: ubuntu-latest
    environment: production

    steps:
      - uses: expo/expo-github-action@v8
        with:
          eas-version: latest
          token: ${{ secrets.EXPO_TOKEN }}

      - name: Roll back to previous update
        run: |
          eas update:roll-back-to-embedded production \
            --non-interactive || \
          echo "Note: roll-back-to-embedded resets to the native build's bundled JS."
          # To roll back to a specific group:
          # eas channel:edit production --branch <old-branch> --non-interactive
```

## Runtime version policy

Critical: OTA updates only install on app instances where the runtime version matches.
Choosing the wrong policy causes silent update failures.

| Policy | When to use |
|---|---|
| `nativeVersion` | Most common; uses `version` from `app.json` as runtime version |
| `sdkVersion` | Use only if you never make native changes between SDK upgrades |
| `appVersion` | Uses the iOS/Android app version; only works with identical versions across platforms |
| Explicit string | Full control; bump manually when native changes ship |

For a Cloudflare Workers + Expo project, `nativeVersion` with explicit `app.json` version bumps
for any native change is the recommended approach.

## Detecting JS-only vs native changes

Not all `mobile/` changes are safe for OTA. Guard against accidental native OTA attempts:

```yaml
      - name: Validate runtime version compatibility
        working-directory: mobile
        run: |
          # Check if any native files changed
          NATIVE_CHANGED=$(git diff HEAD~1 --name-only \
            -- ios/ android/ app.json | wc -l)
          if [ "$NATIVE_CHANGED" -gt 0 ]; then
            echo "::error::Native files changed; OTA update would fail for affected builds."
            echo "Run a full EAS Build instead."
            exit 1
          fi
```

## Anti-patterns

- **Publishing OTA updates before the Workers API is healthy**: if the API deploy fails and the
  OTA update ships, app users get new frontend code talking to a broken API. Always chain with
  `needs: deploy-workers` and `if: needs.deploy-workers.result == 'success'`.
- **Using OTA updates for native module changes**: an OTA update with a mismatched runtime
  version is silently skipped; users stay on the old bundle indefinitely.
- **Skipping `--non-interactive`**: `eas update` may prompt in CI, stalling the runner until
  timeout. Always pass `--non-interactive`.
- **Publishing to `production` channel directly from every branch**: use channel promotion
  (canary → production) or limit publishing to the `main` branch.
- **Not tagging updates with API version**: without metadata linking the OTA update to its
  corresponding API deploy, debugging mismatched client/server behavior is very difficult.

## Gotchas

- `eas update` publishes for all platforms (iOS and Android) by default. Use
  `--platform ios` or `--platform android` to publish to one platform only.
- The `--json` flag output format varies between `eas-cli` versions. Pin `eas-version` in
  `expo/expo-github-action` and test after upgrades.
- EAS Update requires that the `expo-updates` package is installed and configured in the app.
  Missing `expo.updates.url` in `app.json` causes silent failures.
- Channel-to-branch mapping changes take effect immediately for all future update checks, but
  apps that have already downloaded a pending update will still apply it on next launch.
- Free EAS plan limits update bandwidth. High-traffic apps may need the EAS Production plan.

## Verification

1. Merge a JS-only change to `main` and confirm the OTA workflow publishes without triggering
   a full EAS Build.
2. Check the Expo dashboard under Updates to confirm the new update appears on the `production`
   branch.
3. Install the production build on a test device and confirm it picks up the OTA update on
   the next launch.
4. Merge a change touching `android/` and confirm the workflow skips OTA publishing and prints
   the "full EAS Build required" notice.
5. Simulate an API deploy failure and confirm the OTA update step is skipped.

## Related

- `github-actions-expo-eas-build-submit-pipeline.md`
- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-path-filters.md`
- `github-actions-environments.md`

## Sources

- https://docs.expo.dev/eas-update/github-actions/
- https://docs.expo.dev/eas-update/rollouts/
- https://docs.expo.dev/eas-update/runtime-versions/
- https://docs.expo.dev/eas-update/how-it-works/
