# Apple LiveCommunicationKit conversation lifecycle

**Issue:** A communication app models a system conversation UI as the authoritative call state and fails to reconcile interruptions, permissions, and app/backend state.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer Apple platform API; verify OS availability and policy

LiveCommunicationKit integrates supported communication experiences with system UI. Keep one durable conversation state machine and treat system actions as inputs that still require account, permission, network, and backend validation.

**Source:** [Apple LiveCommunicationKit documentation](https://developer.apple.com/documentation/livecommunicationkit)

## Controls

- gate by OS/framework availability and declared communication use case;
- use stable conversation identifiers without embedding secrets;
- make answer, end, mute, and hold transitions idempotent;
- reconcile system, media-session, app, and server states;
- minimize lock-screen metadata and respect device/account privacy;
- provide fallback UI where the framework is unavailable.

## Verification

Test incoming/outgoing, decline, duplicate action, app termination, device lock, network handoff, audio interruption, permission denial, account switch, and backend termination. Confirm stale system actions cannot revive a closed conversation.

## Gotchas

System presentation is not backend authorization or proof of media connectivity. Lifecycle callbacks may race with network events. Availability and eligible app categories can evolve.
