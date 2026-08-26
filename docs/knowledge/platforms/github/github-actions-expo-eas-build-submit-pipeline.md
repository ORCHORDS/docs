# GitHub Actions Expo EAS Build and Submit Pipeline
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You have a React Native / Expo project alongside your Cloudflare Workers API and want to run
Expo Application Services (EAS) builds on every PR and push to main without manually
triggering builds from the Expo dashboard. You also want to gate the App Store / Play Store
submit step behind the same deployment-protection rules that guard your production Workers.

## Context

EAS Build is Expo's managed cloud build service. It compiles iOS `.ipa` and Android `.aab`
artifacts on Expo's infrastructure. `eas-cli` is the command-line interface; it can be
installed in a GitHub Actions runner and authenticated via an EXPO_TOKEN secret. EAS Submit
feeds those artifacts to Apple App Store Connect and Google Play Store. Both services run
remotely — the runner only orchestrates API calls, it does not compile locally.

Key concepts:
- **Build profile** (`eas.json` → `build.<name>`): named configurations (development, preview,
  production) with per-platform overrides.
- **Submit profile** (`eas.json` → `submit.<name>`): App Store / Play credentials and track.
- **EXPO_TOKEN**: a long-lived personal token or robot-account token used by `eas-cli` in CI.
- **`--non-interactive`**: mandatory flag for CI; suppresses prompts that would stall a runner.
- **`--wait`**: tells `eas build` to poll until the remote build finishes and exit non-zero on
  failure. Without it the command returns immediately with a build ID.

## eas.json configuration

```json
{
  "cli": {
    "version": ">= 14.0.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "ios": { "simulator": true },
      "android": { "buildType": "apk" }
    },
    "preview": {
      "distribution": "internal",
      "ios": { "enterpriseProvisioning": "adhoc" },
      "android": { "buildType": "apk" },
      "channel": "preview"
    },
    "production": {
      "autoIncrement": true,
      "ios": { "enterpriseProvisioning": "universal" },
      "android": { "buildType": "app-bundle" },
      "channel": "production"
    }
  },
  "submit": {
    "production": {
      "ios": {
        "appleId": "releases@example.com",
        "ascAppId": "1234567890",
        "appleTeamId": "XXXXXXXXXX"
      },
      "android": {
        "serviceAccountKeyPath": "/tmp/google-service-account.json",
        "track": "internal"
      }
    }
  }
}
```

## Workflow: PR preview builds

```yaml
# .github/workflows/eas-preview.yml
name: EAS Preview Build

on:
  pull_request:
    branches: [main]
    paths:
      - 'mobile/**'
      - 'package.json'
      - 'eas.json'

concurrency:
  group: eas-preview-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build-preview:
    name: Build preview (${{ matrix.platform }})
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write      # to post build-URL comment
    strategy:
      fail-fast: false
      matrix:
        platform: [ios, android]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci
        working-directory: mobile

      - uses: expo/expo-github-action@v8
        with:
          eas-version: latest
          token: ${{ secrets.EXPO_TOKEN }}

      - name: Build preview (${{ matrix.platform }})
        id: build
        working-directory: mobile
        run: |
          BUILD_OUTPUT=$(eas build \
            --profile preview \
            --platform ${{ matrix.platform }} \
            --non-interactive \
            --wait \
            --json 2>/dev/null)
          echo "build_url=$(echo "$BUILD_OUTPUT" | jq -r '.[0].buildDetailsPageUrl')" >> "$GITHUB_OUTPUT"
          echo "artifact_url=$(echo "$BUILD_OUTPUT" | jq -r '.[0].artifacts.buildUrl // empty')" >> "$GITHUB_OUTPUT"

      - name: Post build link to PR
        uses: actions/github-script@v7
        with:
          script: |
            const platform = '${{ matrix.platform }}';
            const buildUrl = '${{ steps.build.outputs.build_url }}';
            const artifactUrl = '${{ steps.build.outputs.artifact_url }}';
            const icon = platform === 'ios' ? '🍎' : '🤖';
            const body = [
              `${icon} **EAS ${platform} preview build complete**`,
              ``,
              `- Build details`,
              artifactUrl ? `- Download artifact` : '',
            ].filter(Boolean).join('\n');
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body,
            });
```

## Workflow: production build + submit on merge

