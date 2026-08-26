# Android 17 Encrypted Client Hello policy

**Issue:** An Android app assumes encrypted DNS also hides TLS destination metadata, or enables Encrypted Client Hello without checking network and endpoint compatibility.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** Android 17 behavior; validate against the final SDK before production rollout

Android 17 adds app configuration for Encrypted Client Hello (ECH) through Network Security Configuration. ECH encrypts ClientHello metadata when the resolver, server configuration, and client path support it; it is not a replacement for certificate validation or application authorization.

**Source:** [Android 17 behavior changes](https://developer.android.com/about/versions/17/behavior-changes-17)

## Controls

- declare ECH policy in the intended base or domain configuration instead of changing global networking accidentally;
- inventory endpoints, CDNs, TLS inspection, captive portals, and enterprise networks before enforcement;
- retain normal hostname and certificate validation;
- expose privacy-preserving telemetry for negotiated, unavailable, fallback, and failed outcomes;
- stage by app version and domain with a rollback path.

## Verification

- tests cover an ECH-capable endpoint, unsupported endpoint, broken configuration, captive portal, and enterprise proxy;
- domain overrides do not leak into unrelated hosts;
- failure handling does not disable TLS verification or retry over cleartext;
- packet-level lab checks confirm the expected ClientHello visibility.

## Gotchas

- DNS encryption and ECH solve different metadata exposures.
- network intermediaries can affect availability.
- preview behavior may change before Android 17 final release; rerun compatibility tests with each SDK update.
