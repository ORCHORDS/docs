# CSS `@scope` and Native Nesting

## Symptom

Component styles leak. You scope with BEM, CSS Modules, or Tailwind layers,
but the moment a third-party widget or a legacy stylesheet lands on the page,
specificity wars break out. Or you want nesting ( Sass-like `&` syntax) but
the build pipeline does not have a preprocessor, and you are unsure which
nesting features are native vs. preprocessor-only.

In 2026, native CSS `@scope` and native nesting are Baseline widely
available. You can write scoped, nested CSS with zero build step.

## Native Nesting

```css
.card {
  padding: 16px;

  & .title {
    font-size: 1.25rem;
  }

  &:hover {
    box-shadow: var(--shadow-lg);
  }

  & > p {
    margin: 0;
  }
}
```

The `&` refers to the parent selector, exactly like Sass. No preprocessor,
no PostCSS plugin — the browser parses it directly.

### When you can omit the `&`

```css
.card {
  .title { font-weight: 600; }   /* valid — implied & */
}
```

You can omit `&` for simple descendant selectors. But you MUST use `&` when
it is part of a compound selector or pseudo-class: `&:hover`, `&.active`,
`.is-dark &`.

## `@scope` — limits where rules apply

```css
@scope (.card) {
  .title { color: var(--text); }
  p { margin: 0; }
}
```

The `.title` rule only applies to `.title` elements inside `.card`, even if
the same `.title` class is used elsewhere on the page. Unlike a descendant
selector `.card .title`, `@scope` does not increase specificity — the rule
stays at `.title` specificity.

### Lower bounds (the `to` clause)

```css
@scope (.post) to (.ad-slot) {
  p { color: #333; }
}
```

This scopes `p` styles to paragraphs inside `.post`, but STOPS at any
`.ad-slot` descendant. Paragraphs inside the ad slot are not affected —
useful for user-generated content with embedded widgets.

## Gotchas

### Nesting does not work without a parent selector in some cases

```css
/* INVALID — top-level nesting needs a parent */
@media (min-width: 600px) {
  .card { /* ... */ }
}
```

This is fine. But this is NOT fine:

```css
.card {
  @media (min-width: 600px) {
    padding: 24px;
  }
}
```

Actually the above IS valid — you can nest at-rules inside style rules. The
thing that fails is nesting a style rule directly inside another without
either `&` or a clear descendant:

```css
.card {
  .title { /* valid */ }
  &title { /* INVALID — needs a combinator or nothing */ }
}
```

When in doubt, use `&`. It is never wrong.

### Specificity does NOT increase with `@scope`

This is the main difference from `.card .title`. The scoped `.title` keeps
specificity `(0,1,0)`. That means a later, unscoped `.title` rule with equal
specificity can still win. If you need higher specificity, raise it inside
the scope block deliberately.

### Nesting deep chains hurt readability and performance

```css
.a {
  & .b {
    & .c {
      & .d { color: red; }
    }
  }
}
```

This compiles to `.a .b .c .d` — a 4-level descendant chain that is fragile
(hard to override) and slower to match. Flatten it.

### `@scope` with `:scope` pseudo-class

Inside a scope block, `:scope` refers to the scope root:

```css
@scope (.tabs) {
  :scope { display: flex; }   /* styles the .tabs element itself */
  .tab { padding: 8px; }
}
```

### Native nesting does not include Sass `@extend` or mixins

Native CSS nesting is syntax only. There is no `@extend`, no `@mixin`, no
control flow. If you relied on those, you still need a preprocessor or a
build-time tool.

### Preprocessor nesting differs subtly

Sass and Less resolve `&` at compile time with slightly different semantics
for complex selectors. If you are migrating from Sass, test the output —
especially for selectors like `& + &` (adjacent siblings), which native CSS
handles but some older Sass patterns do not translate cleanly.

## When to still use CSS Modules or a build step

- You need guaranteed-unique class names at build time (CSS Modules hashes).
- Your team relies on `@extend` or mixins from a design system.
- You target browsers older than the Baseline date (Safari 16.5+, Chrome
  112+, Firefox 117+ for nesting; Safari 17.4+ for `@scope`).
