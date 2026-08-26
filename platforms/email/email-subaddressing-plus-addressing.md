# email-subaddressing-plus-addressing

**Issue:** Subaddressing (RFC 5233 Sieve extension, "detailed addresses") lets one mailbox receive mail at local-part+tag@domain — Gmail and most modern MTAs deliver user+netflix@ to user@, exposing the tag to filters. As of 2025 support is deliberately uneven: Exchange Online supports plus addressing only when an admin enables it (off by default), and Outlook.com and iCloud Mail do not reliably support it at all. For engineers, subaddressing cuts two ways: it is a powerful identity primitive (per-service addresses, abuse attribution, inbox rules) and a source of subtle bugs — uniqueness checks that treat user+a@ and user+b@ as different people, promo-abuse via tag rotation, and normalization mismatches between what your system stores and what the receiving MTA canonicalizes.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Provider support reality (2025)

1. **Gmail: full native support.** Anything between + and @ is delivered to the base account; Gmail webmail and Google Workspace both expose the tag to filters (search to:user+tag). Note the adjacent Gmail quirk: dots in the local part are ignored entirely (first.last@gmail.com === firstlast@gmail.com), which matters as much as plus-tags for canonicalization.
2. **Exchange Online: supported but disabled by default.** Admins must run Set-OrganizationConfig with AllowPlusAddressInRecipients enabled; before that, mail to user+tag@tenant.onmicrosoft.com NDRs. If a customer reports plus-address bounces on a corporate domain, this toggle is the answer — and note Exchange's implementation rejects plus-addresses that collide with real aliases/groups.
3. **Outlook.com and iCloud Mail: effectively unsupported.** Plus-tagged mail to those consumer domains may bounce or land unpredictably; Apple's answer is Hide My Email aliases instead. Never generate plus-addresses on behalf of users at these domains (a "create unique address per service" feature must domain-check first), and treat plus-tags captured from those domains as unreliable routing data.
4. **Self-hosted and ESP infrastructure: verify the separator.** Postfix implements recipient_delimiter (configurable: +, -, or both), Dovecot supports it in LDA/sieve, Fastmail offers both + and - separators. If you run the receiving side, choose the delimiter consciously and document it; if you send transactional mail to plus-addresses, nothing special is needed — you are just addressing an ordinary mailbox.

## Engineering identity systems with subaddressing

1. **Separate the routing address from the identity key.** Store the full address for delivery, but derive the account identity from a normalized base (strip the +tag, lowercase, NFC-normalize, and for Gmail also strip dots). Two signups with user+a@ and user+b@ should map to one account for duplicate-detection and fraud purposes — otherwise tag rotation trivially defeats "one account per person" checks, free-trial farming, and referral-bonus abuse.
2. **Canonicalize at the boundary, not deep in the stack.** Every ingestion point (signup, login, password reset, invite) should pass through one normalizer with unit tests: plus-tag stripping, dot handling per domain (Gmail-only), domain punycode mapping, case folding. Divergent ad-hoc normalization across services is how user+A@ resets a password for user+B@'s account.
3. **Preserve the tag when it carries attribution data.** If users hand out per-service addresses, inbound automation (ticketing, alias routing) often keys off the tag — parse user+support@, user+billing@ at your inbound gateway (Sieve subaddress extension, envelope recipient, or X-Original-To) before any normalization for routing, and store the original for audit. Strip for identity, keep for routing.
4. **Treat the tag as untrusted input.** Tags flow into analytics, CRM dedupe keys, and sometimes URLs or logs. Length-limit and character-validate them at capture (they are valid RFC 5322 atoms that can contain surprising characters), and never build SQL/LDAP/directory lookups that assume the tag is [a-z0-9].

## Detection, filtering, and privacy uses

1. **Inbound filtering on the receiving side.** Sieve subaddress (RFC 5233) exposes the tag as :detail ("user" + "tag"); use it to file, label, or auto-respond per service. On Gmail, filters matching to:user+tag work natively; on Exchange Online with plus addressing enabled, transport rules and inbox rules can key off the tag; Apple Mail (client-side rules) can filter +tags for providers that support subaddressing, but iCloud-as-provider cannot.
2. **Leak attribution as a product feature.** Give users generated per-sender addresses (yourdomain or a subdomain you control, so you fully control delivery) rather than teaching them to hand-rolled plus-tags: sender-tagged addresses show exactly who leaked or sold the address, and because you run the wildcard/catch-all receiving side, support is provider-independent. This is the engineering rationale for alias services (SimpleLogin, Firefox Relay, Hide My Email) over raw plus-addressing.
3. **Assume marketers strip plus-tags.** Normalization-on-receive (stripping +tag) is a common, if hostile, ESP practice, and some sites outright reject + in email fields (validation bugs, not policy). So: never build a security control that depends on the tag surviving someone else's system; treat tag-based addressing as best-effort convenience plus attribution signal, not as an isolation boundary.

## Pitfalls and failure modes

1. **Uniqueness constraints that ignore tags create account takeover; constraints that honor tags create infinite accounts.** Decide explicitly per surface: identity/dedup must collapse tags; deliverability must preserve them. Documenting this one decision prevents both the takeover class (login as user+admin@ for user@) and the abuse class (unbounded free trials).
2. **Password reset and login flows are the highest-risk surface.** A reset flow that resolves user+tag@ to the base account differently than the signup flow did is a credential bug; a login flow that treats them as separate accounts is a support-ticket generator. Fuzz both flows with tag and dot variants in integration tests.
3. **Suppression lists and bounce handling must normalize identically to signup.** If signup canonicalizes user+a@ to user@ but the bounce processor stores user+a@ verbatim, a hard bounce for one variant keeps mailing the other. All email pipelines (send, bounce, complaint, unsubscribe) must share the one normalizer.
4. **Rate limiting and dedupe keyed on raw addresses are trivially defeated.** Any abuse control (coupon issuance, voting, signups-per-IP per-email) keyed on the exact string is bypassed by appending +1 through +N. Key anti-abuse on the normalized base address (plus device/payment signals); key friendly UX on the raw address.
