# character-encoding-utf-8-2026

**Issue:** A form field crashes on a Japanese name. A log line shows `ã©` instead of `é`. A database stores `?????` instead of Cyrillic. The team didn't agree on encoding.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Wrong encoding produces mojibake — `é` becomes `ã©`, Japanese kanji becomes `???`, emoji becomes `ðŸ˜Š`. Users see garbage text. Search across systems fails because the same string is encoded three different ways.

## Root cause

UTF-8 is the universal encoding for web, file storage, and inter-service communication. The failure modes are almost always one of: reading without specifying encoding, mixing encodings in a pipeline, or storing bytes without a declared charset.

## The encoding hierarchy

| Encoding | Use case | Compatibility |
|---|---|---|
| **UTF-8** | Universal — web, files, APIs, databases | ASCII-compatible; variable byte width |
| **UTF-16** | Windows internal, Java strings (before Java 18) | Surrogate pairs for non-BMP |
| **UTF-32** | Fixed-width processing | 4 bytes per code point; wasteful |
| **ISO-8859-1** | Legacy Western European | Single-byte; 256 code points |
| **Windows-1252** | Legacy Microsoft | Superset of ISO-8859-1 |
| **GB18030** | Chinese national standard | Required for some Chinese government systems |

**Default to UTF-8.** Every modern system supports it. Migrate legacy encodings; don't accept new ones.

## The five rules

**1. Declare encoding everywhere.** HTML `<meta charset="utf-8">`. HTTP `Content-Type: text/html; charset=utf-8`. Database columns `CHARACTER SET utf8mb4`. File I/O `encoding="utf-8"`. Without declaration, the system guesses — and guesses wrong.

**2. UTF-8 means `utf8mb4` in MySQL.** The legacy `utf8` in MySQL is a 3-byte subset that can't store 4-byte characters (most emoji, some CJK). Use `utf8mb4` for full Unicode support.

```sql
CREATE TABLE users (
  name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
);
```

**3. Normalize on input.** Multiple Unicode sequences can represent the same visible character (`é` as one character or `e` + combining acute). Pick a normalization form (NFC, NFD, NFKC, NFKD) and apply on input.

**4. Handle BOM consistently.** UTF-8 files can have an optional Byte Order Mark (`EF BB BF`). Some tools expect it, others break on it. Pick a convention per project.

**5. Test with mixed scripts.** A name like "李雷 (Lei Li) — café 北京" mixes CJK, Latin, accents, and punctuation. Test the full pipeline with this input.

## The reading and writing discipline

```python
# Python — always specify encoding
with open('file.txt', 'r', encoding='utf-8') as f:
    content = f.read()

with open('file.txt', 'w', encoding='utf-8') as f:
    f.write(content)

# PowerShell — use -Encoding UTF8 explicitly
Get-Content file.txt -Encoding UTF8
Set-Content file.txt -Encoding UTF8 -Value $content
```

PowerShell 5.1 defaults to ANSI/CP1252 on Windows. Without `-Encoding UTF8`, reading a UTF-8 file produces mojibake. PowerShell 7+ defaults to UTF-8 on Linux but still requires explicit `-Encoding UTF8` on Windows.

## The HTTP API discipline

```http
Content-Type: application/json; charset=utf-8
Content-Type: text/html; charset=utf-8
Content-Type: text/csv; charset=utf-8
```

Always include `charset=utf-8` in `Content-Type`. Servers and clients rely on this to decode the body. JSON (`application/json`) is implicitly UTF-8 per RFC 8259; declaring it is still best practice.

## The database discipline

| Database | Column type | Collation |
|---|---|---|
| MySQL | `VARCHAR(N) CHARACTER SET utf8mb4` | `utf8mb4_unicode_ci` or `utf8mb4_0900_ai_ci` |
| PostgreSQL | `VARCHAR(N)` (always UTF-8 internally) | `en_US.UTF-8` or locale-specific |
| SQLite | `TEXT` (always UTF-8 internally) | N/A |
| SQL Server | `NVARCHAR(N)` (UTF-16) | `database_default` |

