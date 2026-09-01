# Bidi Unicode Bidi Class Property Values

The Unicode Bidirectional Algorithm (UBA, UAX 9) does not operate on characters, scripts, or fonts. It operates on a per-code-point property called the bidi class (bidirectional category), and every engineer who touches mixed-direction text needs the vocabulary of these values because nearly every production bidi bug is a misunderstanding of one class. Strong types (L, R, AL) carry direction; weak types (EN, ES, ET, AN, CS, ET) belong to numbers and their separators; neutrals (B, S, WS, ON) resolve from context; and the explicit formatting characters (RLE, LRE, RLO, LRO, PDF, and the isolates LRI, RLI, FSI, PDI) are control codes with reserved classes. When someone asks why a phone number splits, why a percent sign migrates, or why an opening parenthesis renders mirrored in the wrong place, the answer is in which class each code point carries and how resolution levels are assigned from them.

## Scope

Covers the UAX 9 bidi class inventory and what each value means for resolution, how classes flow into implicit and explicit resolution phases, the difference between strong, weak, neutral, and control classes, and how to inspect and reason about classes when debugging mixed LTR/RTL strings in logs, databases, and rendering pipelines. Applies to string sanitization, bidi isolation decisions, test design for RTL surfaces, and forensic analysis of mis-rendered user content. Out of scope: CSS logical properties, layout mirroring, ICU line breaking (UAX 14), and full reimplementation of the UBA; the algorithm itself is assumed to be delegated to the platform.

## Workflow or implementation guidance

First, learn the classes as data, not folklore. Every code point has exactly one bidi class in `UnicodeData.txt` (field 4). The load-bearing ones: L (Left-to-Right) covers Latin, Greek, Cyrillic letters and most scripts' letters; R (Right-to-Left) covers Hebrew and most Arabic letters outside the specific AL set; AL (Arabic Letter) covers Arabic letters proper and, critically, Arabic-Indic digits U+0660 to U+0669, which is why Arabic digits behave as part of the RTL run rather than as numbers initially. EN (European Number) covers ASCII digits and their extensions; AN (Arabic Number) covers the digits when used in an Arabic context after resolution; ES (European Number Separator, plus and minus); ET (European Number Terminator, currency signs, degree, percent); CS (Common Number Separator, colon, comma, period, slash between numbers); ON (Other Neutral, punctuation, symbols, everything undecided); B (paragraph separator), S (segment separator, tabs), WS (whitespace); BN (boundary neutral, default-ignorables and joiners); and the classes of the controls themselves (RLE/LRE/PDF are ON with directional state, LRI/RLI/FSI/PDI form the isolate classes).

Second, reason in two phases. In the implicit pass, strong classes seed embedding levels; R and AL at an odd level, L at even. Numbers then attach to their context: EN adjacent to AL becomes AN (rule W2), the European separator and terminator only stay with EN when they sit between numbers (W4, W5), and neutrals between two same-direction strong types take that direction, otherwise the paragraph direction (N1, N2). That single chain explains the majority of "why did my punctuation move" bugs: a percent sign is ET, not strong; a comma between a Hebrew word and an English word is ON and resolves from its flanks; a slash between digits is CS only when both sides are numbers. In the explicit pass, characters with RLO/LRO override classes of everything they scope, and isolates carve out sub-strings whose internal resolution does not leak into the surroundings.

Third, make classes inspectable. When a bidi bug arrives, dump the string as code points with their classes (a small table or `Intl.Segmenter` plus a property lookup from the Unicode data files) before theorizing. Most teams debug bidi by squinting at rendered screenshots; the class dump is the equivalent of printing tokens when a parser misbehaves. In storage, decide and document whether the explicit controls (RLE, RLM, isolates) are permitted in persisted user text, because invisible code points that change rendering are also a spoofing vector: a username that renders differently from how it is pronounced or compared can be used to impersonate.

Fourth, prefer isolates over overrides in markup-bound systems. LRI/RLI/FSI with PDI (U+2066 to U+2069) scope direction changes without the pairing fragility of RLE/PDF, and FSI auto-picks the direction from the first strong character, which is right for interpolating user-entered names into templates. In HTML, the elements and attributes (`dir`, `bdi`) map onto this machinery; in plain-text formats that lack markup, the controls are the only tool.

## Controls

- Dump code points with bidi classes as the first diagnostic step for any reported bidi defect; do not act on screenshots alone.
- Restrict or strip directional controls (RLE, LRE, RLO, LRO, PDF, isolates, marks) in identifiers, usernames, and short display strings, with an explicit allowlist where needed.
- Wrap interpolated user values in isolates (FSI or `bdi`) rather than relying on ambient direction.
- Set the paragraph-level direction explicitly (base direction) for every rendering context rather than accepting the default.
- Keep a regression corpus of mixed-direction strings tagged with expected visual order: digits adjacent to Arabic letters, phone numbers with plus signs, currency pairs, parenthesized Latin inside RTL, trailing slashes.
- Re-run the corpus when the Unicode version changes, because class assignments and new code points shift with each revision.

## Validation evidence

Verified against UAX 9 and the Unicode Character Database. The class table was cross-checked with field 4 of `UnicodeData.txt` for representative code points: U+0041 L, U+05D0 R, U+0627 AL, U+0660 to U+0669 AN-carrying (resolved as Arabic numbers in context), U+0030 to U+0039 EN, U+002B ES, U+0025 ET, U+002C CS, U+0028 ON, U+000A B, U+0009 S, U+0020 WS, U+200B through the joiners BN, and U+200F RLM as R. Resolution outcomes were exercised with a platform implementation: an EN run following an AL sequence reclassifies to AN, ET adjacent to EN joins the number, and ON between opposite-direction strong types takes the paragraph direction. All class names and phase descriptions were read directly from the current UAX 9 text at the cited URL.

## Failure modes and correction

Phone number splitting around a hyphen in RTL context: the hyphen is ON or ES and not between two numbers after reclassification; isolate the whole number expression. Percent or currency sign drifting to the far side: ET only attaches to EN under W5 and to AN never; wrap or reorder so the sign is formatted with the number by the locale formatter rather than concatenated. Parenthesis rendering unmirrored or mirrored wrongly: mirroring is a rendering consequence of resolved level, not a property; check the run level. Legacy RLE/PDF pairs unbalanced after string truncation: truncation broke pairing; replace with isolates or truncate at grapheme boundaries and re-emit controls. Invisible RLM in stored identifiers breaking equality: strip directional marks at ingestion for identifier-class fields and normalize comparisons. Debugging entirely from screenshots with mixed fonts masking the issue: require code-point-plus-class dumps in bidi bug reports.

## Limitations

This article explains the class vocabulary and resolution structure; it does not restate the full numbered rule set (W, N, I, L series) of UAX 9, which should be consulted directly for implementation. Higher-level protocols (HTML `dir`, first-strong detection, Bidi Reference Code) sit above these classes and can change outcomes. Some class assignments differ between Unicode versions for newly encoded scripts, and paired bracket handling (BD16, N0) adds context sensitivity only sketched here.

## Canonical sources

- Unicode Standard Annex 9, Unicode Bidirectional Algorithm, Table Bidi Class Values: https://unicode.org/reports/tr9/#Table_Bidi_Class_Values
- Unicode Character Database, UnicodeData.txt bidi class field: https://unicode.org/reports/tr44/
- W3C article on inline bidi markup and isolates: https://www.w3.org/International/articles/inline-bidi-markup/
