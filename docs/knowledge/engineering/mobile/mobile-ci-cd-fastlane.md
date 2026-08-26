# mobile-ci-cd-fastlane

**Issue:** Automating iOS and Android build, sign, and deploy pipelines with Fastlane
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manual code signing and TestFlight/Play Store uploads are error-prone and slow; Fastlane automates the entire pipeline.

## Pattern / Solution
```sh
gem install fastlane
cd ios && fastlane init
```

`ios/fastlane/Fastfile`:
```ruby
default_platform(:ios)
platform :ios do
  lane :beta do
    increment_build_number
    match(type: "appstore")          # fetch certs from git repo
    build_app(scheme: "MyApp")
    upload_to_testflight(skip_waiting_for_build_processing: true)
    slack(message: "iOS beta uploaded!")
  end

  lane :release do
    match(type: "appstore")
    build_app
    deliver(submit_for_review: false)
  end
end
```

`android/fastlane/Fastfile`:
```ruby
default_platform(:android)
platform :android do
  lane :beta do
    gradle(task: "bundle", build_type: "Release")
    upload_to_play_store(track: "internal", aab: "app/build/outputs/bundle/release/app-release.aab")
  end
end
```

Store credentials in environment variables, not Fastfile:
```sh
FASTLANE_APPLE_APPLICATION_SPECIFIC_PASSWORD=xxxx
DELIVER_USER=your@email.com
```

## Gotchas
- `match` requires a private git repo for certificates and profiles; never use `development` certs in CI
- `increment_build_number` only works if the Xcode project uses `agvtool`; ensure `CURRENT_PROJECT_VERSION` is set
- Play Store API requires a Google Service Account JSON key, not your personal Google credentials
- Fastlane lanes run locally by default; wrap in GitHub Actions / CircleCI for actual CI

## Related
- `mobile-ci-cd-github-actions.md`
- `react-native-build-variants.md`
- `android-app-bundle.md`
