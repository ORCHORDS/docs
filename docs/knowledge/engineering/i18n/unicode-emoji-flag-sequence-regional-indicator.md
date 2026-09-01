# Unicode Emoji Flag Sequences and Regional Indicators

Flag emoji are the odd ones in the emoji set: no flag exists as a precomposed character. Every flag — from 🇺🇸 to 🇪🇺 — is a two-code-point sequence of Unicode regional indicator symbols, and the mechanism that turns "two letters" into "one flag" spans the Unicode Standard's emoji rules, ISO 3166-1 territory codes, and the exceptional inclusion of the U+1F3F4 black flag plus tag characters for subdivision flags like 🏴󠁧󠁢󠁳󠁣󠁴󠁿. Mishandling these sequences breaks counters, truncation, autocomplete, and search. This article covers the flag sequence model, the valid-pair rules, subdivision flags, and engineering practices.

## Scope

This article addresses emoji flag representation per the Unicode Standard and UTS #51 (Unicode Technical Standard #51, Unicode Emoji): regional indicator symbols U+1F1E6–U+1F1FF, the RGI (recommended for general interchange) valid pair set, subdivision flag sequences using U+1F3F4 plus Unicode tag characters, and implementation consequences for counting, editing, validation, and display. It does not cover emoji presentation selectors generally, skin-tone modifiers on people, or ZWJ sequences except for contrast.

## Workflow or implementation guidance

Regional indicator (RI) symbols map one-to-one onto letters: U+1F1E6 is "A" (the regional indicator symbol letter A), up through U+1F1FF "Z". A flag is a pair `RI1 RI2` encoding an ISO 3166-1 alpha-2 code: 🇺🇸 is U+1F1FA (U) + U+1F1F8 (S), and 🇯🇵 is U+1F1EF (J) + U+1F1F5 (P).

The rules that matter:

1. **Not every pair is valid.** The Unicode Emoji data defines the RGI set: pairs corresponding to valid ISO 3166-1 alpha-2 codes, plus the EU (🇪🇺, an exception from the ISO reserved EU code) and the United Nations (🇺🇳). Pairs like `RI(X) RI(Q)` render as the letters themselves (boxed "XQ") on conforming systems because XQ is not an assigned code. Validation is therefore data-driven: your emoji data tables (emoji-sequences.txt in the Unicode distribution) enumerate the valid pairs.
2. **Rendering pairs is font policy.** Whether a device shows 🏴 for `GB` subdivision flags or letters depends on vendor emoji fonts; the black-flag+tag construction (U+1F3F4 + tag characters spelling `gbeng`, `gbsct`, `gbwls`) is RGI for England, Scotland, Wales, and a small set of others, but support is uneven. Products must decide: filter non-RGI out of pickers, or render the letters-fallback knowingly.
3. **Counting and editing.** Per UAX #29 grapheme clustering (GB12/GB13), RI pairs combine into one grapheme cluster: 🇺🇸 is one cluster; a run of three RIs clusters as flag + lone letter. Length limits, cursor movement, and truncation must use cluster segmentation, never code units; a 280-"character" limit counting flags as 2 is wrong by the spec's own segmentation.
4. **Odd runs.** Because pairing is positional (first-RI + second-RI, third + fourth), string surgery that deletes one RI from `🇺🇸🇬🇧` (four RIs, two flags) produces `🇺🇸🇧` — one flag plus a stray letter. Any in-place editing operation must operate on cluster boundaries.
5. **Search and normalization.** Users type country names, not RI symbols; search implementations map "USA", "United States", "US" to 🇺🇸 via their own aliases (CLDR annotations provide localized keywords per emoji). NFC/NFD normalization does not compose or decompose flags — they are their own code points; collation at primary strength equates nothing here, so equality is bytewise on the sequence.
6. **Storage.** Store the sequence itself (UTF-8: 8 bytes per flag). Converting to and from ISO codes at boundaries is fine, but derive the mapping from current ISO 3166-1 plus the emoji data exceptions, and version it: territory codes get added (and politically contested), and your flag picker updated years ago should not silently start rendering deprecated pairs as letters.

