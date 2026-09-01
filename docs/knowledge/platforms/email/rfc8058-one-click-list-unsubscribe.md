# RFC 8058 One-Click List-Unsubscribe Mechanics

**Issue:** Email clients that surface unsubscribe as a single button rather than a mailto link depend on RFC 8058's `List-Unsubscribe-Post` header, and senders who omit the header silently degrade the user experience into the multi-step unsubscribe flow that mailbox providers are progressively deprioritizing. Operators who treat unsubscribe headers as a one-time compliance task rather than an active part of their sending infrastructure miss the deliverability signals that mailbox providers use to score sender reputation.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Two Headers Together

RFC 8058 specifies that a message carrying an unsubscribe path must include two headers. The legacy `List-Unsubscribe` header carries one or more URI(s) enclosed in angle brackets, each URI being either a `mailto:` URL or an HTTPS URL. The newer `List-Unsubscribe-Post` header carries a single body value: `List-Unsubscribe=One-Click`. When both headers are present and the HTTPS URI is reachable, a compliant email client can offer the recipient a one-click unsubscribe experience that issues a single HTTPS POST request without requiring the user to compose a message or visit a confirmation page.

The two headers must be present on the same message; one without the other is non-compliant. A sender that ships `List-Unsubscribe: <https://example.com/u>` without `List-Unsubscribe-Post: List-Unsubscribe=One-Click` will see clients continue to render the legacy unsubscribe link rather than a button. Conversely, a sender that ships only the `List-Unsubscribe-Post` header without an HTTPS URI in `List-Unsubscribe` is non-compliant and clients ignore the post header.

## The HTTPS POST Endpoint

The endpoint declared in `List-Unsubscribe` must accept an HTTPS POST with the recipient address in a structured body. RFC 8058 leaves the body format to the sender, defining only that the body should identify the recipient and that the response should indicate the unsubscribe result. Common body formats are URL-encoded form data with `email` and `token` fields, or a JSON object with the same fields. The token is typically a per-recipient secret that prevents third parties from triggering an unsubscribe on someone else's behalf.

The endpoint must respond within a short window; mailbox providers may cancel the request if it takes more than a few seconds. The endpoint should not require authentication beyond the recipient-bound token, and it should not require a CAPTCHA or a JavaScript-rendered confirmation page. A 200 OK with a small JSON body is the standard response; a 4xx error indicates the token is invalid or expired, which the client surfaces to the user as "unable to unsubscribe". Avoid 3xx redirects, as the client may not follow them and the unsubscribe will appear to fail.

## Mailto Compatibility

Some senders support both HTTPS one-click and mailto-based unsubscribe for older clients. The mailto URI in the legacy header must accept a POST from the user; the message body typically contains a subject line like "unsubscribe" and is sent to an unsubscribe handling address. The mailto path requires human action, which is why RFC 8058 exists: it moves the unsubscribe to a single automated POST that mailbox providers can trigger on the recipient's behalf.

When both modes are supported, the sender must deduplicate unsubscribes. A user who clicks the button (HTTPS POST) and then falls back to the mailto path will appear twice in the unsubscribe queue. The unsubscribe endpoint should be idempotent: a second POST from the same address is a no-op and the response is the same as the first. Idempotency is also important for retry handling: a network blip may cause the client to retry, and the second attempt must not produce an error.

## Gmail And Other Provider Behavior

Gmail requires `List-Unsubscribe-Post` for senders above a certain volume threshold, and surfaces the unsubscribe button at the top of the message. The button triggers an HTTPS POST to the URI in `List-Unsubscribe`. Gmail also reports the unsubscribe signal to the sender's reputation score: a sender whose unsubscribe rate is unusually high may be flagged for review. The senders that benefit most from RFC 8058 compliance are bulk senders whose recipients actively use the unsubscribe button; the deliverability cost of being non-compliant has risen steadily since 2024.

Yahoo, Microsoft, and Apple Mail have similar requirements, with varying tolerances for legacy mailto-based unsubscribe. Apple Mail in particular enforces strict adherence to RFC 8058's HTTPS POST requirement and ignores mailto when one-click is offered. A sender that wants the broadest client compatibility must implement HTTPS one-click unsubscribe with a token-based endpoint and a short response time.

## Failure Modes

The most common failure is the HTTPS endpoint returning a non-2xx status when the token is valid. Mailbox providers interpret a 4xx or 5xx as a failed unsubscribe and may report a complaint to the spam feedback loop instead. The sender should ensure the endpoint returns 200 OK for any successful unsubscribe, including the idempotent case. Error cases should return a 4xx with a clear body, and the body should be machine-readable so the client can surface a meaningful message to the user.

A second failure is the endpoint requiring authentication that the client cannot provide. Some senders add an API key or HMAC header that they expect the client to compute; the client cannot do this, and the request fails. The only authentication the client can provide is the recipient-bound token in the body, and the endpoint must validate the token without requiring any additional authentication. Adding extra authentication transforms the one-click experience into a multi-step experience and defeats the purpose of the header.

A third failure is the endpoint timing out under load. Bulk unsubscribe events triggered by Gmail or Microsoft can produce bursts of hundreds of requests per second; an endpoint backed by a slow database or an unscaled container will time out, and the clients will retry. The retry storm further amplifies the load. Provision the endpoint for peak burst traffic, use a cache for token validation, and treat the endpoint as critical infrastructure with the same monitoring and alerting as the sending pipeline itself.

## Canonical sources

1. https://www.rfc-editor.org/rfc/rfc8058
2. https://www.rfc-editor.org/rfc/rfc8058#appendix-A