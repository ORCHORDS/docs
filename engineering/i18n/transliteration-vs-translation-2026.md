# transliteration-vs-translation-2026

**Issue:** The pipeline sent every string through machine translation, so user-supplied non-Latin content broke downstream systems: Cyrillic and Greek display names crashed ASCII-only slug generation, "Мария Танькова" became "Maria Tankova" via MT guesswork in some contexts and stayed raw Cyrillic in others, and search could not connect a Latin-typed query to a Cyrillic-stored record. The team conflated three different operations: translation (converts meaning between languages), transliteration (converts characters between scripts, meaning untouched), and transcription (captures pronunciation). Picking the wrong one produces broken identifiers, inconsistent name matching, and unfindable records.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three operations and when each applies

1. **Translation changes meaning-bearing language.** "Save" → "Speichern". Use it for UI strings and content. Never for names or identifiers — MT of a proper name invents things ("Weide" for Willow as a surname is a guess, not a mapping).
2. **Transliteration maps characters between scripts mechanically.** `Мария` → `Mariya`, `李` → `li` (pinyin), `Τάσος` → `Tasos`. It operates on characters without regard to meaning, which makes it deterministic and safe for identifiers, slugs, and search keys.
3. **Romanization is transliteration into Latin specifically.** It is the operation behind passport names, library catalogs, and ASCII fallbacks. Every romanization is scheme-bound: the same `李` is `li` in Hanyu Pinyin, `lee` in common Korean-style renderings of the equivalent surname, and `ri` in Revised Hepburn contexts — the scheme must be chosen and recorded, not assumed.
4. **Transcription captures speech, not writing.** Relevant for TTS pronunciation hints and search-as-pronounced, not for identifier generation.

## Where transliteration is the right tool

1. **Slug and URL generation.** User titles in any script need ASCII slugs: transliterate first, then strip remaining non-ASCII. Translating instead would change the URL every time the MT model changes — identifiers must be stable.
2. **Search equivalence across scripts.** A user typing `Dostoevsky` should find `Достоевский`. Build a transliterated search column at write time so Latin queries match Cyrillic/Greek/Arabic-stored records without exact-script agreement.
3. **Display fallbacks.** When a font or terminal cannot render a script, a romanized fallback (`Any-Latin; Latin-ASCII`) beats tofu boxes. Mark it clearly as generated text, and keep the original as the source of truth.
4. **Names on documents and matching.** Passports, KYC flows, and payment systems romanize names by fixed national schemes (e.g. ICAO 9303 for MRZ). Two spellings of one name (`Chae`/`Che`) reconciling requires scheme awareness, not fuzzy MT.
5. **Sorting in Latin-only indexes.** A secondary transliterated key enables a deterministic collation for systems that cannot use full Unicode collation.

## Implementation with ICU transforms

1. **ICU `Transliterator` is the reference engine.** ICU4J/ICU4C expose rule-based transforms identified by IDs: `Cyrillic-Latin`, `Greek-Latin`, `Any-Latin` (any script to Latin), and chainable rules like `Any-Latin; Latin-ASCII` (romanize, then fold to plain ASCII). CLDR publishes transliteration guidelines and per-locale data feeding these.
2. **Keyboard/incremental mode exists.** ICU supports filtering and incremental transliteration for per-keystroke input conversion (the mechanism behind OS-level Latin-to-Cyrillic typing aids); use the filtered form when transliterating only part of a mixed-script string.
3. **Custom rules for product vocabulary.** Brand names and trademarked renderings override generic schemes — ICU accepts custom rule files layered on top of a base transform so `Γκρικ` → "Greek" (your brand) rather than "Gkrik".
4. **In JS, use a data package, not ad-hoc maps.** npm packages such as `transliteration` and `any-ascii` bundle character mapping tables (roughly ICU-derived) with `slugify()` helpers. Hand-written `{'а':'a'}` maps miss digraphs (`щ` → `shch`), combining marks, and case pairs — always map through a maintained table.
5. **Do not double-convert.** Transliterate once at the boundary and store the result; re-transliterating already-Latin text is a no-op at best and destructive at worst (Latin characters consumed by accent-folding rules).

## Pitfalls

1. **It is lossy and non-round-trip.** `Достоевский` → `Dostoevskiy` → back yields `Достоевскиы`. Never use transliteration as storage — always regenerate from the original.
2. **Many-to-one collapses.** Distinct source strings can collide after romanization (`李` and `黎` both `li`); transliterated values are not unique identifiers without disambiguation.
3. **Polyphonic characters need word context.** Pinyin for Chinese requires dictionary lookup per word (多音字), not per character — a naive table produces wrong readings for common names. Use a word-aware library for Chinese romanization.
4. **Scheme ambiguity must be recorded.** Store which scheme produced a romanization (`pinyin`, `revised-romanization`, `ISO 9`, `passport-icao`) when the romanized form is user-visible or used in matching, or two systems will disagree about the "correct" spelling.
5. **Never machine-translate identifiers.** If a string feeds URLs, API keys, filenames, or dedup logic, transliteration (or stripping) is correct; MT output changes with model updates and silently breaks stored references.