A worked example: a nationality selector renders flags from ISO codes. For `US` it emits U+1F1FA U+1F1F8; for `XK` (Kosovo) it emits the valid RGI pair; for a user-entered `XQ` it must not emit a fake flag — validation against the RGI list either rejects or falls back to a text label. The picker's "list of countries" and its "list of flags" are two datasets that overlap but are not identical, and conflating them produces letters-in-boxes.

For display-order and bidi: flags are neutral in direction terms but embed cleanly; in RTL sentences a flag island usually needs no isolation since it contains no strong directional characters, but paired with adjacent neutral punctuation it can participate in bidi resolution — isolate whole mention-units ("🇺🇸!" style badges) when they sit at RTL sentence edges.

## Controls

- Source valid flag pairs from the pinned Unicode Emoji data files (emoji-sequences.txt `Emoji_RGI` set) rather than deriving from ISO tables with exceptions hand-coded; regenerate the table on Unicode version upgrades with a changelog.
- Enforce grapheme-cluster counting and editing everywhere flags can appear: chat composers, bio fields, titles; property tests with flag-heavy strings catch regression.
- Validate flag input against RGI at the boundary and fall back to text labels for non-RGI or unsupported-subdivision cases; log the fallback rate to detect data rot.
- Provide localized search aliases from CLDR emoji annotations for the locales you serve; test that searching "Deutschland" finds 🇩🇪 in a German UI.
- Snapshot-render the flag picker per target platform generation (fonts differ); do not assume subdivision flags render everywhere — gate them behind capability detection or accept letters-fallback visibly.

## Validation evidence

- Regional indicator symbols, the RGI flag pair definitions, subdivision tag sequences, and segmentation interactions are specified in UTS #51 (Unicode Emoji) and the Unicode Standard's segmentation annex (UAX #29 GB12/GB13), published by the Unicode Consortium.
- CLDR annotations supply localized emoji keywords used for search.
- A reproducible check: build the RGI pair set from the pinned emoji data and assert (a) `US` is in it, (b) `XQ` is not, (c) `gbeng` subdivision is in it — three assertions that validate the data path most implementations get wrong by hardcoding.

## Failure modes and correction

- **Counting flags as 2 characters.** Symptom: bio limits reject valid input; users complain. Correct by cluster-based counting.
- **Truncating mid-pair.** Symptom: stray boxed letters at string ends in previews. Correct by boundary-aware truncation.
- **Hardcoded ISO→flag derivation.** Symptom: new or contested territories render as letters after OS updates; or invalid pairs render as fake flags on lenient stacks. Correct by consuming the RGI data table.
- **Deleting one RI in edit operations.** Symptom: "🇺🇸🇬🇧" becomes "🇺🇸🇧" after backspace. Correct by cluster-granular editing.
- **Search only by English aliases.** Symptom: non-English users cannot find flags. Correct by CLDR-annotation-driven aliases per locale.

## Limitations

- Vendor rendering varies, especially for subdivision flags; conformance does not guarantee a glyph.
- Political status of territories is contested; shipping a flag list is shipping an editorial position — legal and policy review belongs in the loop.
- Flag validity data tracks ISO 3166-1 and Unicode decisions, which lag real-world changes.
- RI symbols also appear in non-flag contexts rarely (mathematical, stylized text); cluster rules still apply but semantics differ.

## Canonical sources

- Unicode Consortium, UTS #51: Unicode Emoji (flag sequences, RGI set, subdivision flags): https://unicode.org/reports/tr51/
- Unicode Consortium, UAX #29: Unicode Text Segmentation (regional indicator clustering, GB12/GB13): https://unicode.org/reports/tr29/
