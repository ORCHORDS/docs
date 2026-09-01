---
title: "OWASP MASVS 2.1 Network and Platform Verification"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP MASVS 2.1 Network and Platform Verification

## Pinned source and scope
OWASP MASVS **2.1.0**, groups **MASVS-NETWORK** and **MASVS-PLATFORM**. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
Use platform TLS validation, constrain trust exceptions, and authenticate intended service identity. Inventory exported Android components, iOS URL handlers, universal/app links, intents, document providers, pasteboards, WebViews, JavaScript bridges, permissions, and IPC. Validate every inbound message and keep sensitive authorization server-side.

## Domain-specific procedure
Present expired, wrong-name, self-signed, and user-installed certificates; test redirects and alternate endpoints. Invoke every exported component from an untrusted app, mutate deep links, replay intents, traverse file-provider paths, navigate WebViews to hostile origins, and probe bridges. Certificate pinning is optional hardening, not a substitute for correct TLS validation.

## Evidence and decision
Retain certificate cases and handshake errors, exported-surface inventories, hostile-app invocation traces, deep-link inputs, WebView origins, and bridge calls. Map each observation to NETWORK or PLATFORM control IDs.

## Failure modes
Trust-all callbacks, broad exported components, secrets in URLs, wildcard WebView navigation, and pinning used to conceal broken hostname validation are failures.

## Sources
- [Pinned canonical source](https://mas.owasp.org/MASVS/)
