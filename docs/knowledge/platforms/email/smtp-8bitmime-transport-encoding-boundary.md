# SMTP 8BITMIME transport-encoding boundary

**Issue:** A sender transmits 8-bit body content without peer support or assumes 8BITMIME permits arbitrary binary data and internationalized envelope addresses.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

RFC 6152 8BITMIME permits MIME bodies with 8-bit content transfer when advertised. Declare BODY=8BITMIME on MAIL FROM, retain a standards-compliant 7-bit encoding fallback, and keep SMTPUTF8/BINARYMIME semantics separate.

**Source:** [RFC 6152: SMTP Service Extension for 8-bit MIME Transport](https://www.rfc-editor.org/rfc/rfc6152)

## Controls

- re-EHLO after STARTTLS and use only advertised capability;
- serialize valid MIME with line-length and canonical line-ending rules;
- downgrade body encoding safely when unsupported;
- do not alter signed/encrypted content without policy;
- declare the correct BODY parameter.

## Verification

Test 7-bit/8-bit bodies, unsupported relay, multi-hop downgrade, UTF-8 headers, SMTPUTF8 envelope, long lines, signed MIME, and DSNs.

## Gotchas

8BITMIME applies to body transport, not Unicode addresses/headers. It is not BINARYMIME. Relays must preserve or correctly re-encode content.
