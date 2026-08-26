# Compression Dictionary Transport safe rollout

**Issue:** Versioned JavaScript, CSS, WASM, and templated responses often differ only slightly, but dictionary compression can cause cache corruption or content failure if negotiation and dictionary identity are mishandled.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Start with immutable, same-origin versioned resources whose previous versions have high byte similarity. Keep ordinary Brotli/gzip and uncompressed fallbacks.
- Advertise a dictionary with `Use-As-Dictionary` and a narrow match pattern. When the client sends `Available-Dictionary`, verify its SHA-256 value before selecting `dcb` or `dcz`.
- Return the matching `Content-Encoding` and include `Vary: accept-encoding, available-dictionary` on cacheable dictionary-compressed responses.
- Treat `Dictionary-ID` only as a lookup accelerator; it never replaces hash validation.
- Observe browser compatibility, compression CPU, dictionary hit rate, transfer bytes, decompression failures, and CDN cache-key cardinality.

## Verification

1. Byte-compare decoded dictionary-compressed responses to canonical uncompressed artifacts.
2. Test absent, stale, wrong-hash, and malicious Dictionary-ID/Available-Dictionary combinations.
3. Verify CDN and browser caches cannot serve a dictionary variant to a client lacking that exact dictionary.
4. Exercise CSP, CORS, same-origin, private-browsing, and cookie-disabled conditions.
5. Roll a new application version, retain needed dictionaries long enough, then confirm old clients fall back cleanly after retirement.

## Gotchas

The feature has limited browser availability and should be progressive. Dictionaries and dictionary-compressed resources face origin/privacy restrictions. A broad match pattern may bind unrelated or sensitive resources. Compression of secret-bearing responses can amplify side-channel risk; restrict the rollout to public immutable assets first.

## Sources

- [RFC 9842: Compression Dictionary Transport](https://www.rfc-editor.org/rfc/rfc9842.html)
- [MDN: Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)
