# 3-D Secure Challenge UI Localization

**Issue:** When the issuer routes a 3-D Secure transaction to a challenge flow, the cardholder is handed off from the merchant checkout surface to an issuer-controlled or Access Control Server (ACS) controlled challenge window. That handoff is where cart abandonment spikes from roughly 2-5% on frictionless flows to 25-60% on poorly-localized challenge flows. Engineering a localized challenge experience means rendering in the cardholder's expected language and script, supporting the input methods required for that language (IME, diacritics, right-to-left flow), capturing the correct locale for the ACS, and accepting the issuer's authentication result back into the merchant state machine without losing the cart context. Localization is also not just translation: RTL flows require layout mirrors, certain scripts require non-Latin digit sets, and accessibility constraints apply across all of them.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Locale signaling

1. **Browser language headers are the most reliable signal.** Send `Accept-Language` to the 3DS Server on the AReq so the Directory Server can route to an ACS that supports the language. ISO 639-1 codes with optional regional variants (en-GB, fr-CA, pt-BR) are standard. The 3DS specification defines the language field as a 2-character language code from ISO 639-1, with optional region extension; consult your 3DS Server implementation for which forms it accepts.
2. **Cardholder billing country and card BIN both matter.** A card issued in Spain but used from a German IP without an `Accept-Language` header may default to the issuer's preferred language rather than the cardholder's. Where you have authoritative cardholder data (logged-in returning customer), prefer the stored locale; for guest checkouts the BIN-issuer locale is the fallback.
3. **ACS-rendered strings override merchant-rendered strings for the challenge itself.** The merchant cannot translate the OTP entry page because the issuer owns that surface. Localization work in the merchant flow is about the transition — wrapping the iframe, sizing the modal, surfacing an explanation in the cardholder's locale before handoff, and recovering the result without reloading the page in a different language.

## Script and input handling

1. **Latin-1 is not enough.** Cards issued in Greece, Russia, Bulgaria, and the CJK economies require non-Latin-1 character sets for cardholder names, OTP messages, and one-time passcode UI. Render the challenge frame with UTF-8 encoding and a font stack that covers the script. RTL languages (Hebrew, Arabic) require mirrored layouts and right-aligned text where the issuer's iframe does not impose its own directionality.
2. **OTP entry input methods.** Mobile authenticator apps and SMS-delivered one-time codes arrive in Latin or native script depending on issuer. The challenge input field should accept the exact characters delivered; validate length only after locale normalization. Numeric-only fields with length validation rejecting leading zeros or non-ASCII digits are a structural UX failure.
3. **Font fallback in iframes.** Many issuers render challenge content in a sandboxed iframe; fonts the merchant loads do not propagate. Choose a system font stack in the parent frame, and accept that the ACS iframe may render in its own font. Visual harmony is less critical than readable OTP entry.

## Accessibility constraints

1. **WCAG 2.1 AA on the merchant-owned handoff.** The button that opens the challenge modal, the loader shown during handoff, and the recovery of the result back into the merchant flow are merchant surfaces and must meet contrast, focus order, and screen reader announcement requirements. The ACS iframe is out of merchant scope but the parent frame and the messages surrounding the iframe are not.
2. **Keyboard navigation across the iframe boundary.** Focus moving into a cross-origin ACS iframe cannot be programmatically controlled by the parent. Provide a visible "Return to merchant" affordance after the iframe posts back, and a non-modal explanation that screen readers can announce when focus is on the wrapper.
3. **Timeouts and grace periods.** The 3DS specification caps challenge timeouts. A merchant surface that hides the iframe on timeout without an explanatory message leaves the cardholder at the issuer screen with no path forward. Implement an outer timeout in the merchant shell that returns the user to a recoverable state (cart preserved, retry button surfaced) instead of a hard error.

## Failure modes

1. **Locale routing the cardholder to an unsupported language.** The Directory Server returns an ACS in the requested locale only if one exists. For a minority language, the fallback is the issuer's default language (often English). Engineering cannot fix this; it must measure abandonment by locale, identify the population for whom fallback is a structural barrier, and choose either a checkout-time locale preview that warns the cardholder or a non-3DS alternative where exemption applies.
2. **Frame-busting or cookie restrictions.** Some issuers require third-party cookies; Safari's ITP and Firefox's Enhanced Tracking Protection block them. The merchant cannot override these settings, but the implementation should test the challenge flow on the dominant browser/OS pairs in the target market before declaring localization complete.
3. **State machine loses cart context.** A challenge flow that closes the parent tab, reopens the merchant in a fresh window, or strips cart parameters during the postMessage handoff creates abandonment even when the authentication succeeds. The state recovery must use signed state tokens that survive the iframe postMessage round-trip and do not depend on cookies alone.

## Canonical sources

1. EMVCo, EMV 3-D Secure Protocol and Core Functions Specification, latest published version. https://www.emvco.com/emv-technologies/3d-secure/
2. W3C, Web Content Accessibility Guidelines (WCAG) 2.1, W3C Recommendation. https://www.w3.org/TR/WCAG21/
