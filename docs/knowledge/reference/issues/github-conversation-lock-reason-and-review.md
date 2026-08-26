# GitHub Conversation Lock Reason and Review

**Issue:** Locking an issue without a visible reason or review point can suppress legitimate follow-up and turn moderation into an unaccountable permanent state.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Lock only when the whole conversation is nonconstructive or violates community rules, and state a public reason where safe.
- Choose temporary or permanent duration deliberately and assign a review owner for temporary locks.
- Preserve moderation evidence according to policy without exposing sensitive reporter information.
- Remember that locked conversations disable reactions and comments for ordinary participants while privileged collaborators can still act.
- Use `is:locked archived:false` review queries because archived repositories are locked automatically.

## Verification

- Lock and unlock a test issue and verify timeline events, public reason, permissions, reactions, and notification behavior.
- Review all non-archived locked conversations for expiry and continued justification.
- Confirm actor visibility differs appropriately between authorized collaborators and the public.

## Gotchas

- Confirm the cited feature or standard edition remains current before relying on it.
- Keep secrets, personal data, and restricted evidence out of examples and logs.
- Reassess after scope, implementation, or policy changes.

## Sources

- https://docs.github.com/en/communities/moderating-comments-and-conversations/locking-conversations
