# HTTP Content-Language representation metadata

**Issue:** A response copies the request's Accept-Language value into Content-Language, lists every language appearing in the document, or omits the header after serving a negotiated translation. Caches, accessibility tooling, search systems, and downstream clients then receive misleading representation metadata.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

RFC 9110 defines Content-Language as the natural language or languages of the intended audience for the representation. It is representation metadata. It is not a transcript of request preferences, proof of translation quality, or a list of every language fragment contained in the body.

Use it when the server knows the intended audience language of the selected representation. Omit it when the representation is not intended for a particular natural-language audience.

## Controls and implementation

1. Set Content-Language from the canonical language tag attached to the selected representation, not by echoing Accept-Language.
2. Use well-formed language tags and emit multiple tags only when the representation is intentionally for multiple linguistic audiences. A quotation or navigation label in another language does not automatically make the whole response multi-language.
3. Keep document-level declarations synchronized where applicable, such as HTML's lang attribute. Use element-level language markup for embedded passages rather than expanding the HTTP header.
4. Separate negotiation from metadata. Accept-Language can influence selection; Content-Language describes what was selected. Record both values independently for diagnostics.
5. Configure cache keys for the actual selection mechanism. If a shared response varies on Accept-Language, send the appropriate Vary field or use locale-specific URLs. Content-Language alone does not partition a cache.
6. Preserve the header on 304 and transformation paths according to HTTP metadata rules. CDN, compression, and edge-rendering layers must not replace it with their own default locale.
7. Do not use Content-Language as authorization, jurisdiction, geolocation, or currency input. These require separate authoritative signals.
8. For APIs whose body contains language-neutral structured data plus localized fields, document whether the header describes the whole representation or move language tags beside the localized values.

## Verification

Test explicit locale URLs, header negotiation, user-profile and cookie selection, default fallback, bilingual content, untranslated fragments, 304 revalidation, CDN hits, compression variants, error pages, redirects, and responses with no intended audience language.

Assert the header matches the actual selected bundle, the HTML root language, and cache behavior. Vary request preferences while holding the selected representation constant and confirm metadata remains representation-derived.

## Gotchas

- Content-Language can contain a list; it does not mean one value per paragraph.
- A server default is not necessarily the user's preferred language, but it is still the representation's intended language if served as such.
- The header does not replace accessible language markup inside HTML.
- Setting Vary: Accept-Language without normalization can create excessive cache cardinality.

## Official sources

- [RFC 9110 — Content-Language](https://www.rfc-editor.org/rfc/rfc9110.html#name-content-language)
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647.html)
