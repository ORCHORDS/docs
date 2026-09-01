# Unicode Normalization Forms: NFC, NFD, NFKC, NFKD and Their Ambiguities

Two strings can look identical and differ in bytes: `é` as a single precomposed code point (U+00E9) or as `e` plus combining acute (U+0065 U+0301). Unicode normalization forms canonicalize these variants — NFC composes, NFD decomposes, and the compatibility forms NFKC/NFKD additionally fold format characters (ligatures, superscripts, fullwidth forms) into their plain equivalents. Choosing the wrong form, mixing forms, or assuming normalization is idempotent-safe across domains creates duplicate accounts, failed lookups, and security holes. This article covers the four forms, the canonical equivalence versus compatibility equivalence distinction, and the ambiguities that trip implementations.

## Scope

This article addresses normalization forms as specified in UAX #15 (Unicode Normalization Forms): canonical composition/decomposition, compatibility decomposition, the normalization algorithm's stages (decomposition, canonical ordering, composition), interaction with default-ignorable and variation-selector characters, and stability guarantees. It covers selection guidance for storage, identifiers, search, and interop. It does not cover normalization-sensitive encryption, IDN domain validation specifics (confusable policy), or tailoring beyond the standard forms.

## Workflow or implementation guidance

The four forms:

- **NFD** — canonical decomposition: `é` → `e` + combining acute; Å (U+00C5) → A + ring; Korean syllables decompose to jamo.
- **NFC** — canonical decomposition followed by composition: recombines where a precomposed character canonically exists. NFC is the recommended general default for the web and interchange.
- **NFKD** — compatibility decomposition: everything NFD does, plus folding compatibility characters: ligature ﬁ (U+FB01) → `f` `i`; superscript ² → `2`; fullwidth Ａ → `A`; Roman numeral Ⅳ → `I` `V`.
- **NFKC** — compatibility decomposition followed by composition.

The central distinction: **canonical equivalence** (NFC/NFD space) preserves the abstract identity of text — NFD and NFC forms of the same logical text are canonically equivalent and should render identically after shaping. **Compatibility equivalence** (NFKC/NFKD) deliberately loses information: `ﬁ` becomes `fi` and `²` becomes `2`, changing both rendering width and sometimes meaning (2 squared versus 2). Compatibility forms are for matching and comparison, not for storage of user content.

Selection guidance by domain:

1. **User-visible storage: NFC on ingest.** Normalize to NFC once at the boundary (input validation), store the result, and treat the stored form as canonical thereafter. Mixed-form columns are the root of downstream duplicate-detection failures.
2. **Identifiers and uniqueness: NFC, plus uniqueness checked on NFD-derived form where inherited systems demand it.** Account names and document IDs compared after NFC prevent the classic "two visually identical usernames" bug. Case folding for uniqueness must additionally apply case folding before comparison, and fold per Unicode's default case folding with the locale-independent algorithm.
3. **Search indexing: choose per corpus.** Exact-ish search wants NFC; forgiving search often wants NFD or compatibility-folded (NFKC) keys plus case folding. But beware: NFKC keys make `2` match `²` — sometimes desired in code search, catastrophic in a math archive. Document the choice per index.
4. **Filenames and URLs: NFC, with rejection of the small set of characters that change under normalization.** The Unicode "identifier" guidance recommends excluding characters that are not stable under NFC (a tiny set, e.g. some Hangul jamo edge cases historically); systems like DNS and many filesystems canonicalize to NFC or NFD (macOS HFS+ famously NFD, iOS filenames follow), and cross-platform sync without a chosen form sprouts duplicate files named identically to the eye.
5. **Never mix forms in one pipeline stage.** The recurring defect: component A compares with NFC, component B normalizes to NFD, C passes through; equality checks at the joins fail for exactly the accented-content users. Pick the form at the architecture level, write it into the interface contracts, and lint for stray normalization calls.

Ambiguities and edge cases worth knowing:

