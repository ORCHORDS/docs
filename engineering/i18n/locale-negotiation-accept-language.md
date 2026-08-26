# locale-negotiation-accept-language

**Issue:** Parsing and matching Accept-Language headers for server-side locale negotiation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
HTTP `Accept-Language` contains a quality-weighted list of preferred locales. Reading only the first tag ignores quality values and causes wrong locale selection.

## Pattern / Solution
Header format:
```
Accept-Language: fr-CH, fr;q=0.9, en;q=0.8, de;q=0.7, *;q=0.5
```
With `negotiator`:
```js
import Negotiator from 'negotiator';
import { match } from '@formatjs/intl-localematcher';

function negotiateLocale(req, supported, defaultLocale = 'en') {
  const headers = { 'accept-language': req.headers['accept-language'] ?? '' };
  const languages = new Negotiator({ headers }).languages();
  return match(languages, supported, defaultLocale);
}
```
BCP 47 lookup (RFC 4647): `fr-CH` -> try `fr-CH`, then `fr`, then default.

## Gotchas
- `*` wildcard means "any"; ignore it and fall back to default
- Quality `q=0` means "not acceptable"; exclude those tags
- `Accept-Language` is a hint -- always let users override via explicit preference

## Related
- `locale-detection-browser.md`
- `content-negotiation-vary-header.md`
- `locale-fallback-chain.md`
