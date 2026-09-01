# Korean Locale Honorific Speech-Level Selection

Korean encodes social relationship into grammar itself. Where English adjusts tone with word choice, Korean selects among six or seven speech levels (존댓말 versus 반말 and their graded forms) that change verbs, pronouns, and sentence endings. An application that renders Korean must decide which level its interface speaks, and that decision is not cosmetic: 반말 (intimate low form) from a stranger brand reads as rude or as an edgy marketing choice, while excessively formal forms can read as distant or robotic. This article covers the speech-level model, the product decisions involved, how CLDR and ICU expose related formality (and where they do not), and engineering practices for shipping Korean honorifics deliberately.

## Scope

This article addresses Korean speech-level selection in localized products: the morphological system (hasoseoche, hapsyoche/formal polite, haeyoche/polite informal, haoche, hageche, haerache/plain), pronoun and address-term implications, register consistency across UI surfaces, and the interaction with CLDR formality levels. It covers copy strategy and validation. It does not cover Korean grammar pedagogy,IME handling, word-breaking, or Hangul encoding.

## Workflow or implementation guidance

Korean speech levels are verb-ending paradigms. The load-bearing ones for software copy:

- **해요체 (haeyoche)** — the polite informal level. Default for most consumer UI: friendly but respectful. "저장되었습니다" style endings (actually -습니다 family is 합쇼체; 해요체 gives "저장됐어요") read warm; both appear in real products.
- **합쇼체 (hapsyoche)** — formal polite. Reads professional, official, service-announcing. Financial, governmental, and enterprise products lean here: "저장되었습니다".
- **하십시오체/하오체/하게체** — higher-formal or mid-levels; rare in modern UI, occasionally used for deliberate archaic or military flavor.
- **해라체 (haerache)** — plain declarative, used in news headlines and technical documentation for compactness.
- **해체 (haeche, 반말)** — intimate. Used by youth-facing brands, games, and social apps as a deliberate voice choice.

Selection is a brand decision with grammatical consequences that cascade:

1. **Pick one primary level per product voice and document it** in the locale style guide with example strings for success, error, empty, and marketing surfaces. Mixed levels within one screen read as errors even when each sentence is grammatical.
2. **System messages and human-authored content can differ deliberately.** A banking app may use 합쇼체 for system toasts but 해요체 in the chat with support agents; the boundary must be explicit so translators do not "correct" one to match the other.
3. **Address terms follow level.** 반말 voice pairs with "너/당신" avoidance via second-person ellipsis (Korean naturally drops pronouns); formal voice uses 존칭 honorific prefixes (존댓말 markers like -시-) and titles (님: "사용자님", "고객님"). Copy that mixes 반말 endings with 님 address terms is incoherent.
4. **Formality as data:** CLDR defines a formality level in locale extensions for some formatting contexts, but there is no `-u-` keyword that flips UI copy speech level; speech level lives in your translation catalog, not in locale identifiers. Formality keywords that do exist govern certain formatter behaviors (for example, date/time pattern formality in some stacks) and must not be assumed to drive verbs.
5. **Plural/counter and verb agreement don't change with level, but imperative forms do:** buttons ("저장", "저장하세요", "저장하십시오") must match level; a 버튼 reading "저장" (noun form) is level-neutral and a common safe choice for labels, while helper sentences carry the level.
6. **Machine translation defaults toward 합쇼체/해요체 blends;** post-editing rules should specify target endings per string category (button label = noun form; error message = 해요체 question/answer per guide) so MT post-editing doesn't drift.

A worked example, one sentence at three levels for a file-upload error:

- 합쇼체: "파일을 업로드하지 못했습니다. 다시 시도해 주십시오."
- 해요체: "파일을 업로드하지 못했어요. 다시 시도해 볼까요?"
- 반말: "파일 업로드 실패! 다시 해 봐."

All three are correct Korean; they are three different products. The choice belongs to brand and locale leads, and once made, every string is validated against it.

Consistency checking can be partially mechanical: regular expressions over sentence-final endings can classify strings into probable levels (-습니다/ㅂ니다 → hapsyo; -어요/아요/~-네요 → haeyo; -했다/한다 → haera; -했어/해 → hae). Lint the catalog: flag strings whose classified level differs from the declared voice per surface, and route exceptions (legal notices pinned to 합쇼체 even in a 반말 product) through an explicit allowlist.

## Controls

- Maintain a Korean style guide declaring the speech level per surface (system toasts, marketing, chat, legal) with ≥10 canonical example sentences per level; translators onboard against it.
- Lint the Korean catalog with ending-classification regexes and surface the distribution of levels per screen in CI; fail on undeclared mixing.
- Include level-sensitive strings in linguistic QA sign-off specifically (not just generic review), with a native reviewer checking register coherence across a full user journey, not isolated strings.
- Keep pronoun/address-term policy (님 usage, second-person ellipsis) adjacent to the level declaration so they change together, not independently.
- Track third-party content (MT pre-translation, LLM-generated copy) through the same lint before merge; generated Korean drifts toward mid-formal blends.

## Validation evidence

- Speech-level grammar and usage norms are documented in standard Korean-language references and the Korean language's regulatory context (National Institute of Korean Language guidance on 존댓말 usage in public materials).
- CLDR/ICU locale data governs formatting formality knobs where present, per UTS #35 (LDML); speech-level selection for UI copy is a catalog/content decision the standard does not encode — the reason it must be managed as style-guide policy.
- A reproducible check: classify the endings of all strings in a Korean catalog with the regex families above and chart the mix; real shipped products show dominant single-level distributions with deliberate clusters (legal in hapsyo), while unmanaged catalogs show scattered blends — the exact defect the lint exists to catch.

## Failure modes and correction

- **Random level mixing across screens.** Symptom: users perceive the app as buggy or unprofessional; support tickets cite "tone inconsistency". Correct with the style guide plus catalog lint.
- **MT-induced drift.** Symptom: over months, strings regress to generic 합쇼체 even in a 반말 product. Correct by routing all new/edited strings through the level linter in CI.
- **Level mismatch with address terms.** Symptom: 반말 endings plus 님 honorifics in the same sentence. Correct by pairing level and address policy in the guide and checking them in the same review.
- **Assuming a locale keyword sets register.** Symptom: engineers expect formality from a `-u-` extension and ship unreviewed copy. Correct by documenting that speech level lives in strings, and wiring QA to read the actual copy.
- **Inconsistent imperatives on buttons.** Symptom: adjacent buttons mixing noun labels and leveled verbs. Correct by choosing noun-form labels or one imperative level for all actions.

## Limitations

- Ending-based classification is heuristic; quoted speech, noun-final sentences, and code-switched fragments misclassify and need human review queues.
- Register interacts with dialect (Gyeongsang vs standard) and generation; global Korean copy targets standard Seoul register by default.
- Honorific verb morphology (-시-) extends beyond endings into subject honorification, which regex lints cannot fully validate.
- Style guides need periodic refresh as brand voice evolves; a frozen guide ossifies tone.

## Canonical sources

- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML) — locale extensions and formality-related data: https://unicode.org/reports/tr35/
- Unicode, ICU User Guide — locale handling underlying Korean formatting: https://icu.unicode.org/
