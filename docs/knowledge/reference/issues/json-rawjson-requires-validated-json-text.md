# JSON.rawJSON Requires Validated JSON Text and Context

**Issue:** `JSON.rawJSON()` embeds validated primitive JSON text during stringification. Treating it as a general object fragment or string-escaping bypass creates type and composition errors.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Accept raw JSON only from a trusted serializer that produces the intended primitive grammar.
- Keep untrusted strings as ordinary strings; never prequote them to force raw insertion.
- Validate the resulting document against the consumer schema.
- Record runtime support and use one reviewed compatibility path.
- Keep HTML/script embedding escaping separate from JSON validity.

## Verification
- Test numbers, strings, booleans, null, whitespace, objects, arrays, malformed text, huge numeric literals, and script-context characters.
- Round-trip through `JSON.stringify` and the consuming parser/schema.
- Assert ordinary user text remains quoted and escaped.

## Gotchas
Raw JSON is not arbitrary structural splicing; object and array text is rejected. A valid JSON document can still be unsafe when embedded unescaped in HTML.

## Official sources
- [ECMAScript JSON.rawJSON](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.rawjson)
