# mime-encoded-words-rfc2047

**Issue:** Email headers are 7-bit ASCII by default, so any non-ASCII text — accented names, CJK subjects, emoji in preview text — must be carried as RFC 2047 encoded words in the form =?charset?encoding?text?=. Getting this wrong produces mojibake subjects (=?utf-8?B?...?= shown raw to users), headers that exceed the 76-character encoded-word limit (a MUST NOT in the spec), spaces swallowed between adjacent encoded words during folding, and filtering rules that silently fail because downstream tools decode inconsistently. Builders also face a modern fork: legacy encoded-words versus native UTF-8 headers under RFC 6532/SMTPUTF8, where choosing wrong breaks delivery through older relays. This is the header-layer counterpart to email-address-internationalization-eai.md, which covers Unicode addresses rather than header text.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When and where to encode

1. **Encode only unstructured header fields and display names.** Subject, keywords, content-description, the display-name portion of From/To/CC (the part before the angle-addr), and comments are fair game. Never encode the addr-spec itself — user@domain must remain literal ASCII or an EAI address under SMTPUTF8, or delivery fails.
2. **Leave pure ASCII unencoded.** If the header value is already ASCII, emitting it raw is both spec-correct and friendlier to filters and log grepping. Encoding ASCII adds fragility with zero benefit.
3. **Encode at the library boundary, not in templates.** Use your MIME library's header-encoding functions (Python email.header, Ruby Mail::Encodings, Node's libmime/nodemailer prepared headers) rather than hand-concatenating =?utf-8?B?...?= strings; the libraries handle length, folding, and B/Q selection.
4. **Structured fields need parameter encoding instead.** Filename parameters in Content-Disposition use RFC 2231 continuations (filename*=utf-8''...), not encoded words. Mixing the two mechanisms is a classic generator bug.

## Choosing B versus Q

1. **B (base64) for mostly non-ASCII text.** When the string is dominated by non-ASCII bytes (CJK, Cyrillic, emoji-heavy subjects), B encoding is the compact and conventional choice; most libraries pick it automatically.
2. **Q (quoted-printable variant) for mostly ASCII with a few specials.** An accented character or two inside a long English subject wastes far less space under Q, which passes ASCII through and escapes only the specials (using underscores for spaces in this context, unlike body quoted-printable).
3. **Prefer the shorter encoding and let the library choose.** Decoders MUST accept both per RFC 2047, so encoding choice is purely an efficiency and readability decision; several mail libraries offer an automatic shortest-of-both mode.
4. **Never mix encodings mid-word or hand-roll escapes.** Each encoded word stands alone with its own charset and encoding token; concatenating half-encoded fragments produces strings no decoder can recover.

## Length, folding, and whitespace rules

1. **Respect the 75-character encoded-word limit.** An encoded word must not exceed 75 characters (which fits the 76-octet header line budget with room for separators). Over-long encoded words are a spec violation and show up as garbled nonsense in strict clients; split the text into multiple consecutive encoded words instead.
2. **Separate adjacent encoded words with linear whitespace.** Two encoded words in a row must have a space between the closing and opening =? tokens, or decoders treat them as one malformed blob.
3. **Know that whitespace BETWEEN encoded words is discarded on decode.** When folding a long header, the CRLF-plus-WSP between two encoded words is stripped during decoding. A literal space the user should see must be represented inside the encoded words (as an encoded space or underscore), never as the delimiter between them — otherwise subjects lose words ("MeetingMonday").
4. **Fold between encoded words, never inside one.** Continuation lines must break at encoded-word boundaries. Breaking inside the ?B? payload corrupts it in parsers that unfold naively.

## Charset consistency and decoding pitfalls

1. **Use UTF-8 everywhere, uniformly.** Legacy charsets (iso-8859-1, windows-1252, gb2312) still appear in the wild and decoders must handle them, but anything you generate should be UTF-8; mixed charsets across the words of one header cause decode failures and are a spam-filter smell.
2. **Decode defensively on ingest.** When parsing inbound mail, decode every encoded word with its declared charset, map unknown charsets to a replacement policy, and normalize the result; naive UTF-8 assumption on inbound data throws away or mangles legacy mail. Fold in RFC 2231 handling for parameters at the same boundary.
3. **Do not filter on raw subject bytes.** Spam rules, routing rules, and analytics that substring-match the raw Subject header silently miss matches hidden inside encoded words (a known issue class even in modern sieve implementations). Normalize/decode to a canonical internal string first, then match.
4. **Test round-trips with hostile fixtures.** Emoji (4-byte UTF-8), combining diacritics, RTL text, long CJK subjects requiring many folds, and an ASCII word trapped between two encoded words should all round-trip through your encode and decode paths; the between-words-space case is the one that reliably regresses.

## SMTPUTF8 and the modern path

1. **RFC 6532 allows raw UTF-8 in headers.** When the entire submission and relay path advertises SMTPUTF8 (8BITMIME extension), you can emit native UTF-8 subjects and display names with no encoded words at all — cleaner logs, better filter behavior.
2. **The downgrade problem is real.** If any relay or final receiver on the path lacks SMTPUTF8, native UTF-8 headers cause rejection or mangled delivery, and message downgrading is poorly supported in practice. Unless you control the path, encoded words remain the interoperable default.
3. **Follow your ESP's lead.** Major ESP APIs accept UTF-8 header values and re-encode to encoded words for legacy paths automatically; feed them plain UTF-8 strings rather than pre-encoding, or you get double-encoded =?utf-8?B?PT91dGYtOD... subjects.
4. **Verify in the wild, not just in tests.** Send subjects with emoji and non-ASCII display names to Gmail, Outlook.com, and a catch-all test inbox, and confirm both rendering and threading survive; encoded-word boundaries occasionally interact with Subject-based threading heuristics (see email-threading-references-in-reply-to.md for the threading mechanics).
