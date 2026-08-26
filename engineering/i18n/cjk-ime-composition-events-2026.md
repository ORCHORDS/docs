# cjk-ime-composition-events-2026

**Issue:** A chat app fires its "Enter to send" handler while a Japanese user is still converting kana to kanji, sending the half-composed romaji string instead of the selected text. A search-as-you-type field re-filters on every keystroke of Chinese pinyin input, flickering through dozens of garbage intermediate states. Both bugs come from treating IME (Input Method Editor) input like plain keyboard input. This article is the 2026 playbook for `compositionstart` / `compositionupdate` / `compositionend`, the `isComposing` flag, and the browser quirks (notably Safari's event ordering and `keyCode === 229`) that make naive fixes fail.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 events and flags

1. **`compositionstart`.** Fired when the user begins an IME session (e.g., typing romaji into a Japanese field). The current text is about to become editable "pre-edit" text that the user will convert.
2. **`compositionupdate`.** Fired as the composition text changes — each pinyin syllable, each conversion candidate swap. This is intermediate state; never persist or submit it.
3. **`compositionend`.** Fired when the user commits the composed text. The `event.data` holds the final string; only now is the value "real" from the app's perspective.
4. **`KeyboardEvent.isComposing`.** True while a composition session is active. Every `keydown` handler that triggers actions (Enter-to-send, Esc-to-cancel, arrow-key navigation) must early-return when this is true.
5. **`keyCode === 229`.** Browsers report keyCode 229 for keys routed through the IME. Safari (WebKit bug 165004) fires some `keydown` events *after* `compositionend` with `isComposing === false`, so robust handlers check both: `if (e.isComposing || e.keyCode === 229) return;`.

## The 5-step gating pattern

1. **Track composition state.** Keep a boolean (`isComposingRef.current = true` on `compositionstart`, false on `compositionend`) so non-keyboard logic can consult it. In React, use a ref, not state, to avoid re-render races.
2. **Gate action keydowns.** In the Enter handler, return early when `e.nativeEvent.isComposing || e.keyCode === 229`. The Enter that *confirms a candidate* belongs to the IME, not to your submit logic.
3. **Defer search/filter until `compositionend`.** For typeahead, ignore `input`/`onChange` while composing; on `compositionend`, run the search once with the final value. Algolia's InstantSearch and similar libs document this exact pattern.
4. **Debounce anyway.** Even after gating, debounce 200-300 ms: Japanese users often commit several words in sequence, and you want one search per phrase, not per commit.
5. **Handle `compositionend` as the source of truth.** Read the final value from the target (or `event.data`) there, then run validation, submit enablement, and character counters against it.

## The 5 classic IME bugs

1. **Enter submits mid-conversion.** The most-reported CJK bug in chat apps; fixed only by the isComposing/229 gate above, not by debounce alone.
2. **Live validation rejects pinyin/romaji.** A username regex like `/^[a-zA-Z0-9]+$/` rejects the intermediate romaji or accepts it wrongly, flipping error messages on/off while the user types. Validate on blur or `compositionend`, never per-keystroke.
3. **`maxLength` counts composition operations.** Some browsers enforce `maxlength` against raw keystrokes during composition, truncating candidates. Use JS-based length checks on the composed value (grapheme-aware) instead of the attribute for CJK fields.
4. **Autocomplete/mention popups steal keystrokes.** A mention menu listening for raw `keydown` intercepts the IME's Enter/Space, breaking conversion. Popups must respect the same isComposing gate.
5. **React `onChange` double-fires.** React's synthetic events historically fired extra `onChange` during composition (react issue #<number>); gating on composition state rather than diffing values avoids the class of bugs entirely.

## The 5 testing practices

1. **Test with a real IME.** Automated `element.type()` does not produce composition events. On macOS add Chinese/Japanese/Kana input in test plans; Playwright can dispatch synthetic `compositionstart`/`compositionend` events as an approximation.
2. **Assert the gate exists.** Unit-test the keydown handler with a fake event `{ isComposing: true, keyCode: 229, key: 'Enter' }` and assert no submit happened.
3. **Simulate Safari ordering.** Fire `compositionend` *before* the final `keydown` in one test case to catch the WebKit-bug-165004 ordering.
4. **Test search deferral.** Type "nihongo", assert zero searches fired during composition, assert exactly one fired after `compositionend` with the committed value.
5. **Log composition telemetry.** In QA builds, log composition session boundaries per field; CJK users' drop-off in a field often correlates with an unhandled composition bug.

## Gotchas

- **`isComposing` is on the native event.** In React use `e.nativeEvent.isComposing`; the synthetic event re-exposes it as `e.isComposing` but ordering quirks make the keyCode 229 backstop mandatory.
- **Never block the keystroke itself.** Do not `preventDefault()` IME keydowns — you will break conversion. Only skip *your own* handler logic.
- **`event.data` differs between `compositionupdate` and `compositionend`.** Only the latter is final; some browsers insert the committed data into the input *after* the event, so read the input's value on the next tick if you need the merged text.
- **Chinese vs Japanese vs Korean differ.** Chinese IMEs compose long pinyin runs (defer aggressively); Japanese compose short segments repeatedly (gate every segment); Korean IMEs compose jamo per-syllable with frequent inline updates — the same gating pattern covers all three.
- **Password fields are exempt.** IMEs are disabled for `type="password"`, so gating code there is dead weight — but keep it for search, chat, notes, and any mention/tag input.

## Source URLs (verified 2026-08-15)

- https://developer.mozilla.org/en-US/docs/Web/API/Element/compositionstart_event
- https://www.stum.de/2016/06/24/handling-ime-events-in-javascript/
- https://dev.classmethod.jp/en/articles/react-ime-composition-pitfalls/
- https://github.com/facebook/react/issues/3926
- https://bugs.webkit.org/show_bug.cgi?id=165004
- https://route360.dev/en/post/algolia-ime-input/
- https://dev.to/oikon/improving-japanese-input-ux-in-multilingual-applications-properly-handling-ime-conversion-2ild

## Related

- `i18n/locale-aware-input-validation.md` — validation timing interacts with composition end
- `i18n/grapheme-cluster-iteration.md` — counting characters in composed CJK text
- `i18n/chinese-japanese-cjk-fonts.md` — rendering the text the IME produces
