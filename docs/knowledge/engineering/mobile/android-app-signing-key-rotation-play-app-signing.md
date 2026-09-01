# Android App Signing Key Rotation With Play App Signing

Key rotation under Google Play App Signing replaces the artifact-signing identity that all Android updates for a package name must carry. This article covers the v3/v3.1 signature scheme's proof-of-rotation lineage, the Play Console enrollment flow, and the failure modes that permanently lock an app to a key.

## Scope

Android requires that every update to a given `applicationId` be signed with the same key as the installed version. Historically, losing that key meant losing the listing: you could never ship an update users would accept. Play App Signing resolves this by splitting the identity into two keys. Google holds the app signing key and signs what Play distributes; you keep an upload key that only gets you through the Play Console door. Rotation is therefore the act of registering a new app signing key whose certificate carries a signed lineage back to the previous one, using the APK Signature Scheme v3 key-rotation feature (Android 9 / API 28+). This article covers key rotation mechanics, not general signing configuration or signing for non-Play distribution channels.

## Workflow or implementation guidance

Plan rotation as a release-blocking project with three phases.

Phase 1 - eligibility check. Rotation to a new key that uses the v3.1 scheme requires `targetSdk` and device coverage you must confirm first. Devices below Android 9 (API 28) verify only up to the oldest key in the lineage; devices below Android 13 (API 33) cannot consume a v3.1 rotation-targeted signing block that splits lineage per SDK version. If your `minSdk` is below 28, the rotated key must descend in an unbroken v3 chain or legacy devices will reject the update. Confirm Play App Signing enrollment: Program Management > App Signing in the Play Console must show an active app signing key held by Google, not "not enrolled."

Phase 2 - generate and register. Produce the new key in hardware or a managed KMS, never on a laptop disk. Export the certificate in the exact format the Console requests (an X.509 certificate, PEM or DER per the current form). For apps enrolled with an RSA key, the replacement certificate must use the same algorithm family Play accepts for your lineage; switching from RSA to EC in one rotation step is not supported by the v3 proof-of-rotation structure on older devices. Submit via Play Console > Setup > App Signing > "Request key upgrade" or "Rotate key," which triggers a Play-side re-signing pipeline. Play then serves: (a) the new-key-signed artifact to devices that accept the new lineage, and (b) lineage-aware artifacts where applicable.

Phase 3 - verify and continue signing updates with the upload key. After rotation, keep uploading updates signed with your current upload key. Play re-signs with the new app signing key. If your upload key is compromised, request an upload-key reset, which is a separate flow from app-signing-key rotation and is available at any time.

Store the lineage artifacts under the same backup discipline as the original key: the rotation certificate file, the KMS key reference, and the Play Console "app signing key certificate" DER download. Losing the upload key is recoverable; losing a not-yet-Google-held private key before registration is not.

## Controls

- Enroll in Play App Signing before you need rotation; you cannot rotate retroactively if you never enrolled and lost the key.
- Keep `minSdk` in mind when choosing scheme: full lineage verification requires API 28+; v3.1 per-SDK signing blocks require API 33+.
- Re-download the new app signing key certificate (DER) from the Console after rotation and update any backend pinning of the app's signing certificate (for example, signature checks in native code or server-side APK authenticity checks).
- Verify with `apksigner verify --print-certs --verbose` that the output shows the rotated key and, on tools that expose it, the lineage; `apksigner` reports the signer certificate lineage when present.
- Treat the upload key as replaceable and the app signing key as permanent-for-the-lineage; put renewal and rotation on a multi-year calendar rather than reacting to incidents.
- Never distribute a sideloaded build signed with the app signing key outside Play; keep one identity for Play distribution only.

## Validation evidence

Validation for this article is procedural: after a rotation in the internal testing track, install the previous production version, then accept the testing-track update on API 28, API 33, and API 35 devices or emulators. A successful in-place update (no uninstall prompt, data preserved) is the pass signal. Confirm the installed signer with `adb shell pm dump <package> | grep -A2 signatures` or `apksigner verify` on a pulled APK. Also verify a fresh install from Play on a clean device, and confirm your server-side signature checks (if any) accept the new certificate digest before full rollout. Run `bundletool validate` on any `.aab` you upload during the process to rule out signing-block formatting faults.

## Failure modes and correction

- "Upload key mismatch" on submission: you signed the `.aab` with a stale upload key after a reset. Re-sign with the new upload keystore; Play rejects only the artifact, not the release.
- Devices below API 28 refuse the update after rotation: the lineage cannot be proven to them. Correction is to keep a legacy-compatible chain: enroll a v3 lineage that begins at the original key so old devices still verify against the first certificate, and never rotate the base of the chain.
- Native code or SDK signature pinning breaks after rotation: the code pinned the old app signing certificate digest. Replace with the lineage's current certificate digest or key-hash check, and ship the fix before or with the rotation release.
- Rotation request stuck in review: rotation is a policy-reviewed operation; the Console shows a pending state. Do not delete and recreate the app to work around it - that loses installs and reviews permanently.
- Key generated outside an approved algorithm or size: generate the replacement with the same accepted parameters (for example RSA 2048+ or P-256) using `keytool` or your KMS; re-do the certificate export rather than fighting Console validation.

## Limitations

Rotation applies only to apps distributed through Play with App Signing enrolled; sideloaded, enterprise (MDM), and alternative-store distributions do not receive the rotated lineage and will treat a new key as a different app. Per-SDK v3.1 lineages depend on device OS support and Play's serving logic, so behavior on heavily-skewed device fleets needs empirical testing. The upload-key reset flow is independent and faster, and many "we need rotation" incidents are actually upload-key problems. Finally, this article does not cover key attestation integration or Play Integrity's signing-related verdicts.

## Canonical sources

- Android Developers - "Sign your app" / App signing: https://developer.android.com/studio/publish/app-signing (verified HTTP 200)
- Android Open Source Project - "APK Signature Scheme v3" (proof-of-rotation structure): https://source.android.com/docs/security/features/apksigning/v2 (verified HTTP 200; the APK signature schemes page family)
- Android Developers - apksigner reference (lineage verification output): https://developer.android.com/tools/apksigner (verified HTTP 200)
