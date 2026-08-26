# webvtt-subtitle-caption-localization

**Issue:** Video is now a standard product surface — onboarding tours, feature explainers, help content, recorded webinars — and every locale you support eventually asks for subtitles. WebVTT is the only caption format browsers natively render via the HTML5 track element, and it is deceptively simple: a text file of timed cues. The localization difficulty lives in the editorial constraints that ride on top of the format: subtitle translation must fit hard reading-speed budgets (about 15-17 characters per second comfortable, 20-21 CPS a common ceiling per 2025 industry guidance), line-length limits (32-42 characters per line, two lines maximum), and fixed cue timing that does not stretch because German expanded the sentence 30 percent. Translators are not just translating; they are condensing to fit a box measured in characters, seconds, and lines simultaneously. Engineering owns the tooling that makes those constraints visible and enforceable, the timing adjustments when translations do not fit, and the text-direction handling for RTL and bidi captions.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Format constraints and what they mean for translators

1. **WebVTT imposes no content limits — industry standards do.** The format happily carries a 300-character cue for a 2-second window; the result is unreadable. Reading speed, line length, and line count are editorial standards (Netflix-style 42 characters per line, ~20 CPS adult ceiling, two lines) that your pipeline must compute and enforce, because neither the browser nor the file format will.
2. **Cues are atomic translation units with invisible context.** Each cue is translated in isolation unless you give translators the surrounding cues, speaker names, and a shot of the video. Delivering a plain VTT file into a translation tool loses who is speaking and what was said before and after; supply a sidecar context or use a TMS workflow that shows adjacent cues.
3. **VTT styling and positioning do not localize.** Cue settings (line, position, align) and ::cue styling are authored once against the source timing and layout. A translation that runs two lines where the source ran one can collide with the player controls or on-screen text; treat cue geometry as a per-language review item, not a shared constant.
4. **Speaker and voice tags travel inside the text.** The v speaker tag (v Narrator) and inline markup (b, i, timestamp activations) are part of the cue payload that translators see and can break. Strip or protect markup in the translation interface, and validate that every tag in the source cue survives into the translation.

## Reading-speed budgets across locales

1. **Target 15-17 CPS for comfortable adult content; treat 20-21 CPS as the ceiling.** Current subtitling guidance converges on these numbers: adults max around 250 wpm (roughly 20 CPS), children's content lower (around 200 wpm), fast sports and action averaging 17-20 CPS. Encode the budget per content class, not globally.
2. **Measure CPS on the translated text, not the source.** A source cue at 14 CPS can become 18 CPS in German or Spanish after expansion; the budget check must run post-translation, inside the QA step, against the same cue timings.
3. **Set a minimum duration too.** Cues shorter than roughly one second (or about 0.3-0.375 seconds per word in pacing terms) flash unreadably even when short. QA should flag both over-budget (too fast) and under-duration (too brief) cues.
4. **Let translators condense, and tell them they may.** The core subtitle-translation skill is meaning-preserving compression, not verbatim translation — verbatim output that blows the CPS budget forces either re-timing or bad UX. Style guides for each target language must state the condensation policy and the terminology that may not be dropped.

## Line length and expansion management

1. **Hard-wrap at the locale's per-line limit, two lines max.** Thirty-two characters is the safe norm; 42 is the aggressive upper bound used by streaming-style guidelines. Break lines at natural linguistic boundaries (after punctuation, between clauses) — never mid-word for Latin scripts, and let the translator place the break, since a syntactically wrong break reads as an error even within the character budget.
2. **Plan for expansion asymmetry.** Rule-of-thumb expansion from English is roughly 25-35 percent for German and French, less for Spanish and Portuguese, and compression for CJK targets (more meaning per character, but stricter line rules). When translations exceed limits, the escalation order is: condense wording, then split the cue, then shift timings — re-recording narration is the last resort.
3. **CJK and no-space scripts need different wrapping rules.** Chinese and Japanese can break almost anywhere except before forbidden characters, so a character-count check suffices; Thai has no spaces and needs dictionary-based segmentation for breaks; Arabic scripts should not be broken inside a connected letter group. A single wrap algorithm will fail all of these differently — check per script.
4. **Never machine-wrap translated cues at deploy time.** Automatic wrapping at render time ignores linguistic boundaries and produces broken lines in every script. Wrapping is a translation-time decision baked into the file.

## Timing and cue collisions

1. **Re-time when translation forces structural changes.** Splitting one cue into two requires dividing the source duration (respecting the minimum-duration rule); merging two into one requires their union with a gap check. Tooling should propose the timing edit, and QA should verify no cue overlaps its neighbor after edits.
2. **Preserve synchronized entry/exit semantics.** A cue that is deliberately synchronized to on-screen action (a button highlight, a UI walkthrough step) must keep its start time even when the text must be condensed to fit — flag action-synced cues in the source so translators know timing is frozen and only wording may change.
3. **Keep cue gaps visible.** A tiny or negative gap between consecutive cues causes flicker or double-render in some players. QA computes inter-cue gaps per file and per language variant; a translated file can violate gaps the source never had because cue splitting changed the topology.

## RTL and bidirectional caption text

1. **Set direction explicitly for RTL caption tracks.** Relying on the Unicode bidi algorithm alone mangles cues that mix RTL text with Latin brand names, numbers, or code snippets. Use the WebVTT vertical/line semantics plus a dir cue setting or ::cue override where supported, and test in every target browser because bidi handling in caption renderers is inconsistent.
2. **Apply bidi isolation to embedded opposite-direction runs.** Wrap Latin-in-Arabic runs with Unicode isolates (FSI/PDI or LRI/RLI) rather than relying on paired brackets heuristics — the same UAX #9 discipline as in-app strings, covered in the bidi articles, applies inside cue text.
3. **Punctuation at RTL line ends is the visible bug.** Trailing periods, question marks, and parentheses jump to the wrong side when direction metadata is missing; screenshots of end-user rendering per locale are the only trustworthy verification, per the workspace screenshot-evidence rule.

## QA checklist before shipping a locale

1. **Automate the measurable checks in CI.** Per file and locale: CPS within budget, line length within limit, max two lines, minimum duration, no overlapping cues, markup intact, direction set for RTL. A linter pass makes the editorial standards enforceable instead of aspirational.
2. **Human-review a sample against the video.** Machines cannot judge whether the condensation preserved meaning or the line breaks land on natural boundaries; a linguistic spot check of the highest-traffic videos per locale catches systematic issues the linter cannot.
3. **Test playback on real target devices.** Captions render differently across browsers and mobile players (font, wrap, bidi, styling support); verify on the actual device matrix with screenshots before declaring the locale done, and log renderer errors during playback per the standard monitoring protocol.