- **Composition exclusions.** Some decomposable sequences never recompose under NFC (the composition exclusion table, e.g., U+0344 COMBINING GREEK DIALYTIKA TONOS); NFC of some strings still contains combining marks, so "NFC means no combining marks" is false.
- **Canonical ordering.** Combing marks reorder by combining class under all forms; strings differing only in mark order are canonically equivalent. Comparisons must normalize, never bytewise.
- **Not idempotent under transformation in composition tails? No — all four forms are idempotent: normalize(normalize(x)) = normalize(x).** The trap is different: **normalizing a substring then concatenating can differ from normalizing the whole string**, because composition can cross the join (a starter at the end of segment A plus a combining mark at the start of segment B). Concatenate first, normalize second, whenever composition may cross boundaries — chunked streaming normalizers handle this with a carry state.
- **Default ignorables and variation selectors.** Variation selectors (U+FE0F emoji presentation) are inherited combining classes and survive canonical normalization; NFKC removes some format characters but keeps emoji selectors — matching pipelines that strip them must do so explicitly and symmetrically.
- **Unassigned code points.** Normalization is defined so future character additions cannot change existing normalized text (stability policy): new characters start out with decompositions that preserve prior outputs. Still, upgrade your Unicode tables deliberately: normalization output can change for text containing newly-assigned characters' canonical equivalents introduced by later versions.

A worked example: a CRM ingests leads from three sources; one sends `Jose\u0301`, another `José` (NFC), a third `Ｊｏｓé` fullwidth-prefixed from a CJK form. Dedup on NFC bytes matches the first two and keeps the third separate; dedup on NFKC + casefold merges all three — which is right depends on business intent, and the pipeline should encode that intent explicitly in one function with tests.

## Controls

- Enforce a single normalization form per data domain at the write boundary (NFC default for content), implemented in one shared library; forbid scattered normalize calls via review and dependency linting.
- Add a `normalized` marker or checksum column when ingesting from untrusted sources so downstream consumers can assert the contract instead of re-normalizing defensively (re-normalization is cheap but masks violations).
- Property-test: for a corpus of tricky strings (accented Latin, Hangul syllables and jamo mixtures, Arabic with marks, Indic conjuncts with nukta, emoji with modifiers and selectors, fullwidth Latin), assert pipeline equality: f(NFC(x)) behaves identically whether x arrives as NFC or NFD.
- For substring-concatenation code paths, unit-test the join cases (starter + combining mark across the boundary) or use a streaming normalizer that carries state.
- Track the Unicode version of your normalization tables in the build manifest; upgrades run the corpus test suite and changelog output diffs.

## Validation evidence

- The definitions of NFC, NFD, NFKC, NFKD, the composition exclusion table, canonical ordering algorithm, and the normalization stability policy are specified in UAX #15: Unicode Normalization Forms, published by the Unicode Consortium.
- The Unicode Character Database supplies the decomposition mappings the algorithm consumes.
- A reproducible check: take `U+0041 U+030A` (A + ring) and `U+00C5` (Å); NFC maps both to U+00C5, NFD maps both to the two-code-point sequence — and `U+FB01` (ﬁ) is unchanged by NFC but becomes `f i` under NFKD — three observations that pin the canonical/compatibility boundary precisely.

## Failure modes and correction

- **Mixed-form columns.** Symptom: duplicate-looking rows, lookups missing entries. Correct by a one-time NFC migration plus boundary normalization.
- **NFKC stored as the display form.** Symptom: ligatures and fullwidth typography destroyed, superscripts flattened in user content. Correct by storing NFC and deriving compatibility forms only in the comparison index.
- **Normalize-substring-then-concatenate.** Symptom: rare strings fail equality after segment-wise processing. Correct by whole-string or stateful streaming normalization.
- **Bytewise equality on user text.** Symptom: visually identical strings unequal after copy-paste from different sources. Correct by comparing normalized forms at defined checkpoints.
- **Normalization in security comparisons without case folding policy.** Symptom: `Jose\u0301` vs `JOSÉ` treated distinct where the product intended sameness (or vice versa). Correct by explicit (form, folding, locale-sensitivity) triple in the auth/identity comparison spec.

## Limitations

- Normalization does not handle confusables: Cyrillic `а` and Latin `a` remain distinct under every form; anti-spoofing needs confusable data on top.
- Compatibility folding decisions are one-way information loss; reversing is impossible.
- Locale-sensitivity: default algorithms are locale-independent; language-specific matching (Turkish dotless i) requires explicit tailoring outside the four forms.
- Renderer behavior can still differ between canonically equivalent strings in deficient font stacks; normalization guarantees equality of meaning, not of every legacy renderer's output.

## Canonical sources

- Unicode Consortium, UAX #15: Unicode Normalization Forms: https://unicode.org/reports/tr15/
- Unicode Consortium, UTS #10: Unicode Collation Algorithm (interaction of normalization with comparison): https://unicode.org/reports/tr10/