For MySQL: alter the database and all tables, convert columns, verify with `SHOW VARIABLES LIKE 'character_set%'`. Migration is a one-time effort but easy to skip.

## The regex and string handling

```python
# ❌ bytes-based regex on UTF-8 string
re.search(b'\w+', text.encode('utf-8'))  # works but limits patterns

# ✅ string-based regex on Unicode text
re.search(r'\w+', text, re.UNICODE)  # matches Unicode word characters
```

Use Unicode regex patterns for matching across scripts. `\w` with `re.UNICODE` matches accented Latin, Cyrillic, CJK; without it, only ASCII.

## The normalization forms

| Form | Behavior | Use when |
|---|---|---|
| NFC | Composed: `é` as one character | Storage, comparison |
| NFD | Decomposed: `e` + combining acute | Search, fuzzy matching |
| NFKC | Compatibility composed | Identifiers, slugs |
| NFKD | Compatibility decomposed | Search across compatibility forms |

Default to NFC for storage. Use NFD for search (matches more variations). Use NFKC for slugs (strips compatibility characters like full-width digits).

```python
import unicodedata
normalized = unicodedata.normalize('NFC', text)
```

## The emoji and supplementary plane

Characters above U+FFFF (most emoji, some historical scripts, mathematical alphanumeric symbols) require 4 bytes in UTF-8 or surrogate pairs in UTF-16. MySQL's `utf8` (3-byte) cannot store them. JavaScript uses UTF-16 internally; the `String` length counts UTF-16 code units, not code points.

```javascript
'😀'.length  // 2 (surrogate pair), not 1
[...'😀'].length  // 1 (iterator yields code points)
```

For accurate character count, use the iterator. For storage in MySQL, use `utf8mb4`.

## The common failure modes

| Failure | Cause | Fix |
|---|---|---|
| `ã©` instead of `é` | UTF-8 bytes interpreted as Latin-1 | Specify UTF-8 in reading code |
| `?????` instead of CJK | Wrong encoding in DB column | Migrate to utf8mb4 |
| `ðŸ˜Š` instead of `😀` | UTF-8 bytes interpreted as Latin-1 twice | Decode as UTF-8 once, not multiple times |
| Empty string on input | BOM treated as part of string | Strip BOM on read |
| Crash on invalid byte | Strict decoder rejects malformed input | Use `errors='replace'` or sanitize upstream |

## Verification

The tell that encoding is working:

- A name with mixed scripts (CJK + Latin + accents) round-trips correctly through the system
- Database columns are `utf8mb4`; emoji are stored without truncation
- HTTP responses declare `charset=utf-8`
- File I/O always specifies `encoding='utf-8'`
- Unicode normalization (NFC) is applied on input

The tell it isn't:

- `ã©` appears in logs
- `?????` appears in the database
- Emoji truncate to 3 bytes
- PowerShell scripts produce ANSI output despite source being UTF-8

## Gotchas

- **MySQL `utf8` is not UTF-8.** It's 3-byte; use `utf8mb4`.
- **PowerShell 5.1 defaults to ANSI.** Use `-Encoding UTF8` explicitly.
- **JavaScript `String.length` is UTF-16 code units.** Emoji are 2; use the iterator.
- **Normalize on input.** `é` and `e+combining acute` are the same visible character.
- **Declare encoding everywhere.** HTML, HTTP, DB, files. Guessing leads to mojibake.
- **Test with mixed scripts.** "李雷 café 北京" exposes every encoding bug in the pipeline.
- **Strip BOM or include it consistently.** Mismatched handling causes empty first characters.

## Related

- `i18n/icu-message-format.md` — Unicode strings in messages
- `i18n/rtl-bidi-handling.md` — bidirectional text in mixed-script UIs
- `i18n/locale-negotiation.md` — locale affects encoding

## Source URLs (verified 2026-08-10)

- https://developer.mozilla.org/en-US/docs/Web/API/Encoding_API
- https://www.w3.org/International/questions/qa-choosing-encodings
- https://stackoverflow.com/questions/64869030/what-is-the-difference-between-utf8-and-utf8mb4
- https://docs.python.org/3/howto/unicode.html
- https://www.unicode.org/reports/tr15/
