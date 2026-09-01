# CSS Nesting Relaxed Display Condition

## Scope

Authoring and maintaining native CSS nesting after the "relaxed" syntax change that removed the mandatory `&` prefix on nested selectors. Covers what the relaxed display condition permits, where `&` is still required, the parser ambiguities that motivated the stricter original rule, and how to configure tooling so nested stylesheets compile once and lint cleanly. Excludes preprocessor nesting (Sass, Less, PostCSS nesting plugins) except where behavior differs, and excludes the `@scope` rule, which is a separate feature that overlaps in intent.

## Workflow or implementation guidance

Native nesting lets component styles live in one block. Under the original specification, every nested selector had to begin with `&` (for example `& .title { }`), and selectors starting with a type selector or a function-like token failed to parse. The relaxed syntax allows a nested selector to omit `&` whenever the sequence cannot be mistaken for a declaration.

```css
.card {
  padding: 1rem;

  .title {          /* relaxed: no & needed */
    font-weight: 600;
  }

  > .subtitle {     /* combinators still imply relative selectors */
    color: #555;
  }

  &:hover {         /* & still required when the parent must be a compound part */
    background: #f6f6f6;
  }

  &.is-active {     /* & required before a class on the parent itself */
    outline: 2px solid currentColor;
  }
}
```

The rule to internalize: omit `&` when the nested selector targets a descendant; keep `&` when the selector must attach to the parent element itself (pseudo-class, additional class, or a compound of the parent). A nested `.title` is `:is(.card) .title`. A nested `&:hover` is `:is(.card):hover`. Writing `:hover` alone nested under `.card` still works in relaxed parsing, but being explicit with `&` keeps the intent legible in review.

The ambiguity that the strict rule guarded against is declarations-versus-selectors at parse time. Tokens like `color: red;` parse as a declaration, but `color .badge { }` parses as a nested selector in relaxed mode, and a declaration whose value is missing falls through differently in older engines. Consequently, one class of mistakes — unfinished declarations — now silently becomes a selector instead of a parse error. Lint rules that require declarations to end with a semicolon catch this.

Specificity and ordering behave exactly as the flattened output does: each nesting level prepends the ancestor selector inside `:is()`, so specificity is that of the most specific argument in the `:is()` list, and source order follows the physical order of the nested blocks. Deep nesting does not add specificity per level beyond the selector contributions, but it does harm readability; a house rule of at most two or three levels keeps review tractable.

Migration workflow for a codebase on a nesting preprocessor: enable native nesting as the parse target, then delete the build step, then fix the small set of constructs where native and preprocessor semantics differ. The main difference is `&` concatenation: preprocessors historically string-concatenated `&-suffix` into a literal selector string, while native CSS uses `:is()` semantics and does not support suffix concatenation on compound parent selectors the way preprocessors did. BEM-style suffix selectors therefore need rewriting into explicit descendant or attribute selectors before the preprocessor can be removed.

```css
/* preprocessor-only construct: rewrite before going native */
.card { &__title { font-weight: 600; } }

/* native equivalent */
.card { [class*="__title"] { font-weight: 600; } }
/* better: restructure to .card .title */
```

## Controls

- Nesting depth limit enforced by stylelint (`max-nesting-depth`), typically 2 or 3.
- Stylelint rule banning preprocessor-only `&`-suffix concatenation during migration.
- `&` required for parent-attached selectors (`&:hover`, `&.is-active`, `& + &`); descendant selectors may omit it.
- `@media` and other at-rules may be nested inside a rule block without `&` and apply to the enclosing selector.
- Build pipeline: once native nesting is the target for all supported browsers, the transpile step is removed and the source is what ships.

## Validation evidence

- Cross-check computed styles on a test page against the flattened equivalent stylesheet; any divergence indicates a construct where `:is()` semantics changed the outcome.
- Run the stylesheet through the CSS parser in each supported browser engine and confirm zero console parse errors; a single unparsable block can invalidate following rules in older engines.
- Screenshot-diff component states (hover, active, disabled) before and after removing the preprocessor to catch specificity reorderings that produce the same computed declarations but different cascade winners.
- Verify final CSS payload no longer contains a nesting transpile pass by checking the served asset for `:is(` insertion patterns versus source.

## Failure modes and correction

- Unfinished declaration `color` on its own line becomes a nested selector in relaxed parsing and silently drops the property. Require semicolons via lint and format-on-save.
- `& .title` and `.title` nested at different levels both flatten to the same selector but different source order, so later nested blocks override earlier ones unexpectedly. Flatten conflicting rules or reorder within one block deliberately.
- Preprocessor `&-suffix` concatenation breaks under native parsing. Rewrite BEM suffix patterns into real descendant selectors before dropping the build step.
- Nesting a keyframes block inside a rule is not a nesting feature; `@keyframes` must be top-level (or in a nested context supported by the engine's rules for at-rules), otherwise animations never register.
- Very long `:is()` chains from deep nesting produce slow selector matching in large documents; cap depth and prefer class-scoped selectors.
- Copy-pasted nested blocks from documentation written under the strict syntax keep unnecessary `&` everywhere; harmless, but normalize with a formatter pass so the codebase reads consistently.

## Limitations

- Native nesting requires a CSS Nesting-capable engine for every supported browser; the relaxed syntax landed after the initial strict syntax, so very old evergreen versions parse only the `&`-prefixed form, and the transpile step must remain until the support floor clears it.
- No suffix concatenation: the feature deliberately does not reproduce preprocessor string concatenation on `&`.
- Every level introduces `:is()`, which means specificity takes the maximum of its arguments and zero-specificity pseudo-elements inside `:is()` are constrained; some selector rewrites are unavoidable.
- Nesting does not create a scope boundary: nested selectors still match anywhere in the document; `@scope` is the feature for lexical containment.
- Tooling maturity: some minifiers, lint plugins, and CSS-in-JS serializers predate relaxed nesting and mangle unprefixed nested selectors; pin versions that support the syntax.

## Canonical sources

- CSS Working Group, CSS Nesting Module Level 1 (relaxed syntax included): https://drafts.csswg.org/css-nesting-1/
- MDN, Using CSS nesting: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_nesting/Using_CSS_nesting
- W3C, CSS Nesting Module Level 1 (TR): https://www.w3.org/TR/css-nesting-1/
- MDN, CSS nesting module overview: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_nesting
