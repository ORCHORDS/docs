# CSS Container Queries Style Container

## Scope

Using container style queries — `@container style(--flag: on) { ... }` — to style a component based on custom property values declared on an ancestor container, instead of propagating variant flags through class names or context. Covers declaring a style container, querying custom properties, combining queries, and the design shift from state-in-class to state-in-variables. Excludes size container queries (`@container (min-width: ...)`) except where the two are contrasted, and excludes JavaScript style computation, since the point of the feature is to keep variant switching in CSS.

## Workflow or implementation guidance

The scenario: a card component ships in three densities (compact, comfortable, spacious) and two emphasis levels. The density is already stored in a `--density` custom property on the card shell because padding, gaps, and type scale all derive from it via `calc()`. Emphasis, however, affects descendant nodes — a badge, a title clamp, a footer border — that live in separate shadow parts and nested components. Passing an emphasis class through every level is noisy. A style container makes the ancestor a query target for descendants.

First, opt the shell into being a container. A style query does not need `container-type`, but it does need `container-name` for the query to target it reliably when multiple containers could match.

```css
.card {
  container-name: card;
  --density: comfortable;
  --emphasis: normal;
}

.card[data-density="compact"] { --density: compact; }
.card[data-emphasis="high"]   { --emphasis: high; }
```

Descendants then query the nearest qualifying ancestor.

```css
@container card style(--emphasis: high) {
  .card__badge { font-weight: 700; }
  .card__title { text-wrap: balance; }
}

@container card style(--density: compact) {
  .card__footer { border-top: 1px solid #ccc; padding-block: 4px; }
}
```

A `style()` query matches only custom properties and only after computation, so the data-attribute mapping above is the recommended pattern: keep the public API as attributes or classes, and mirror it into custom properties on the container in one place.

Composition is where style queries earn their keep. Two independent flags produce four combinations without four classes:

```css
@container card style(--emphasis: high) and style(--density: compact) {
  .card__title { font-size: 0.95rem; }
}
```

Contrast with size queries: `@container (width > 40rem)` answers "where am I laid out" while `@container style(...)` answers "what variant am I in". Mixing them on one container is fine — declare `container-type: inline-size` alongside `container-name` when the same shell should support both, but note that adding `container-type` creates layout containment, which changes how descendants' percentage heights and floats resolve. When only style queries are needed, omit `container-type` to avoid the containment side effects entirely.

Deployment workflow: define the variant contract as a typed list (name, allowed values) in the design system docs, generate the custom-property declarations from that list in the build, and forbid descendant components from setting the flags themselves — only the container owner writes them, descendants only read through `@container`. That rule keeps the data flow one-directional and prevents the "who set this to high?" debugging sessions.

## Controls

- `container-name` on the ancestor; required in practice to disambiguate among nested containers.
- `container-type` omitted for pure style queries; set to `inline-size` only when size queries share the container.
- `@container <name> style(--var: value)` query blocks; the queried value must be a computed-value match, so `0` and `0px` are different values for length-typed properties.
- Boolean combination with `and` / `not` inside a single `@container`; multiple queries in one rule merge with `and`.
- `style()` queries support the "does this custom property exist" form via `style(--flag?)` in newer drafts — verify support before relying on it.

## Validation evidence

- Toggle each data attribute in DevTools and confirm descendant styles change with no class churn; the Elements panel shows the container badge on the ancestor once `container-name` is set.
- Assert in a visual regression suite that the four flag combinations render distinctly; style queries fail silently on a typo'd property name, so pixels are the honest check.
- Check computed values with `getComputedStyle(card).getPropertyValue('--emphasis')` — the query matches computed values, so this readout predicts exactly what the query sees.
- Confirm zero `container-type` on containers that only serve style queries if descendant layout regression tests (percentage heights, floats) previously passed.

## Failure modes and correction

- Querying a non-custom property (`@container style(color: red)`) does not match. The spec restricts style queries to custom properties; refactor to mirror that state into a custom property.
- Custom property name typo: the query evaluates as not matching, with no console error. Centralize flag names as build-time constants or a CSS `@property` registration so a typo becomes a build error.
- Unit mismatch: `--gap: 16` (unitless) never matches `style(--gap: 16px)`. Register the property with `@property { syntax: '<length>'; ... }` or enforce typed values at the authoring boundary.
- Descendant sets the flag on itself and expects to read it via `@container`: a container is not its own style-query target. Move the declaration to the true ancestor.
- Styles flash unvarianted on load when the flag is set by inline script after paint. Set the custom property in the server-rendered style attribute or a blocking style block.
- Deeply nested containers with the same name: the nearest matching name wins, which surprises teams expecting the outermost to apply. Use distinct names per level.

## Limitations

- Style queries match custom properties only; standard properties cannot be queried.
- The feature shipped in Chromium first; Firefox and Safari support arrived later, so a `@supports (container-name: --x)` guard or graceful degradation is needed during rollout.
- No transitions between variant states: changing a custom property value switches the matched query block instantly; animation of custom property changes requires `@property` registration with an animatable syntax plus the registered-property interpolation rules.
- A `style()` query cannot reference the container's own `@container` context (no recursion), and querying inherited custom properties that cascade from far up the tree still requires the queried ancestor to be the named container.
- Debugging is weaker than for class-based variants: no DOM attribute marks the active query in the markup, so tooling and code review rely on the CSS itself.

## Canonical sources

- CSS Working Group, CSS Containment Module Level 3, style containers: https://drafts.csswg.org/css-contain-3/#style-container
- MDN, `@container` at-rule: https://developer.mozilla.org/en-US/docs/Web/CSS/@container
- W3C, CSS Containment Module Level 3 (TR): https://www.w3.org/TR/css-contain-3/
- MDN, CSS containment module overview: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment
