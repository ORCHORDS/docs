# SMTP SIZE capability and octet accounting

**Issue:** A sender checks attachment file size rather than the serialized SMTP message, then exceeds the receiver's advertised limit after MIME/base64 and transport encoding.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

RFC 1870 SIZE lets a server advertise a fixed maximum and a client declare estimated message size on MAIL FROM. Measure the complete serialized message octets under the chosen transfer method and still handle final server rejection.

**Source:** [RFC 1870: SMTP Service Extension for Message Size Declaration](https://www.rfc-editor.org/rfc/rfc1870)

## Controls

- parse SIZE only from the post-STARTTLS EHLO capability set;
- calculate headers, MIME boundaries, transfer encoding, and body;
- enforce smaller local/product limits independently;
- send the parameter only when supported;
- reject oversized user input before expensive upload/encoding where possible;
- preserve per-recipient/provider limits.

## Verification

Test exact boundary, one octet over, base64 expansion, Unicode headers, DATA dot-stuffing versus BDAT, server with SIZE but no numeric maximum, and changed capability after TLS. Confirm no partial transaction is treated as accepted.

## Gotchas

Advertised size can be a fixed ceiling, not current available storage. Acceptance of MAIL FROM does not guarantee final acceptance. Attachment bytes are not message bytes.
