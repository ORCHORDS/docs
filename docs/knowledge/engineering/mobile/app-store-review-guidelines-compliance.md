# App Store Review Guidelines — Compliance Engineering for iOS and Android

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your mobile app submission is rejected by Apple App Review or Google Play
Review, and the rejection reason references guideline violations you
were not aware of. Your team submits an update, waits 24-48 hours for
review, gets rejected, fixes one issue, resubmits, and gets rejected for
a different reason. Each review cycle takes days, delaying releases.
You have no pre-submission checklist, no automated compliance checks,
and no systematic way to catch guideline violations before submission.

## Context

Apple's App Store Review Guidelines and Google Play Developer Program
Policies define what apps can and cannot do on their platforms. In 2026,
Apple updated guidelines (June 8, 2026) with stricter rules around AI
disclosures, data transparency, privacy manifests, and Live Activities.
Google Play has tightened policies around data safety declarations,
target API level requirements, and AI-generated content. Both platforms
use a combination of automated binary analysis and human review. The
key engineering concern is building compliance into the development
process rather than discovering violations at submission time.

## Apple App Store review process

```
Binary upload → Automated checks → Human review → Decision

Automated checks:
  □ Malware scanning
  □ API usage validation (private APIs rejected)
  □ Entitlement verification
  □ Privacy manifest compliance (PrivacyInfo.xcprivacy)
  □ Binary size and architecture checks

Human review:
  □ App tested on physical devices
  □ Metadata accuracy (screenshots, descriptions)
  □ Privacy declarations vs. observed behavior
  □ In-app purchase implementation
  □ Content policy compliance
```

## Key compliance areas (2026)

### 1. Privacy and data transparency

```
Apple requirements:
  □ PrivacyInfo.xcprivacy manifest in all apps and SDKs
  □ Declare all data collection in App Store Connect
  □ App Tracking Transparency (ATT) prompt before tracking
  □ Purpose strings for all system permissions
  □ Nutrition labels match actual data practices

Google Play requirements:
  □ Data Safety section accurately completed
  □ Privacy policy URL provided
  □ Data deletion capability (user can request deletion)
  □ Consent before data collection for sensitive categories

Common rejection: privacy declarations do not match
observed network traffic (Apple tests with proxies).
```

### 2. AI and ML disclosures

```
2026 requirements:
  □ Disclose which AI services the app uses
  □ Specify what user data is sent to AI services
  □ AI-generated content must be labeled
  □ Chatbot interactions must disclose AI (not human)
  □ AI cannot make health, legal, or financial decisions
    without human oversight disclosure
```

### 3. In-app purchases

```
Apple:
  □ Digital goods/services MUST use Apple IAP
  □ Physical goods/services can use external payment
  □ Subscriptions must use StoreKit 2
  □ Restore purchases button required
  □ Clear pricing before purchase confirmation
  □ No misleading subscription flows

Google:
  □ Digital goods use Google Play Billing Library
  □ Subscription transparency: clear terms, easy cancel
  □ Grace period and account hold support
  □ Price changes require user consent

Rejection trigger: offering digital content purchase
via web link or external payment without IAP.
```

### 4. Minimum API level

```
Apple (2026):
  □ Minimum deployment target: iOS 16 (recommended iOS 17)
  □ Must support current and previous iPhone models
  □ iPad support required for universal apps
  □ SwiftUI preferred for new UI (UIKit still accepted)

Google Play (2026):
  □ New apps: targetSdkVersion >= 35 (Android 15)
  □ App updates: targetSdkVersion >= 34 (Android 14)
  □ Apps targeting lower API levels are rejected
  □ Photo/video permissions: must use photo picker (no broad access)
```

## Pre-submission checklist

```
Metadata:
  □ App name does not include pricing or "free"
  □ Screenshots are actual app screens (no renders)
  □ Description accurately reflects app functionality
  □ Age rating matches content
  □ Category selection is appropriate

Privacy:
  □ PrivacyInfo.xcprivacy includes all tracking domains
  □ App Store Connect privacy labels are accurate
  □ ATT prompt appears before any tracking
  □ Purpose strings explain WHY each permission is needed
  □ Data Safety section (Google) is complete and accurate

Functionality:
  □ App does not crash on launch or during core flows
  □ Login flow works (provide demo account in review notes)
  □ All links are functional (no broken URLs)
  □ Placeholder content is removed
  □ App works offline or shows appropriate offline message

Payments:
  □ Digital purchases use platform IAP
  □ Restore purchases works correctly
  □ Subscription terms are clear before purchase
  □ Free trial length is accurately displayed
  □ Cancellation flow is accessible

Content:
  □ User-generated content has reporting/blocking mechanism
  □ AI features disclose AI usage
  □ No copyrighted material without license
  □ No misleading claims (health, financial)
```

## CI/CD integration

```yaml
# Automated pre-submission checks (Fastlane)
lane :precheck do
  # Validate app metadata
  precheck(
    negative_apple_sentiment: {level: :error},
    placeholder_text: {level: :error},
    other_platforms: {level: :warn},
    future_functionality: {level: :error}
  )

  # Validate privacy manifest
  sh("plutil -lint path/to/PrivacyInfo.xcprivacy")

  # Check for private API usage
  sh("grep -r '_UIPrivate\\|_NS.*Private' Sources/ && exit 1 || true")

  # Validate entitlements
  sh("codesign -d --entitlements :- build/App.app | \
      plutil -lint -")
end

lane :submit do
  precheck
  build_app(scheme: "Production")
  upload_to_app_store(
    submit_for_review: true,
    automatic_release: false,
    submission_information: {
      add_id_info_uses_idfa: false
    }
  )
end
```

## Review notes best practices

```
Always include in review notes:
  □ Demo account credentials (if login required)
  □ Explanation of non-obvious features
  □ Steps to access restricted features
  □ Why specific permissions are needed
  □ Explanation of background activity
  □ Contact information for review questions

Example:
  "Demo account: demo@example.com / TestPass123
   To test push notifications, send a message from
   the second demo account: demo2@example.com
   Location permission is used for store finder
   (Settings > Privacy shows our usage).
   Contact: review@mycompany.com"
```

## Anti-patterns

- **Submitting without testing on device** — simulators and emulators
  miss device-specific issues (camera, biometrics, push notifications).
  Apple reviewers test on physical devices; your app must work on them.
- **Hidden functionality** — hiding features from reviewers that
  violate guidelines (server-side feature flags that enable prohibited
  functionality after review). Apple has caught and permanently banned
  developers for this.
- **Ignoring rejection feedback** — resubmitting without addressing
  the specific rejection reason. Repeated guideline violations can
  lead to account suspension. Address every point in the rejection
  notice.
- **Last-minute compliance** — discovering privacy manifest
  requirements the day before a major release. Build compliance
  checks into CI/CD so violations are caught during development.

## Gotchas

- **Review time variability** — Apple review typically takes 24-48
  hours but can take up to 7 days during busy periods (post-WWDC,
  holiday season). Plan submissions with buffer time before deadlines.
- **Expedited review** — Apple offers expedited review for critical
  bug fixes. Use sparingly; abuse results in rejection of future
  expedite requests.
- **Regional requirements** — apps distributed in specific regions
  may need additional compliance (China requires ICP license, EU
  requires GDPR compliance UI, South Korea requires age verification).
  These are checked during review.
- **Third-party SDK compliance** — your app is responsible for
  guideline compliance of all included SDKs. A third-party SDK using
  private APIs or collecting undisclosed data causes your app to be
  rejected. Audit SDK privacy manifests.

## Verification

- Pre-submission checklist is completed for every release.
- Automated compliance checks run in CI/CD pipeline.
- Privacy manifests are accurate and up to date.
- Demo accounts and review notes are provided with every submission.
- In-app purchases use platform-required payment systems.
- AI features include required disclosures.
- Third-party SDKs are audited for compliance.

## Related

- `documentation/docs/policies/mobile/ota-updates-expo-codepush.md`
- `documentation/docs/policies/compliance/soc2-type-ii-audit-preparation.md`
- `documentation/docs/policies/security/zero-trust-network-architecture-ztna.md`

## Source URLs (verified 2026-08-16)

- iOS App Store Review Guidelines 2026 — https://theapplaunchpad.com/blog/ios-app-store-review-guidelines/
- Apple App Store Review Requirements 2026 — https://lexogrine.com/blog/apple-app-store-review-requirements-2026
- Complete First-Time App Review Guide 2026 — https://capgo.app/blog/first-time-app-review-guide/
- Apple App Store Submission Guide 2026 — https://gotechsolutions.co/blog/apple-app-store-submission-guide-2026/
