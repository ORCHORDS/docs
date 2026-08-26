# idn-punycode-internationalized-email

**Issue:** Email addresses are the identifier nearly every product keys its accounts on, yet the default engineering assumption — that an email is pure ASCII — is wrong for hundreds of millions of users. People own addresses with accented Latin characters (josé@example.fr), Greek, Cyrillic, Chinese, or Arabic local parts, and domains written entirely in non-Latin scripts. The email stack handles this through two different mechanisms that are frequently confused: internationalized domain names (IDN), which must be converted to punycode ASCII because DNS remains ASCII-only, and Email Address Internationalization (EAI), which transports the local part as UTF-8 via the SMTPUTF8 extension. Products that validate with a naive ASCII regex silently reject valid users at signup, while products that accept Unicode addresses carelessly expose themselves to homograph phishing. Getting this right touches validation, storage, delivery, display, and abuse review, and each layer has different rules.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The two-part problem: domain vs local part

1. **DNS forces punycode on the domain.** The domain portion of any address must be resolvable through DNS, which only accepts ASCII. IDNA2008 (RFC 5890 through 5893) defines how a Unicode domain label becomes an A-label: punycode encoding (RFC 3492) with the xn-- prefix, for example, bücher.example becomes xn--bcher-kva.example. You never store or transmit raw Unicode in the DNS layer; you convert at lookup time.
2. **The local part stays UTF-8 under EAI.** The mailbox name before the @ is not a DNS name, so punycode does not apply. SMTPUTF8 (RFC 6531) lets the envelope, and RFC 6532 lets the message headers, carry UTF-8 local parts such as 用户@example.cn. Converting the local part to punycode is a common and destructive mistake — it changes the address into a different mailbox.
3. **EAI support is still not universal.** Many receiving mail systems — especially older corporate gateways and some SaaS providers — do not advertise SMTPUTF8. A send to an EAI address through a non-EAI relay will bounce or silently mangle. Delivery strategy must probe capability and have a documented fallback.
4. **Two identities, one address.** In IDNA the Unicode form (U-label) and the punycode form (A-label) of the same domain are two spellings of one name, and case-insensitive. The local part, by contrast, is case-sensitive in principle (RFC 5321) and must be compared byte-for-byte after NFC normalization, never lowercased blindly.

## Validation rules that actually work

1. **Split on the last @, then validate each half separately.** The display name, comments, and quoted-string forms of RFC 5322 make monolithic regexes hopeless. Parse structurally: everything after the final @ is the domain, everything before is the local part. This also survives the rare quoted @ inside the local part.
2. **Validate the domain with an IDNA library, not a regex.** Run the domain through a current IDNA2008 implementation (UTS-46 transitional handling off) that checks label validity rules — contextual rules for Arabic and Indic scripts, Bidi requirements, disallowed code points — and rejects overlong labels. Hand-rolled checks miss contextualjoiner rules and accept domains the registry layer would never issue.
3. **Keep local-part validation loose.** Enforce only the hard limits (64 octets local part, 255 for the domain) plus a short blocklist of control characters and whitespace. Anything stricter — mandating ASCII letters, banning dots in odd positions, requiring a TLD pattern — will reject addresses that legitimately exist under EAI.
4. **Normalize before comparing.** Apply Unicode NFC normalization to the local part at entry time and store the normalized form, because ö can be composed or decomposed and those two byte sequences are different mailboxes to a strict server. Compare domains case-insensitively after punycode conversion; compare local parts exactly.
5. **Test with the awkward corpus.** Add addresses containing Latin-1 accents, Greek omicron vs Latin o, zero-width characters, an all-Chinese local part, and a quoted local part with an @ to the signup test suite. The zero-width and confusable cases should be rejected or flagged; the rest should pass.

## Homograph and spoofing defenses

1. **Treat mixed-script domains as hostile by default.** IDN homograph attacks register domains that mix scripts with visually identical glyphs (Cyrillic а inside a Latin word) so paypal-аpple-secure.example looks legitimate. Security research through 2025 continues to document punycode abuse in email phishing campaigns specifically, because mail clients render the Unicode form while the underlying wire format hides xn-- labels. Apply UTS #39 mixed-script confusable checks to any domain used in signup, password reset, or sender verification flows.
2. **Show the punycode form when scripts mix, Unicode when they do not.** The safe display policy mirrors browsers: render the U-label only when the domain is single-script (or a permitted script combination); otherwise display xn-- explicitly so the deception collapses. Never allow a display name in your product to render an IDN differently from this rule.
3. **Check the whole address, not just the domain, for confusables.** A local part like admın (dotless i) in a password-reset reply-to is a social-engineering vector even when the domain is clean. Run the full address through confusable detection in abuse paths, while keeping the normal signup path fast and permissive.
4. **Do not let lookalike domains collide in account lookup.** If your product derives account identity or tenant slugs from email domains, map domains through punycode and a confusable-skeleton function before comparison, so two homograph domains cannot squat the same namespace.

## Sending, storing, and displaying

1. **Store the address verbatim and derive wire forms at send time.** Keep the user-entered Unicode address (NFC-normalized) as the source of truth. Compute the punycode domain on demand for MX lookups, and re-compute on every send so changes in IDNA library behavior or registry policy do not strand stale encodings in the database.
2. **Probe SMTPUTF8 per recipient and have a fallback.** At delivery time, check whether the receiving MX advertises SMTPUTF8. If it does not, either queue and retry through an EAI-capable relay, or send an ASCII fallback notice asking the user for an ASCII address — but decide this policy explicitly instead of discovering it as a bounce.
3. **Set headers correctly for UTF-8 addresses.** Message headers carrying non-ASCII addresses need RFC 6532 UTF-8 headers when the transport supports SMTPUTF8, or RFC 2047 encoded-words in legacy environments. Tools that only speak legacy encoding will mangle EAI headers; verify your mail library supports both before shipping international addresses into transactional flows.
4. **Audit every regex in the signup and login path.** The classic failure is a corrected API validator paired with a leftover ASCII regex in the login form, the password-reset endpoint, or an analytics pipeline. grep for @-centric patterns and run the EAI test corpus through each; the address that signs up must also be able to log in and receive mail.
