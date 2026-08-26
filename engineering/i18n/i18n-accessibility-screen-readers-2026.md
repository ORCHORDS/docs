# i18n-accessibility-screen-readers-2026

**Issue:** The localized builds passed translation QA but failed blind users: `<html lang>` stayed `en` on all 14 locales so screen readers pronounced German text with an English voice (unintelligible), `aria-label`s like "Close dialog" were never extracted for translation and stayed English on every locale, alt text and `aria-live` announcements came from the wrong message catalog, and brand names got mangled because nothing was marked `translate="no"`. Accessibility and internationalization share the same substrate — language — and localized UIs ship a11y regressions unless the invisible strings and language declarations are treated as part of the localization pipeline, not an afterthought.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Language declaration

1. **Set `<html lang>` per locale, correctly.** Screen readers (NVDA, JAWS, VoiceOver) switch synthesis voice based on the declared language; German text under `lang="en"` is read with English phonetics and is effectively unusable. Use valid BCP 47 tags (`de`, `pt-BR`, `zh-Hans`), never empty strings or defaults left over from the scaffold.
2. **Update `lang` on SPA locale switches.** Client-side routing that swaps message catalogs without updating `document.documentElement.lang` leaves the voice mismatched until a full reload — hook the locale store to set it on every language change, not only at initial render.
3. **Mark inline language runs.** A Japanese product name inside an English page needs `<span lang="ja">…</span>` so the reader pronounces it as Japanese; mixed-language pages without per-run `lang` get one voice and garble everything. The same applies to transliterated blocks and quoted foreign text.
4. **Do not fake it with `xml:lang` alone in HTML.** In HTML5 the `lang` attribute is what assistive tech consumes; `xml:lang` matters for XHTML/XML pipelines and polyglot documents. Setting only one of them, or setting them inconsistently, produces tool-dependent behavior.

## Translating the invisible strings

1. **ARIA labels are user-facing text.** `aria-label`, `aria-description`, `aria-placeholder`, `aria-roledescription`, and `aria-valuetext` are read aloud — screen reader users hear the untranslated English label even when the visible UI is fully translated, often with wrong-voice pronunciation on top. Extract them into the same catalogs as visible strings and wire them via attribute-level i18n binding (the `data-i18n-attr="aria-label:key"` pattern).
2. **Alt text is localized content.** Image descriptions belong in message catalogs with the translator context of the surrounding text; a translated page with English alt text fails WCAG 3.1.2 (Language of Parts) in spirit and practice. Decorative images keep `alt=""` in every locale.
3. **Announcements in the active locale.** `aria-live` region text ("Item added to cart") must be pulled from the *current* locale at announce time, not cached from load time; a stale-locale toast announcement is worse than none because it can contradict what sighted users see.
4. **Placeholders, `title`, and tooltips are strings too.** `placeholder` and `title` are frequently forgotten in extraction passes; they are announced/read by assistive tech and visible to everyone. Add all attribute-bound strings to the i18n lint rules so a new untranslated `title` fails CI.
5. **An English label is better than none — but only as a stopgap.** Missing labels make controls unnamed (WCAG 4.1.2 failure); untranslated labels at least name the control. Track untranslated a11y strings as a distinct bug class with severity between the two.

## Mixed-language content and `translate="no"`

1. **Mark brand names and technical terms `translate="no"`.** Without it, browser auto-translate and MT-assisted pipelines localize brand names inconsistently ("Shell" → "Muschel"). `translate="no"` on the element (and the corresponding rule for TMS content) keeps them stable.
2. **Give the reader a fighting chance on foreign terms.** A brand name embedded in localized prose still needs correct pronunciation hints: wrap it with `lang="en"` plus `translate="no"` so an English-capable voice or the closest match reads it properly instead of spelling it letter by letter.
3. **Interpolated fragments break TTS phrasing.** Concatenating translated and untranslated fragments ("Added to ITEM-0042") forces a single voice to switch mid-sentence; prefer full-sentence messages with placeholders so each announcement is one coherent language run.
4. **Code, IDs, and keyboard keys stay untranslated.** Wrap literals like `Ctrl+K` in `translate="no"` and often `lang`-neutral spans so MT pipelines and screen readers treat them verbatim instead of translating "Ctrl" in Polish.

## Testing checklist

1. **Automated `lang` checks in CI.** axe-core and Lighthouse flag missing/invalid `lang` on `<html>`; extend with a custom check that `documentElement.lang` matches the active route's locale in e2e runs after every programmatic switch.
2. **VoiceOver/NVDA pass per release locale.** Spot-check that the reader actually changes voice on `lang` boundaries and that icon buttons announce the translated label (not the icon class name, not English).
3. **Catalog parity for a11y keys.** A script comparing keys used in `aria-*`/`alt`/`title` bindings against per-locale catalogs catches the "translated visible text, forgot invisible text" gap — make it a CI failure, matching the string-freeze discipline used for visible UI.
4. **Screen-reader pseudo-localization.** Extend pseudo-localization to attribute strings, not just text nodes; if pseudo-loc passes but a11y strings were never wired, the pipeline is extracting only visible DOM.
5. **Consult W3C guidance.** The WAI/i18n "Language of Parts" techniques and community write-ups on multilingual accessibility (Ben Myers' multilingual a11y guide is the standard practical reference) enumerate the `lang`-marking patterns worth copying for quotes, transcripts, and language-learning content.
