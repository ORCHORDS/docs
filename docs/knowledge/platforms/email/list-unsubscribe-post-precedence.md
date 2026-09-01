# List-Unsubscribe-Post Header Precedence

Two unsubscribe mechanisms now compete for the same click. The older one is the mailto: URI in the List-Unsubscribe header: the client composes an email, or the provider relays one, and the sender's inbound pipeline processes it. The newer one is RFC 8058's one-click: the List-Unsubscribe-Post header tells the provider that an HTTPS POST with a fixed body performs the unsubscribe directly, and the provider surfaces a single-action button in its UI. When both exist for the same message - and most bulk mail now carries an HTTPS one-click URI alongside a mailto: fallback - something must decide which fires, in what order, and what happens when they disagree. That decision is precedence, governed by a mix of specification rules, provider UI behavior, and sender-side consistency obligations.

## Scope

This article covers precedence between the RFC 8058 one-click POST mechanism and other unsubscribe paths - mailto: URIs, HTTPS GET web links, and mailbox-provider unsubscribe services built atop these headers. It addresses receiver-side ordering rules and sender-side obligations keeping concurrent mechanisms consistent. It does not cover base List-Unsubscribe syntax, CAN-SPAM unsubscribe timing law, preference-center architecture, or RFC 8058's core POST semantics beyond what precedence requires.

## Workflow or implementation guidance

Precedence is decided at four layers; each has a defined rule and failure behavior.

**Layer 1 - Provider capability gate.** A provider offers its one-click UI only when the message satisfies RFC 8058's preconditions: a List-Unsubscribe-Post header carrying exactly `List-Unsubscribe=One-Click`, a companion List-Unsubscribe containing an HTTPS URI, and a DKIM signature covering both headers. Fail any precondition and the provider falls back to older behavior - a plain unsubscribe action against the mailto: URI, or no UI at all. The sender does not choose which mechanism fires; the sender chooses which mechanisms are available, and the capability gate picks.

**Layer 2 - One-click before mailto.** Where both a conforming HTTPS URI and a mailto: URI are present, providers that support one-click act on the POST and do not simultaneously send the mailto. The mailto is the fallback for clients and providers that never implemented RFC 8058. Senders must treat this as eventual consistency, not exclusivity: the mailto may still arrive minutes or days later for the same recipient, processed by a different code path, and suppression state must already reflect the one-click action.

**Layer 3 - POST versus web GET.** The HTTPS URI in the header is the same URL a user might reach through a footer link in the rendered body. A one-click POST and a user's browser GET against the same endpoint must produce the same outcome - an unsubscribed recipient - even though the requests differ in method, headers, and authentication context. Endpoints that only handle form POSTs and redirect GETs to a confirmation page break this equivalence, and the breakage surfaces as "I clicked unsubscribe in the provider's UI and still get mail."

**Layer 4 - Sender-side arbitration.** With up to three channels able to deliver an unsubscribe event for one message - provider POST, mailto arrival, web session - the sender needs idempotent arbitration: one canonical action per (recipient, list) pair, first event wins, later events acknowledged without side effects. Confirmation emails are sent at most once, and never in response to the one-click POST itself.

Operationally, the published header set is a precedence declaration. One-click plus mailto says "prefer POST, mailto is fallback." Only mailto opts out of provider one-click UIs entirely. An HTTPS URI without List-Unsubscribe-Post leaves the URI as a GET target only - a middle state inviting the layer-3 equivalence problem without granting the one-click UI.

## Controls

- Header consistency lint: List-Unsubscribe-Post present implies exactly one HTTPS URI in List-Unsubscribe, both headers signed in `h=`.
- Endpoint equivalence test in CI: the same token exercised via POST and via browser GET, asserting identical suppression outcomes.
- Idempotency key per (recipient, list), with duplicate-event counters detecting providers double-firing.
- Single-confirmation rule: no confirmation email triggered by one-click POSTs.
- Fallback monitoring: mailto unsubscribe arrivals tracked alongside POSTs per provider, the ratio watched for behavior shifts.
- Token scope validation: the one-click token names exactly one list, preventing precedence races from over-unsubscribing.
- Audit log recording channel of origin - post, mailto, web - for every unsubscribe event, retained for consent disputes.

## Validation evidence

- Message fixtures with four header configurations (both, post-only, mailto-only, https-without-post) submitted to provider test inboxes, with evidence of which UI each produced.
- Duplicate-event test: a one-click POST followed by the same recipient's mailto 30 minutes later, asserting one suppression row and zero duplicate confirmations.
- GET/POST equivalence results across the endpoint's deployed versions.
- Signature-coverage test: both headers removed from `h=` in a control message, confirming the one-click UI disappears.
- Per-provider channel-mix telemetry over a sustained window showing post-to-mailto ratio stability.
- Consent-dispute export demonstrating channel-of-origin attribution for sampled unsubscribe events.

## Failure modes and correction

The signature-coverage defect - headers added after DKIM signing - silently downgrades every affected message to the mailto path; fix the injection order and monitor the channel mix, which shifts visibly when coverage breaks. Users reporting "unsubscribed but still receiving" after clicking the provider's button usually hit layer-3 inequivalence: the POST suppressed one list while the footer GET pointed at another, or the GET redirected to a confirmation page never completed; unify token scopes and remove redirect chains. Duplicate unsubscribes across lists from a single click mean the token encoded too broad a scope; narrow it. A provider suddenly sending mailto where it previously sent POSTs indicates either your coverage failure or a provider policy change - the channel-mix control distinguishes them, since your defect shifts the ratio across all providers at once. Confirmation emails triggered by one-click POSTs violate the no-additional-interaction posture; suppress them at the response layer. Total absence of any unsubscribe event for a user who clicked points at token-delivery failure between provider and endpoint; check receipt logs before list state.

## Limitations

Precedence rules are enforced by each provider's implementation, and behavior varies: some verify DKIM coverage strictly, others loosely; some expose one-click UIs only above reputation thresholds; some built their unsubscribe services atop these headers in ways the specifications do not describe. The sender cannot observe which mechanism a provider used except through channel-of-origin logs. Mailto processing remains necessary indefinitely, since support for RFC 8058 is universal neither at the UI nor enforcement level. Header precedence says nothing about legal sufficiency, a consent-law question. Cross-list token scoping constrains UX - a user wanting all-lists unsubscribe needs a broader flow - and the one-click contract's statelessness leaves the sender reconstructing context entirely from the token.

## Canonical sources

- [RFC 8058: Signaling One-Click Functionality for List Email Headers](https://www.rfc-editor.org/rfc/rfc8058.html)
- [RFC 2369: The Use of URLs as Meta-Syntax for Core Mail List Commands (List-Unsubscribe)](https://www.rfc-editor.org/rfc/rfc2369.html)
- [RFC 6376: DomainKeys Identified Mail (DKIM) Signatures](https://www.rfc-editor.org/rfc/rfc6376.html)
- [RFC 8058 (IETF Datatracker record)](https://datatracker.ietf.org/doc/rfc8058/)
- [M3AAWG: sender best practices and published documents](https://www.m3aawg.org/published-documents/)
