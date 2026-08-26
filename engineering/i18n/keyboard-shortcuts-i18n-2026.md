# keyboard-shortcuts-i18n-2026

**Issue:** Keyboard shortcuts are designed and tested on US QWERTY and then break for international users. Character-based shortcuts fire on the wrong letter or not at all on AZERTY (where the number row requires Shift), on Cyrillic, Greek, and Arabic layouts (where Latin letters are not printed), and on non-Latin IMEs. Menu mnemonics conflict or point at characters absent from the localized strings, and shortcut hints rendered from US-QWERTY assumptions teach users the wrong keys. Getting this right requires understanding how the platform maps physical keys to characters, deciding per shortcut whether muscle memory or semantics matters, and localizing the display layer separately from the binding layer.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The core model: physical keys versus characters

1. **Distinguish event.code from event.key on the web.** event.code reports the physical key (KeyZ, Digit1, Backquote) based on a US-QWERTY reference layout, while event.key reports the character the layout actually produces (я on Russian, é on French). Binding to event.code preserves QWERTY muscle memory across layouts; binding to event.key preserves semantic meaning (the character the user sees). Choose per shortcut, and never mix them unconsciously.

2. **The OS already maps many accelerators through the Latin layout.** Windows and most Linux toolkits translate Ctrl-based accelerators through the Latin equivalent of the active layout, which is why Ctrl+Z/X/C/V mostly work for Russian and Greek users even though the printed letters differ. Real-world bug reports (for example, KDE tracking Ctrl+W producing Ctrl+Z behavior on a stacked Russian-phonetic AZERTY layout) show the mapping has edge cases with stacked layouts — do not assume it is free.

3. **Layouts deliberately preserve shortcut positions.** Most national layouts (including Cyrillic and Dvorak variants) keep Z/X/C/V/A/W in QWERTY physical positions precisely for shortcut muscle memory. Binding common editing shortcuts to physical keys aligns with this convention; rebinding them per layout breaks it.

4. **Dead keys and IME composition intercept keystrokes.** On layouts with dead keys (French, Spanish) or under active IME composition (CJK), key events are consumed or transformed before your handler runs. Guard shortcuts during composition events (keydown with isComposing or keyCode 229) to avoid firing mid-composition.

## Choosing bindings that travel

1. **Avoid keys that do not exist everywhere.** Bracket keys, backtick, and the number row without Shift are awkward (AZERTY) or inaccessible (some tablet keyboards, Russian layouts) on common layouts. Prefer letters plus modifiers, arrows, and Enter/Escape/Backspace, which exist on effectively all layouts.

2. **Reserve the platform-conventional shortcuts.** Undo, cut, copy, paste, select-all, find, and save must keep their system conventions; users on any layout already know them. Microsoft's guidance for global hotkeys warns against remapping system-wide conventions — spend your novelty budget on app-specific shortcuts only.

3. **Prefer physical-key binding for spatial shortcuts.** Shortcuts that map to spatial concepts (navigation, pane focus, editor commands) should bind to physical positions so they feel identical everywhere; semantic shortcuts (search for a term, insert the character) may bind to characters.

4. **Single-key shortcuts are the highest risk.** A plain keypress as a shortcut (common in power-user apps: j/k navigation) collides with text input, IME composition, and dead-key entry. Require a modifier, or gate single-key shortcuts on non-editing focus and IME-inactive state.

## Localizing the display layer

1. **Render hints from the same binding model the handler uses.** If the handler listens to event.code, a hint that says Ctrl+Z is a lie for an AZERTY user (they press the key at QWERTY-Z's position, labeled differently). Either render the character the user's active layout produces (via the Keyboard API layout map when available) or render an unambiguous spatial description for physical bindings.

2. **Localize menu mnemonics independently.** The underlined accelerator letter in a menu item must be a letter present in the localized label; assigning mnemonics is part of the string localization workflow, not the shortcut definition. Check mnemonic collisions across the whole menu in each locale (two items claiming the same letter).

3. **Use platform-correct modifier naming.** Display Command on macOS and Ctrl (or the localized equivalent, e.g. Strg in German) elsewhere; drive this from platform detection plus the UI locale, not hard-coded English strings.

4. **Provide a discoverable shortcut sheet.** A rendered shortcut cheat-sheet (help overlay) generated from the binding registry keeps hints consistent and gives international users a place to learn what actually fires on their layout.

## Testing matrix

1. **Test with real layouts, not simulated keys.** Manually switch the OS input source to French AZERTY, Russian ЙЦУКЕН, and an active CJK IME, and run the full shortcut suite; automated events with synthetic key codes do not reproduce layout mapping and IME interception.

2. **Assert on both event.code and event.key in tests.** Unit-test the binding logic with synthetic events carrying both physical and character values, covering the stacked-layout case (Cyrillic active, Latin-equivalent expected) that produced real-world bugs.

3. **Verify the hint text matches the behavior per locale.** Screenshot the shortcut sheet and menus in each supported UI locale on at least one non-QWERTY layout, confirming hints and mnemonics are truthful.

4. **Fuzz shortcuts during composition.** Fire shortcuts mid-IME-composition and mid-dead-key sequences and assert they do not fire; firing mid-composition corrupts CJK text entry and is a top complaint from power users in those locales.
