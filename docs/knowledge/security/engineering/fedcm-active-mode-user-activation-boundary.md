# FedCM active-mode user-activation boundary

**Issue:** FedCM active mode is designed for explicit user-triggered identity flows and must not be turned into background account probing.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Require trusted user activation, bind request to visible RP action, minimize IdP list and retain non-FedCM recovery.

## Tests

Synthetic click, iframe, repeated prompt, stale activation, cancellation, unsupported browser.

## Gotchas

A browser prompt is not application consent to every downstream permission.

## Official sources

- https://w3c-fedid.github.io/FedCM/
