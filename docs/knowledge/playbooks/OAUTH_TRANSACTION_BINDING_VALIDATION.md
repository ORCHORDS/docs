# OAuth Transaction Binding Validation

## Trigger
Run before releasing OAuth/OIDC client flows, after authorization/callback/session changes, after identity-provider/client-library upgrades, and during periodic authentication-protocol review.

## Inputs
- OAuth/OIDC client flow definitions.
- PKCE, `state`, and OIDC `nonce` implementation details as applicable.
- Browser/user-agent session binding design.
- Authorization callback and token-exchange handlers.
- Safe test client/provider environment.

## Procedure
1. Document which transaction-binding controls apply to each authorization flow: PKCE, OAuth `state`, OIDC `nonce`, or another protocol-defined mechanism.
2. Verify client-generated transaction values are produced with sufficient unpredictability and are specific to one authorization transaction.
3. Verify the client binds the transaction values to the originating client instance and user-agent/session context.
4. Complete a normal authorization flow and confirm callback and token-exchange validation consume the expected transaction state.
5. Send a callback with a missing transaction-binding value and confirm rejection before authenticated application state is established.
6. Send a callback with a value generated for a different transaction or browser session and confirm rejection.
7. Start two parallel authorization attempts and swap callback values between them; confirm neither flow accepts the other transaction’s binding state.
8. Replay a previously accepted callback or binding value and confirm it cannot be reused to authenticate a new transaction.
9. For authorization-code flow using PKCE, send an incorrect `code_verifier` and confirm token exchange fails.
10. For OIDC, test an incorrect `nonce` where applicable and confirm the response is rejected.
11. Review logs/diagnostics and confirm transaction secrets are not unnecessarily exposed.
12. Record findings, remediate, and repeat the failed binding/replay cases.

## Escalation
Escalate callback acceptance without same-session transaction proof, reusable or guessable transaction values, cross-flow swaps, replay acceptance, or continuation after binding validation fails.

## Evidence
- Flow/control mapping.
- Normal authorization result.
- Missing/wrong binding tests.
- Parallel-flow swap test.
- Replay test.
- PKCE mismatch test.
- OIDC nonce mismatch test where applicable.
- Logging/diagnostic review.

## Completion criteria
Authorization responses and token exchanges are accepted only when securely bound to the transaction and user-agent/session that initiated them, with replay and cross-transaction substitution rejected.

## Source basis
- OWASP ASVS 5.0.0 requirements V10.1.2 and V10.2.1: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv
