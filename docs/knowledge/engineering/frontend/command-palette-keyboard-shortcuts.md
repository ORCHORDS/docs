# command-palette-keyboard-shortcuts

**Issue:** Power users abandon apps that make every action a mouse hunt, and modern products answer with a command palette (Cmd+K) plus global keyboard shortcuts. But palettes accrete into unmaintainable jungles: commands hardcoded across dozens of components, shortcut collisions between the palette, the browser, and OS-level handlers, focus traps that lose the user's place, and searchable lists that render a thousand unvirtualized rows. A palette is really three small systems — a command registry, a keyboard event architecture, and a searchable UI — and each needs to be designed once at the app level.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The command registry

1. **Commands are data, not markup.** Model every action as a first-class object — id, title, keywords, icon, shortcut, availability predicate, and a `run()` function — registered in a central registry (context/store) rather than scattered JSX. This is the core of the cmdk ecosystem pattern and what makes the same command drivable from the palette, a shortcut, a menu, and docs simultaneously.
2. **Register from features, aggregate globally.** Feature modules register their commands on mount and unregister on unmount, so the palette always reflects what is actually possible in the current route/context. A statically-authored global list goes stale the moment a feature gains an action.
3. **Make availability dynamic and honest.** An `enabled`/`when` predicate per command hides or disables actions that do not apply ("Delete page" without a selected page). Showing every command and failing on run teaches users the palette lies.
4. **Add keywords and synonyms aggressively.** Search quality is mostly vocabulary coverage: "rename", "edit title", "change name" should all find the rename command. cmdk's built-in filtering accepts per-item keywords; a tiny alias list per command pays for itself immediately.
5. **Support hierarchical commands when the list grows.** Beyond ~100 flat commands, switch to grouped results (Pages / Actions / Settings) and nested submenus with breadcrumb state (cmdk renders sub-commands as a drill-in level). Flat-plus-fuzzy stops working when users must wade past 40 matches.

## Keyboard event architecture

1. **One global shortcut manager, not per-component listeners.** A single keydown listener at the app root dispatches through a registry that resolves the current handler by context (which route, which overlay is open), tracks active shortcuts, and provides the help/discovery surface. Per-component `useEffect` key listeners are how shortcut collisions and double-fires happen.
2. **Check conflicts in CI, not in bug reports.** Maintain the shortcut map as data; lint or a unit test asserts no two commands claim the same chord in the same context and none collide with browser-reserved combos (Cmd+T/W/L, Cmd+Shift+N — intercepting these either silently fails or breaks the browser).
3. **Honor input context.** Shortcuts must not fire while the user types in a text field unless the command is explicitly input-safe (or uses a two-step escape hatch). The standard rule: single-key shortcuts are suspended in inputs; modifier combos pass through, with an allowlist for the palette itself (Cmd+K must open even from inside a form).
4. **Escape and layering must be explicit.** Escape closes the topmost layer only (palette over dialog over menu), with focus returned to the layer below. A global Escape handler that closes everything at once is disorienting and a focus-management bug.
5. **Expose shortcuts in the UI and in the palette.** Render the keybinding next to every menu item that has one, list all shortcuts inside the palette itself (a "Keyboard shortcuts" command), and surface a `?`-triggered cheat sheet. Undiscoverable shortcuts are dead code.

## The palette UI

1. **Build on cmdk (React) or equivalent primitives, not from scratch.** cmdk (by Pacocoursey, used by Vercel/Linear-style apps) is the de-facto standard: unstyled, accessible combobox/dialog semantics, built-in fuzzy filter, keyboard navigation (arrows, Enter, Tab autocomplete). Wrapping it in a Radix Dialog gives focus trapping and portal rendering for free.
2. **Open with Cmd+K / Ctrl+K, focus the input, restore focus on close.** The open/close contract: palette opens with input focused; close (Escape or executed command) returns focus to the previously focused element. Losing focus origin is the most common palette bug and breaks keyboard users entirely.
3. **Rank by usage, not just fuzzy score.** Sort equal-score matches by recency/frequency (most-used commands first, recently-used bumped). A palette that always shows commands in registration order trains users it is slower than the menu it replaced.
4. **Virtualize and debounce.** Large registries (all pages, all docs entries) render through a virtualized list, and async sources (searching Notion-style page graphs) debounce input with request cancellation. Synchronous filtering of a few hundred items is fine; a thousand DOM rows per keystroke is an INP regression.
5. **Design the empty and loading states.** "No results for X" with a fallback (search docs instead / create new) keeps the palette useful; a spinner with no skeleton makes it feel broken on slow async sources.
6. **Announce results to screen readers.** The combobox pattern (ARIA 1.2) with `aria-activedescendant` tracking the highlighted option lets AT users arrow through results; result-count changes should be announced politely. cmdk ships most of this — do not wrap it in divs that strip the roles.
