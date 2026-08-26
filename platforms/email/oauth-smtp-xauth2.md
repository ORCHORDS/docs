# oauth-smtp-xauth2

**Issue:** Application mail was historically sent by SMTP with a plain username/password (or Gmail "app password") against `smtp.gmail.com` or `smtp.office365.com`. That era is closing: Microsoft is retiring Basic authentication for SMTP AUTH client submission (phased rejections from March 1, 2026, 100% rejection by April 30, 2026, disabled by default by end of December 2026), and Google has pushed Gmail toward OAuth 2.0 with app passwords as a 2FA-gated second-class option. Any system still relaying through Gmail or Microsoft 365 with basic credentials needs to move to OAuth 2.0 with the XOAUTH2 SASL mechanism — or deliberately migrate to a true transactional ESP — before the deadline breaks outbound mail.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why basic-auth SMTP is ending

1. **Microsoft has a published, dated retirement.** Exchange Online's client-submission SMTP AUTH (`smtp.office365.com:587` with username/password) is being deprecated: Basic auth rejections begin phasing in March 1, 2026, reach 100% by April 30, 2026, and Basic auth for SMTP AUTH is disabled by default for existing tenants by end of December 2026 (Microsoft Tech Community, "Updated Exchange Online SMTP AUTH Basic Authentication Deprecation Timeline").
2. **App passwords die with it on the Microsoft side.** Anything relying on an Entra ID app password or plain credentials for SMTP AUTH stops working on the same schedule — including printers and legacy apps, which Microsoft steers toward Direct Send (anonymous MX submission) or connectors instead.
3. **Gmail already treats passwords as the exception.** Consumer Gmail requires 2FA to even create an app password, and Google's documented path for SMTP/IMAP automation is OAuth 2.0 with XOAUTH2; app passwords can also be invalidated by security policies without warning.
4. **Credential hygiene is the driver.** Static SMTP passwords in config files and env vars are a standing breach surface and a compliance finding; short-lived OAuth tokens remove the long-lived shared secret from your infrastructure.
5. **Decide: relay-with-OAuth or move to an ESP.** XOAUTH2 through Gmail/M365 is fine for low-volume internal/notification mail; product transactional volume belongs on SES/SendGrid/Postmark/etc. with proper SPF/DKIM/DMARC — OAuth changes the credential, not the deliverability math of relaying from a consumer/tenant mailbox.

## XOAUTH2 mechanics

1. **It is a standard SASL mechanism.** The SMTP client authenticates with `AUTH XOAUTH2`, sending a base64-encoded string of the form `user=<address>\x01auth=Bearer <access-token>\x01\x01` — the password is replaced by an OAuth access token, nothing else about the SMTP conversation changes.
2. **Hosts and ports stay familiar.** Gmail: `smtp.gmail.com` on 587 (STARTTLS) or 465 (implicit TLS); Microsoft 365: `smtp.office365.com` on 587 with STARTTLS — same endpoints, new `AUTH` mechanism.
3. **The token is the OAuth access token, not the refresh token.** Access tokens live roughly 3600 seconds for Google and about 60–90 minutes for Microsoft; putting a refresh token in the SASL string fails with a permanent authentication error.
4. **Failure responses look like SMTP errors.** Gmail returns `535-5.7.8` with an extended base64 JSON blob (e.g. `invalid_grant`) for bad/expired tokens; Microsoft returns `535 5.7.139 Authentication unsuccessful`. Parse the blob — the error string distinguishes expired token from revoked consent from wrong scope.
5. **Most mail libraries support it natively.** Nodemailer (`type: 'OAuth2'`), Python `smtplib` (build the XOAUTH2 string manually or via `auth_string` helpers), MailKit/SMTP.js, and Postfix (via `smtp_sasl_oauth2` mechanisms) all ship XOAUTH2 support — no custom protocol code required.

## Google (Gmail) setup

1. **Create an OAuth client in Google Cloud Console.** An OAuth 2.0 client ID/secret for a Web or Desktop application; no Gmail API enablement is needed for pure SMTP submission, though the Gmail API path is the alternative (REST `messages.send`) if you would rather skip SMTP entirely.
2. **Pick the narrowest scope.** `https://www.googleapis.com/auth/gmail.send` covers SMTP send and Gmail API send; `https://mail.google.com/` grants full mailbox access and should be avoided for send-only relays — narrower scopes reduce both blast radius and the Google security-review burden.
3. **Exchange a one-time authorization code for a refresh token.** Run the consent flow once (adding your test user as a test user while the app is in testing mode), capture the `refresh_token`, and store it as the single long-lived secret — access tokens are minted from it at runtime.
4. **Refresh proactively and cache the access token.** Request a new access token when the cached one is within a few minutes of its `expires_in` (≈3599s), and reuse the same token across many SMTP sessions; minting a fresh token per message wastes quota and races Google's rate limits.
5. **Service accounts do not work without domain-wide delegation.** A bare service-account token gets a `555` error from Gmail SMTP; in Google Workspace you must grant the service account domain-wide delegation with the mail scope — consumer Gmail accounts cannot use service accounts for this at all.
6. **Expect refresh-token revocation events.** Consumer-account password changes, revocation from the Google Account security page, or 6 months of non-use can invalidate the refresh token; monitor for `invalid_grant` and re-run consent before outbound mail silently stops.

## Microsoft 365 setup

1. **Register an app in Microsoft Entra ID.** Create the app registration, and choose delegated (Authorization Code flow, a real user mailbox) or application (Client Credentials flow, app-only) permissions depending on whether one mailbox or a service identity is sending.
2. **Grant `SMTP.Send` and consent it.** The required scope/permission is `https://outlook.office365.com/SMTP.Send` (delegated or application permission); request tokens from the v2 token endpoint with this scope — a token without it authenticates then fails `MAIL FROM` with `535 5.7.3`.
3. **Client-credentials senders need SMTP AUTH enabled.** Application-permission sending still requires SMTP AUTH enabled on the mailbox being used, and the app must be allowed by any tenant `ApplicationAccessPolicy` — common silent failure in locked-down tenants.
4. **Acquire and cache tokens via MSAL.** MSAL (or plain OAuth2 token requests with client secret/certificate) returns an access token for the `smtp.office365.com` resource; cache it until near-expiry exactly as with Google.
5. **The username in XOAUTH2 is the mailbox.** For delegated flow it is the signed-in user's UPN; for client credentials it is the mailbox being sent from — the token proves authorization, the `user=` field selects the mailbox.

## Operational gotchas

1. **Refresh races under concurrency.** When several workers detect expiry simultaneously, they each hit the token endpoint; the losing token response can revoke the previous refresh token on some providers. Serialize refresh behind a lock or a single token-service endpoint.
2. **Scopes are per-token, not cumulative.** Requesting `gmail.send` after previously consenting `mail.google.com` yields a token with only `gmail.send`; if code assumes broader access it fails confusingly. Store which scope each credential was granted.
3. **Alert on authentication, not just on send failure.** A revoked refresh token manifests as every message failing with `535`/`invalid_grant`; a monitor that pages on the first auth failure prevents the "outbound mail has been down for two weeks" incident.
4. **Keep a tested basic-auth-free rollback path.** The safe fallback is a second registered OAuth client (or a transactional ESP API key) — not the old password, which is exactly what is being retired.
5. **Log token expiry, never tokens.** Access tokens are bearer credentials; keep them out of SMTP debug logs (Nodemailer/MailKit debug output includes the AUTH exchange) by redacting `AUTH XOAUTH2` lines in log pipelines.
