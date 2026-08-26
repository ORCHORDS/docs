# headless-ui-architecture-patterns

**Issue:** A team needs an accessible combobox/date-picker/menu but the design system has its own visual language, so installing a styled component library (MUI, Ant) means fighting a theme war with `!important` and override slots. Meanwhile hand-rolling the component means re-implementing ARIA roles, keyboard navigation, and focus management — and shipping the bugs that follow. The headless pattern splits the difference: a component library that ships all behavior (state, a11y, keyboard, focus, positioning) and zero styling, with composition APIs that let you own 100% of the markup. By 2026 this is the dominant architecture — Radix UI, React Aria, Base UI (v1.0 December 2025, from the Radix/MUI/Floating UI teams, now an opt-in base for shadcn/ui), and TanStack's headless adapters all embody it.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The core idea: behavior/style separation

1. **A headless component is a state machine plus an API, not a DOM tree.** It owns open/close state, selection model, typeahead, roving tabindex, ARIA wiring, and portal positioning — then hands you components/props (`Trigger`, `Content`, `render` functions) that render your markup with the right behavior attached. You write the JSX and CSS; the library guarantees the semantics.
2. **Accessibility is the product being bought, not the styling.** The expensive part of a combobox is `role="combobox"`, `aria-expanded`, `aria-activedescendant`, keyboard model (arrows/Enter/Escape/typeahead), and focus restoration — precisely what headless libraries implement to WAI-ARIA spec and test across screen readers. Rebuilding this per-project is where a11y bugs breed.
3. **Unstyled means Tailwind-friendly, CSS-Modules-friendly, anything-friendly.** Because no styling opinions ship, headless primitives slot into an existing design system without a theme layer; this is exactly why shadcn/ui composes Radix (and now optionally Base UI) primitives under Tailwind classes.
4. **Controlled and uncontrolled modes are part of the contract.** Quality headless components accept `value`/`onValueChange` (controlled) or `defaultValue` (uncontrolled) uniformly, so forms integrate (react-hook-form, RHF resolvers) without hidden internal state.
5. **The pattern extends past components.** Headless is an architecture for any reusable frontend logic: headless tables (TanStack Table), headless virtualizers (TanStack Virtual), headless carousels (Embla). Data/behavior engines that make zero assumptions about rendering.

## Choosing a library (2026 landscape)

1. **Radix UI Primitives.** The incumbent: ~50 unstyled primitives, excellent composability, battle-tested in production design systems; powers shadcn/ui by default. Choose for breadth and community muscle memory.
2. **Base UI.** The successor effort by the creators of Radix, Floating UI, and MUI; reached v1.0 on 2025-12-11 with a stable API, simpler package structure, and modern styling hooks. Choose for greenfield projects betting on the forward path; expect a smaller ecosystem of copy-paste examples than Radix for now.
3. **React Aria (Adobe).** Behavior hooks (`useComboBox`, `useDialog`) rather than components: maximum control and the strongest a11y pedigree (Adobe's testing feeds the WAI-ARIA Authoring Practices). Choose when you need hook-level composition or non-React-idiom rendering; note React Aria Components now offers the component-layer API too.
4. **Headless UI (Tailcast/Netlify lineage).** Smaller surface (menu, listbox, combobox, dialog, disclosure) but the simplest API; tightly associated with Tailwind. Choose for small projects that only need the classic five interactive widgets.
5. **Decision heuristics.** Evaluate on: WAI-ARIA conformance evidence, controlled/uncontrolled symmetry, portal and positioning story (Floating UI integration), SSR support, and whether source is copyable (shadcn-style) or dependency-installed. Bundle-size differences are secondary — primitives tree-shake well.

## Building your own headless component (when you must)

1. **Start from the ARIA authoring pattern, not a screenshot.** Each widget has a spec'd keyboard model and role structure (APG patterns); implementing those first and styling second is what separates a headless build from a div-with-click-handlers build.
2. **Split into a state machine and presentation slots.** Keep open/highlighted/selected state in a controller (context provider) and expose parts as compound components with data attributes (`data-state="open"`, `data-highlighted`) — CSS keys off attributes, so styling never re-enters the logic. This is the compound-component pattern documented in `react-compound-components.md`, applied headlessly.
3. **Wire a11y via props, not DOM ownership.** Use `useId` for label/control linkage, spread the controller's getter props (`getTriggerProps()`, `getContentProps()`) onto whatever element the consumer renders, and let `asChild`/`render`-style props let consumers swap the rendered element entirely.
4. **Centralize keyboard handling with roving tabindex.** One keydown handler on the container implementing the pattern's key map, with `tabIndex={0}` only on the active item, beats per-item handlers; document the key map as public API.
5. **Ship positioning and portals as part of behavior.** Popovers need to escape overflow contexts (portal) and reposition on scroll/resize (Floating UI). A headless menu without a positioning story pushes the hardest bug onto every consumer.

## Integration and testing patterns

1. **Test behavior with Testing Library, styled with Storybook.** Headless components are ideal axe-core + jest-dom targets: assert roles, keyboard traversal order, and ARIA state (e.g., `aria-expanded` toggling) — assertions that survive any restyle. Visual regression (Chromatic/Storybook) covers the styling layer separately.
2. **Screen-reader smoke tests in CI.** A nightly VoiceOver/NVDA script over the storybook of primitives catches regressions unit tests cannot; the a11y contract is the part you promised users.
3. **Version the primitive layer behind your own wrapper components.** Wrap `<Menu>` etc. in your design system's API so swapping Radix for Base UI later is an internal refactor, not an app-wide rewrite — the same facade rule as any dependency.
4. **Watch SSR and hydration.** Portals and ids must be deterministic server-side; test the component inside an SSR harness (Next.js/React Router SSR) not just client-only tests, per `hydration-mismatch-debugging.md`.
5. **Document the keyboard contract in-story.** Each primitive's story should include a "keyboard interactions" panel (interaction tests) so the supported keys are executable documentation, discoverable by every consumer.
6. **Related reading in this knowledge base:** `react-compound-components.md` (the composition mechanics underneath), `native-popover-dialog-anchor.md` (which platform primitives can now replace headless ones for popover/dialog), `tailwind-component-patterns.md` (the styling half of the stack), `web-accessibility-focus-management.md`.
