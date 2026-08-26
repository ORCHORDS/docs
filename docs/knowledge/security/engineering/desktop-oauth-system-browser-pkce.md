# Desktop OAuth: system browser, PKCE, and callback validation

**Category:** Security
**Author:** ORCHORDS
**Source:** [example project architecture rules](https://github.com/example-org/example-repo)

## Problem

Embedding a provider login page in a desktop renderer weakens the browser security boundary and commonly breaks provider policies. A desktop authorization-code flow still needs correlation and proof that the callback belongs to the initiating request.

## Practice

- Start authorization in the user's system browser, not an embedded popup.
- Use authorization code flow with PKCE using the S256 challenge method.
- Generate a high-entropy state value per attempt, persist it only for the pending authorization, and verify it before exchanging the code.
- Bind the callback listener or registered deep link to a short-lived, single-use transaction.
- Store tokens in an OS-appropriate protected store; never pass refresh tokens into untrusted renderer code.
- Provide a clear cancellation and expiry path that destroys the pending state.

## Verification

1. Complete a normal authorization and confirm the state is consumed once.
2. Submit a callback with an altered, expired, or reused state; it must be rejected before token exchange.
3. Confirm a renderer cannot read raw refresh tokens.
4. Test cancellation and provider-denial flows without leaving a reusable pending callback.

## Failure modes

- An embedded webview captures credentials or conflicts with the provider's security model.
- Missing state validation permits login-CSRF or account-linking attacks.
- Reusable callbacks or exposed tokens allow authorization replay.
