# Android Passkey Creation and Credential Mediator Activities

Passkeys replace passwords with origin-bound WebAuthn credentials stored in a synced or device-local credential provider. On Android, the platform route for apps is the Credential Manager (`androidx.credentials`) API: the app requests passkey creation, the system surfaces a chooser (the "credential mediator") listing the available credential providers — Google Password Manager, third-party password managers, physical security keys — and the user completes creation in the chosen provider. The app's job is narrower and stricter than it looks: prove its identity (associated domains), construct a correct `CreatePublicKeyCredentialRequest` with a server-generated challenge, and handle the mediator's outcomes including user cancellation. This article covers the creation flow, the request JSON contract, mediator/provider behavior, and the failure modes.

## Scope

This article addresses Android passkey creation via Credential Manager: `CredentialManager.createCredential`, `CreatePublicKeyCredentialRequest` and its `requestJson` (WebAuthn `publicKey` creation options), `origin`/`ClientDataHash` for associated domains, provider mediation and the chooser UX, ActivityResult-based flows, and error handling (`CreateCredentialException` types). It covers the client half of the flow and its server contract. It does not cover the Web (navigator.credentials) flow, iOS equivalents, or the relying-party server's verification internals beyond what the client must send.

## Workflow or implementation guidance

The end-to-end creation flow has five parties: your app, the Credential Manager system service, the credential providers (mediators), the user, and your relying-party server. The sequence:

1. **Server issues the creation options.** The app requests a passkey-creation session; the server returns WebAuthn `publicKeyCredentialCreationOptions`: challenge (random, single-use, TTL-bounded), rp (id = your domain, e.g. `example.com`), user (id + displayName), pubKeyCredParams (algorithm list, typically ES256/RS256), authenticatorSelection (resident key required for passkeys, user verification preferred), excludeCredentials (existing credentials for this account, to avoid duplicates per provider).
2. **App calls Credential Manager.**
   ```kotlin
   val request = CreatePublicKeyCredentialRequest(requestJson)
   val result = credentialManager.createCredential(activityContext, request)
   val response = result.registrationResponseJson
   ```
   The `requestJson` is the server's options serialized (with a few client-side fields like `user.name` display data). On API 34+ with the system service (and via the Jetpack library on older levels), the system shows the chooser listing providers capable of creating a passkey for `rp.id`.
3. **Association gate.** The provider (not your app) enforces that your app is legitimately associated with `rp.id`: the Digital Asset Links statement (`assetlinks.json` at `https://example.com/.well-known/assetlinks.json`) must declare your app's package and signature fingerprint under the `get_login_creds` (and for passkeys, `delegate_permission/common.get_login_creds`) relation. Missing/incorrect association is the number-one cause of "create passkey" silently not appearing in the chooser — the provider filters you out before any UI shows.
4. **User completes creation in the mediator.** The chosen provider (with biometric/user verification per `authenticatorSelection`) generates the keypair, and returns the attestation/registration response JSON: credential id, authenticator attestation response (clientDataJSON including the challenge and origin, authenticatorData, attestationObject).
5. **App forwards to the server; server verifies and stores.** The client does no verification. The server validates the challenge (issued by it, unused, unexpired), verifies the origin/clientData (your app's origin or the `ClientDataHash`-mediated equivalent), checks attestation format, and stores the public key. From then on, the credential id is the account's passkey handle for authentication.

Engineering details that decide success:

- **Request JSON correctness.** The platform validates the JSON structurally; the providers validate semantically. Common defects: challenge not base64url-encoded per WebAuthn's bytes-as-base64url convention; `rp.id` set to the app package name instead of the domain (they are different things — domain is `example.com`, package is `com.example.app`); missing `pubKeyCredParams` (providers differ in algorithm support — include at least ES256 and RS256); `user.id` not base64url bytes.
- **`origin` and hash for native.** Web passkeys carry the site origin in clientDataJSON. Native apps use the app's asset-link-proven identity; with third-party password managers acting as providers, the request can carry an `ClientDataHash` so the RP server binds the ceremony to app-generated data — follow your provider-integration docs here; mismatched expectations surface as server-side verification failures, not client errors.
- **Cancellation is a first-class outcome.** `CreateCredentialCancellationException` means the user backed out; treat as "not now", offer the passkey button again later. `CreateCredentialInterruptedException`/`NoCredentialException`-family outcomes (for retrieval) and provider-specific `CreateCredentialUnknownException` need distinct UX: retry-able vs. report-able.
- **The chooser will also offer passwords.** Credential Manager unifies password and passkey flows; if your app also supports passwords, request types in priority order and design UI for "the user chose a password even though we suggested passkeys" — passkey-first, password-fallback is the standard posture.
- **Lifecycle:** launch from a foreground `Activity` context (the chooser is UI); on configuration change/activity recreation, the pending request is cancelled — anchor the flow to a user-visible step (a "Create passkey" button), not to screen load.

A worked example: a banking app adds passkey signup. Server issues options with challenge + `excludeCredentials` of the account's existing passkeys. App calls `createCredential`; the chooser offers Google Password Manager and the user's installed third-party manager. User picks, verifies with fingerprint; the provider creates the credential and returns registration JSON; the app POSTs it; the server verifies challenge/origin/attestation, stores the key, and marks the account passkey-capable. Next login, retrieval uses the sibling `getCredential` flow with `GetPublicKeyCredentialOption` — same provider machinery, reversed direction.

The duplicate-credential question is worth designing for: `excludeCredentials` prevents creating two passkeys in *one* provider, but users can legitimately create one passkey per provider (phone-synced + security key). Decide with product whether "Add another passkey" is a flow you expose, and track per-account credential inventory server-side.

## Controls

- Validate the `requestJson` in debug builds against a schema (challenge/rp/user/params present, base64url fields well-formed) so malformed server payloads fail loudly in QA, not as provider quirks in production.
- CI/release check: fetch the production `/.well-known/assetlinks.json` for every environment the build targets and assert package name + SHA-256 fingerprint match the signing cert of that build type (debug vs release fingerprints differ; staging builds need staging-domain associations).
- Error taxonomy in analytics: classify CreateCredential exceptions (cancellation vs interruption vs unknown) with provider attribution where available; rising "unknown" from one provider signals an integration break, not user behavior.
- Keep challenge TTL short (60–120 s) and single-use server-side; the client is untrusted transport for the challenge.
- Test on the provider matrix (Google Password Manager + major third-party managers) per release; provider behavior on algorithm lists and attestation formats varies at the margins.

## Validation evidence

- The Credential Manager API (`createCredential`, request/response types, exception taxonomy), the passkey creation request JSON contract (WebAuthn creation options fields, base64url conventions), and the Digital Asset Links association requirement for credential providers are documented in the Android Developers credential management and passkeys guides published by Google.
- The WebAuthn-level semantics (challenge, rp.id, pubKeyCredParams, authenticatorSelection, attestation response structure) are specified by the W3C Web Authentication specification, which the Android request JSON mirrors.
- A reproducible integration test: staging server issues options → app calls createCredential on a device with a provider enrolled → user completes → app forwards response → staging server verifies and returns success; then repeat with a deliberately missing assetlinks statement on a second staging domain and observe the provider filtering (no passkey option offered) — validating both the happy path and the association gate end-to-end.

## Failure modes and correction

- **Passkey option absent from chooser.** Cause: assetlinks mismatch (wrong fingerprint, missing relation, wrong domain). Correct by release-pipeline association checks per environment.
- **Server rejects registration.** Cause: origin/clientData mismatch or challenge reuse. Correct by verifying against the exact app-identity contract and single-use challenge store.
- **Silent failure on JSON defects.** Cause: base64url vs base64 confusion in `user.id`/challenge. Correct by debug-build schema validation and provider-matrix tests.
- **Flow dies on rotation.** Cause: request launched from a recreated activity's callback. Correct by anchoring to explicit user action and re-requesting after recreation.
- **Duplicate passkey confusion.** Cause: excludeCredentials misunderstood as global uniqueness. Correct by server-side credential inventory and deliberate multi-passkey UX.

## Limitations

- Provider availability varies by device/user (no enrolled provider ⇒ no passkey path; offer password fallback by design).
- Attestation conveyance and policy differ across providers; relying parties needing strong attestation must negotiate per provider, not assume.
- The API surfaces for passkeys require recent platform/Jetpack versions on older devices; capability-detect and degrade.
- Cross-app credential sharing (site + app using one passkey) depends on correct asset-link alignment on both sides — half-aligned setups half-work.

## Canonical sources

- Google, Android Developers — Integrate Credential Manager with passkeys (creation and retrieval flows, request JSON, error handling): https://developer.android.com/training/sign-in/passkeys
- W3C, Web Authentication: An API for accessing Public Key Credentials — Level specifications (creation options and registration response semantics): https://www.w3.org/TR/webauthn-3/
