# Federated Account Change Signaling

## Purpose

Federated identity creates state at both an identity provider (IdP) and relying party (RP). Important changes such as compromise, account termination, attribute updates, or authenticator changes may need to be communicated outside the normal federation transaction so downstream systems do not continue relying on stale identity state.

NIST SP 800-63C Revision 4 defines shared signaling as a controlled mechanism for exchanging those state changes.

## Trust boundary

Shared signaling must be governed by the federation trust agreement. The agreement should document:

- which events cause a signal;
- which party is permitted to send and receive each signal;
- the data and parameters included;
- how a receiver is expected to process the signal;
- privacy-review requirements; and
- the security controls protecting the signaling channel.

Signals should contain only the personal information necessary to identify and process the affected subscriber account.

## Important IdP-to-RP events

NIST recommends signaling changes such as:

- account termination, suspension, or disablement;
- suspected account compromise;
- changes to account attributes or identifiers;
- changes to the possible IAL, AAL, or FAL range; and
- authenticator updates.

If an RP receives a compromise signal, it should review activity associated with the RP account for suspicious actions.

## RP-to-IdP signals

An RP can also signal account termination, suspension, suspected compromise, and addition or removal of bound authenticators. If the IdP confirms suspicious activity after receiving a compromise signal, NIST requires the IdP to signal other RPs used by that subscriber during the suspected period where appropriate.

## Linked-account privacy

Where an RP links multiple IdPs to one RP account, signaling practices should avoid revealing the identity of the subscriber's other linked IdPs. Shared signaling is a state-management tool, not a reason to disclose the broader federation graph.

## Sources

- NIST SP 800-63C Revision 4 — Shared Signaling: https://pages.nist.gov/800-63-4/sp800-63c.html
- NIST SP 800-63C Revision 4 — General-Purpose IdP: https://pages.nist.gov/800-63-4/sp800-63c/GenIdP/

## Scope note

This article describes reusable federation-security controls. Specific event formats, protocols, trust agreements, privacy obligations, and operational response procedures remain deployment-specific.