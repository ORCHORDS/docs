# Android App Links dynamic rules and verification

**Issue:** Deep-link routing often changes faster than a mobile release. Android 15+ can merge server-delivered rules with the app's declared App Link scope, but a malformed or overly broad statement can route the wrong URLs or silently fall back to the manifest.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## What is authoritative

Android verifies a host through `.well-known/assetlinks.json`. On Android 15+ devices with Google services, `dynamic_app_link_components` can refine matching by path, fragment, and query parameter. Those dynamic rules do **not** expand the scheme/host scope declared in the installed app manifest.

## Safe implementation

- Keep the manifest declaration broad enough only for the hosts the app owns; use dynamic rules to refine paths.
- Publish one unambiguous dynamic-rule object for each site/relation/app combination.
- Order rules from specific allow cases to broad exclusions or fallback rules: evaluation stops at the first match.
- Treat malformed or empty dynamic rules as a safe fallback case—Android discards them and uses the static manifest rules.
- Serve `assetlinks.json` over HTTPS, without redirects, as `application/json`; publish it independently on every supported host.
- Use the production signing certificate fingerprint when Play App Signing is enabled; a locally generated signing fingerprint can differ from the distributed app's fingerprint.
- Test both Android 15+ (dynamic rules) and Android 14 and earlier (which ignore the extension), plus browser fallback and unauthenticated access to the well-known file.

## Operational checks

1. Validate the hosted JSON and its response headers from the public internet.
2. Compare declared app-package IDs and certificate fingerprints with the release configuration.
3. Exercise allowed, excluded, unlisted, query-qualified, and fragment-qualified URLs on physical or emulator devices.
4. Roll out a restrictive rule change with monitoring and a documented reversal; server-side retrieval is periodic, not an immediate client-side switch.

## Sources

- [Android Developers — Configure website associations and dynamic rules](https://developer.android.com/training/app-links/configure-assetlinks)
- [Digital Asset Links statement list](https://developers.google.com/digital-asset-links/v1/statements)

## Tags

`android` `app-links` `deep-links` `assetlinks` `verification`