```yaml
# .github/workflows/eas-production.yml
name: EAS Production Build & Submit

on:
  push:
    branches: [main]
    paths:
      - 'mobile/**'
      - 'eas.json'

jobs:
  build-and-submit:
    name: Production build & submit
    runs-on: ubuntu-latest
    environment: mobile-production    # GitHub Environment with required reviewers
    permissions:
      contents: read
      id-token: write   # if using OIDC for any auxiliary service

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci
        working-directory: mobile

      - uses: expo/expo-github-action@v8
        with:
          eas-version: latest
          token: ${{ secrets.EXPO_TOKEN }}

      # Write Google Play service account key from secret
      - name: Write Play Store service account
        run: |
          echo '${{ secrets.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON }}' \
            > /tmp/google-service-account.json

      - name: Build production (iOS + Android)
        working-directory: mobile
        run: |
          eas build \
            --profile production \
            --platform all \
            --non-interactive \
            --wait

      - name: Submit to stores
        working-directory: mobile
        run: |
          eas submit \
            --profile production \
            --platform all \
            --non-interactive \
            --latest    # submits the most recent successful production build

      - name: Clean up service account key
        if: always()
        run: rm -f /tmp/google-service-account.json
```

## Secrets required

| Secret name | Scope | Description |
|---|---|---|
| `EXPO_TOKEN` | Repository | EAS robot account token |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | Environment: mobile-production | Google Play service account JSON key |
| App Store credentials | Managed by EAS | Stored in EAS Credentials, not in GitHub Secrets |

Apple App Store Connect API keys (key ID, issuer ID, private key) are stored inside EAS Credentials
and referenced by `eas.json`. They never need to be in GitHub Secrets.

## Coordinating with Cloudflare Workers API deploy

When the mobile app depends on a new Workers API version, sequence the builds:

```yaml
jobs:
  deploy-api:
    uses: ./.github/workflows/deploy-workers.yml
    secrets: inherit

  build-mobile:
    needs: deploy-api
    # ... EAS build steps
```

This ensures the API is live before the mobile release ships.

## Anti-patterns

- **Running `eas build --local` in CI**: installs Xcode/Android SDK on the runner; extremely
  slow and expensive. Use remote EAS Build instead.
- **Not using `--wait`**: the job succeeds immediately regardless of build outcome; a failed
  remote build goes unnoticed.
- **Committing `google-service-account.json`**: even in a private repo this is a serious
  credential leak. Always write from a GitHub Secret and clean up with `if: always()`.
- **Triggering production submit on every PR**: EAS submit costs and App Review delays make
  this impractical. Gate it behind `push` to `main` and a GitHub Environment with reviewers.
- **Skipping `paths` filters**: rebuilding mobile on every backend change wastes build minutes.
  Scope triggers to `mobile/**` and `eas.json`.

## Gotchas

- `expo/expo-github-action@v8` must be pinned to a SHA for security hardening workflows.
- `--json` output format from `eas build` changed between major CLI versions; pin `eas-version`
  in the action input and test after upgrades.
- EAS free tier has concurrent build limits. For teams with multiple active PRs, builds queue.
  Consider `eas build --no-wait` and a separate polling job, or upgrade EAS plan.
- The `--latest` flag on `eas submit` submits the most recent successful build for that profile.
  If a prior build succeeded and the current one failed, this can accidentally submit stale
  artifacts. Capture the build ID explicitly:

```bash
BUILD_ID=$(eas build --profile production --platform ios --non-interactive --wait --json \
  2>/dev/null | jq -r '.[0].id')
eas submit --profile production --platform ios --id "$BUILD_ID" --non-interactive
```

- iOS builds require that Apple credentials are already configured in EAS Credentials. Run
  `eas credentials` interactively once to set them up before enabling CI.

## Verification

1. Open a PR touching `mobile/` and confirm both iOS and Android preview build jobs start.
2. Check that build-URL comments appear on the PR.
3. Merge to main and confirm the production workflow is gated by the `mobile-production`
   environment approval.
4. After approval, confirm both stores receive the new build.

## Related

- `github-actions-environment-protection.md`
- `github-actions-matrix-strategy-workers.md`
- `github-actions-secrets-management.md`
- `github-actions-concurrency-groups.md`

## Sources

- https://docs.expo.dev/eas/github-actions/
- https://github.com/expo/expo-github-action
- https://docs.expo.dev/eas-update/github-actions/
- https://docs.expo.dev/submit/introduction/
