# design-token-pipelines

**Issue:** Design decisions — colors, spacing, typography, radii, motion durations — leak into frontends as hardcoded hex values, magic pixel numbers, and one-off Tailwind classes, so a rebrand or dark-mode rollout becomes a repo-wide find-and-replace with inevitable misses. A design token pipeline treats those decisions as named, versioned data: designers edit tokens in a source of truth, CI validates and transforms them, and the build emits CSS custom properties, Tailwind config, TypeScript constants, and platform assets (iOS/Android) from the same input. The practice matured significantly in 2025: the W3C Design Tokens Community Group published the DTCG Format Module 2025.10, the first stable version of the interchange format, and tooling such as Style Dictionary v4 and Terrazzo now consume it natively. Getting the pipeline right — token taxonomy, naming, validation, and governance — is the difference between tokens as real infrastructure and tokens as a second, conflicting source of truth.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Token taxonomy and naming

1. **Three-tier architecture.** Use core (primitive) tokens for raw decisions (blue-500, space-4), semantic (alias) tokens for intent (color-action-primary, space-padding-card), and component tokens for overrides on specific components (button-primary-background). Each tier may only reference the tier below it.
2. **Names express intent, never appearance.** A token named color-text-link can be re-themed from blue to purple without renaming; color-blue-600-for-links cannot. The $type field carries the appearance concern, so names should stay purpose-oriented.
3. **Group tokens by domain, not by screen.** Grouping by color, dimension, typography, shadow, and motion keeps the set finite; grouping by page produces thousands of near-duplicate tokens that rot immediately.
4. **Composite tokens for multi-part values.** DTCG composite types (border, shadow, typography, stroke) bundle sub-values (width, style, color) so a component consumes one coherent token instead of three that can drift apart.
5. **Ban style logic in names.** Avoid gradient-stop-2-of-hero-banner; if a value needs that much context it is a component token, not a global one.

## The DTCG standard (2025.10)

1. **First stable spec.** The Design Tokens Format Module 2025.10 (published October 2025 by the W3C Design Tokens Community Group) defines the JSON file format for exchanging tokens between tools — the first stable revision after years of draft iterations.
2. **Core syntax.** Tokens are objects with $value (the value), $type (color, dimension, number, fontFamily, duration, cubicBezier, composite types), and optional $description and $extensions. Groups are nested objects; references use the {group.token} alias syntax with braces.
3. **Tool support is broad but versioned.** Style Dictionary v4 supports the DTCG format natively (though full 2025.10-revision support is still landing), Terrazzo targets it directly, and Tokens Studio can sync in DTCG versus its legacy format. Validate inputs against the spec in CI rather than trusting hand-edited JSON.
4. **$extensions for tool-specific data.** Keep non-standard metadata (Figma variable IDs, theming scopes, deprecation flags) inside $extensions so the file remains portable across tools that ignore it.
5. **Alias depth is finite.** Spec tooling resolves chained aliases, but deep chains (semantic-of-semantic-of-core) make debugging resolution failures painful; cap the chain at two hops.

## Pipeline architecture

1. **Tokens as code.** Store token JSON/YAML in the repo (or sync it from Tokens Studio/Figma variables via GitHub integration) and treat changes as pull requests with review, diffing, and semantic versioning — the same as any other code.
2. **Style Dictionary v4 as the default transformer.** It reads DTCG-format sources, applies platforms (web, ios, android), and writes outputs: CSS custom properties, SCSS maps, Tailwind theme JS, Swift/Kotlin constants, and JSON for documentation sites. Register preprocessors (for example the Tokens Studio sd-preprocess package) when designers sync in tool-specific shapes.
3. **Validate before build.** Run a token validator in CI that checks DTCG conformance, unresolvable references, circular aliases, and $type mismatches (a dimension value referenced by a color alias). Fail the build on invalid tokens; never let a broken alias ship as a raw unresolved string.
4. **One build, many outputs.** Emit CSS custom properties as the runtime layer for theming (including per-theme attribute selectors for dark/high-contrast mode) plus compile-time constants for platforms that cannot read CSS.
5. **Diff reporting in review.** Post a rendered diff of changed tokens (name, old value, new value, affected themes) on every token PR so reviewers can see blast radius without opening JSON files.

## Multi-platform and theming outputs

1. **CSS custom properties for runtime theming.** Web themes switch by swapping property values under a selector (data-theme="dark") — tokens compiled to custom properties let you re-theme without rebuilding JavaScript.
2. **Static outputs where CSS cannot reach.** Native mobile (Swift/Kotlin), canvas rendering, email templates, and PDF generation need token values baked at build time; the same DTCG source feeds these via different platform configs.
3. **Tailwind integration through the theme.** Map semantic tokens into the Tailwind theme object (or CSS-first theme variables in v4) so utilities like bg-action-primary reference tokens instead of raw palette values — Tailwind remains the ergonomic layer, tokens remain the truth.
4. **Theme matrices explode; bound them.** Dimensionality (brand x mode x density x platform) multiplies fast. Generate only the combinations you actually ship, and encode the combination in the output file name so stale combinations are obvious in review.

## Governance and anti-patterns

1. **Deprecate, never silently rename.** Renaming a token breaks every consumer at once. Mark old names deprecated in $description, keep them as aliases to the new name for a transition window, and grep consumers before removal.
2. **No raw values in component code.** Enforce with lint rules (stylelint declaration-property-value-allowed-list for colors, or a custom ESLint rule on style props): if a hex or px literal appears in a component, CI fails. Exceptions belong in a documented allowlist.
3. **Avoid two sources of truth.** If designers use Figma variables, sync them into the repo automatically; a hand-copied duplicate diverges within weeks. The repo build output is the only artifact applications consume.
4. **Version the token package.** Publish generated outputs as a versioned internal package (or release tag in the monorepo) so apps upgrade deliberately and can pin while mid-migration.
5. **Measure adoption.** Track the ratio of token-referencing styles to literal values in the codebase as a KPI; pipelines that are not enforced drift back to hardcoding regardless of tooling quality.
