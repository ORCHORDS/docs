# OAuth device authorization: bounded polling and phishing-resistant UX

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [RFC 8628: OAuth 2.0 Device Authorization Grant](https://datatracker.ietf.org/doc/html/rfc8628)

## Scope

Use the device authorization grant only for devices that cannot practically host a browser-based authorization flow or accept an authorization callback, such as televisions and input-constrained appliances. It is not a replacement for normal native-app browser authorization.

## Practice

- Begin a device flow only after an explicit user action; do not start polling automatically at application launch.
- Display the authorization server's verification URI and the user code accurately, with a clear indication of the requesting client and requested scope.
- Treat device codes and user codes as short-lived, single-use secrets. Never log them or include them in telemetry.
- Poll no faster than the server-provided interval (or the specified default), and apply the server's slow-down response by increasing delay.
- Stop immediately on expiry, denial, or terminal error. Retire the pending transaction and require a fresh user start.
- Rate-limit user-code entry and monitor abuse without revealing whether a particular code is valid.

## Verification

1. Confirm a normal approval yields a token only once and only before expiry.
2. Confirm cancellation, expiry, and denial stop polling and leave no active transaction.
3. Simulate slow-down responses and verify the client increases its interval.
4. Confirm the sign-in page shows enough origin and client context for a user to detect a phishing attempt.

## Failure modes

- Starting a device flow automatically creates unnecessary polling load and confusing prompts.
- Excessive polling overloads the token endpoint.
- Long-lived or logged device codes make remote phishing and replay easier.
- Using device flow on a capable native app degrades the security and usability of the standard browser-based flow.

## Related

- [RFC 8628](https://datatracker.ietf.org/doc/html/rfc8628)
