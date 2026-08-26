# email-local-part-normalization

**Issue:** Applications that treat email addresses as unique identifiers while storing them raw get burned by provider-specific equivalence rules. Gmail ignores dots in the local part (first.last@gmail.com and firstlast@gmail.com are the same mailbox), treats googlemail.com as gmail.com, and both Gmail and Outlook honor plus-addressing (user+tag@). Without a canonicalization layer, one human can register unlimited "distinct" accounts, dodge bans and suppression lists, inflate dedup-keyed analytics, and defeat per-address rate limits. Naive fixes are equally dangerous: lowercasing and dot-stripping every domain breaks deliverability records for providers where local parts genuinely are case- or dot-sensitive, and mutating the stored address itself breaks SMTP delivery and SPF/DKIM identity. The engineering problem is storing an exact delivery address while enforcing uniqueness on a carefully scoped normalized form.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Canonicalization rules by provider

1. **Lowercase the domain, always.** Domains are case-insensitive by DNS and SMTP convention (RFC 5321), so Example.com and example.com are identical for every receiver. Local-part case is technically significant per RFC but virtually no provider distinguishes it; canonical lowercase for the uniqueness key is the accepted 2025 consensus.
2. **Strip dots in the local part only for Gmail.** For addresses at gmail.com and googlemail.com, remove every dot from the local part before hashing. Major platforms (Facebook, several financial services) do exactly this to block dot-variant duplicate accounts. Do not dot-strip other domains: dots are significant at most providers and stripping can collapse two legitimately different mailboxes.
3. **Alias gmail.com and googlemail.com.** Google treats these domains as equivalent, so normalize googlemail.com to gmail.com (or hash the combined local+normalized-domain pair) before uniqueness checks.
4. **Strip the plus-suffix for identity, never for delivery.** Cut the local part at the first plus sign when computing the normalized key. The tag portion is still needed at delivery time to route sub-addressed mail, so keep the original address intact. See email-subaddressing-plus-addressing.md for the delivery-side design.
5. **Do not normalize away trailing periods or other oddities.** Gmail accepts and ignores a trailing dot (firstlast.@gmail.com delivers to firstlast) but exotic hand-rolled rules beyond dots, plus, and domain aliasing are how false-positive account merges happen. Keep the rule table small, explicit, and unit-tested.

## Storage schema

1. **Store two columns: address_raw and address_normalized.** The raw column is the exact string used for SMTP RCPT TO and display. The normalized column (lowercase, provider-scoped dot/plus stripping, gmail domain alias) carries the UNIQUE constraint. Never overwrite the raw value with the normalized one.
2. **Make normalization deterministic and versioned.** Hash or derive the normalized form with a pure function checked into the repo, and record which version produced each row. When rules change (a new provider quirk is discovered), recompute in a backfill job rather than leaving mixed generations behind the unique index.
3. **Index the normalized column for lookups, not just integrity.** Login-by-email, suppression checks, ban enforcement, and password-reset lookups should query the normalized form so dotted or plus-tagged variants resolve to the same account.
4. **Apply the same key in the suppression pipeline.** Hard bounces, unsubscribes, and complaint entries must be keyed on the normalized form, or a user re-subscribes with first.last+shop@gmail.com and sails past a list that suppressed firstlast@gmail.com.

## Abuse and fraud prevention

1. **Treat normalized-key collisions at signup as a signal, not an error.** Surface "you already have an account" (which also leaks nothing when handled generically) instead of a raw uniqueness failure, and log the variant pattern: rapid-fire dotted registrations from one IP are a classic promo-abuse and ban-evasion fingerprint.
2. **Rate-limit on the normalized key.** Free-trial caps, referral bonuses, and magic-link frequency limits keyed on the raw string are trivially bypassed with dot variants; keying on the canonical form closes the hole.
3. **Credential-stuffing defenses benefit too.** Checking compromised-credential or known-account lists against normalized addresses catches far more hits, since stuffing dictionaries rarely preserve the victim's exact dot placement.
4. **Re-verify ownership on canonical collisions.** If a new signup normalizes to an existing account's key, require ownership proof of the new variant (standard verification email) before linking anything, so an attacker cannot squat a dotted variant of a victim address to inherit sessions or data.

## Pitfalls

1. **Normalizing for delivery instead of identity.** Stripping dots from the RCPT TO path works for Gmail today but is provider-behavior gambling; keep delivery on the raw address and normalization in the identity layer only.
2. **Assuming plus is safe to strip everywhere.** A minority of providers (and some on-prem Exchange configurations) treat plus as a literal local-part character. The uniqueness key can still strip it (collisions there are rare and low-harm), but confirm the variant is deliverable before binding it to an account.
3. **Case-sensitive local parts exist in the wild.** RFC 5321 permits them. If you serve mail to such domains, allow an escape hatch: skip case-folding when the domain is on a known case-sensitive list rather than corrupting the delivery key.
4. **Unicode addresses.** EAI/SMTPUTF8 addresses (see email-address-internationalization-eai.md) must be normalized in NFC form and lowercased per Unicode case-folding rules before comparison, or visually identical addresses compare unequal. Test the canonicalizer against EAI fixtures before shipping it.
