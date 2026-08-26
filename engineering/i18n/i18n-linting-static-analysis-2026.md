# i18n-linting-static-analysis-2026

**Issue:** A team has an i18n library installed, yet every sprint review surfaces a new hardcoded English string someone snuck into JSX, a `t('common.save')` call pointing at a key that does not exist, and a locale file with 300 keys nobody references anymore. Code review cannot catch this at human speed across a large codebase. This article covers the 2026 static-analysis stack for i18n — ESLint rules that ban literal UI strings, extraction diffs that catch drift in CI, undefined-key and unused-key checkers, and placeholder/ICU validation — so these bug classes are machine-caught before merge.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 layers of i18n static analysis

1. **Literal-string linting (editor/PR time).** `eslint-plugin-i18next`'s `no-literal-string` rule flags any JSX text or string literal headed for the UI. This is the first line of defense against the "Cancel" buried in markup.
2. **Extraction diff (CI time).** Run `i18next-parser` or `formatjs extract` in CI on every PR and diff against the committed catalog: new keys the developer forgot to add, and removed keys that are now dead, fall out of the diff automatically.
3. **Undefined-key checking.** `eslint-plugin-i18next-no-undefined-translation-keys` (and equivalent typed-key setups) verifies every `t('...')` argument resolves to a real key in the translation files — catching typos and renames that render as raw keys in production.
4. **Unused-key detection.** AST scanners (Better i18n CLI, i18next-scanner output, or a custom script comparing extracted keys against catalog keys) report catalog entries nothing references, so the catalog shrinks deliberately instead of rotting.
5. **Placeholder and ICU validation.** Post-extraction checks assert that `{count}` placeholders, HTML tags, and ICU syntax survive translation round-trips unchanged in every locale file — a malformed German plural clause fails the build instead of shipping a crash or gibberish.

## The 5 eslint-plugin-i18next no-literal-string options

1. **`markupOnly: true`.** Restricts checking to JSX text nodes (`<p>Cancel</p>`) instead of every string literal, dramatically cutting false positives in logic-heavy files — the usual starting configuration for existing codebases.
2. **`ignores` / `ignorePattern`.** Allowlists for legitimate literals: className values, test IDs, `aria-*` tokens, analytics event names. Maintained as a reviewed list, not scattered inline disables.
3. **`ignoreCallee`.** Skips calls to known-safe functions (`classNames(...)`, `dayjs(...)`) so wrapping code doesn't force artificial `t()` plumbing through non-UI utilities.
4. **`validateTemplate`.** Checks template-literal interpolations so `` `Hello ${name}` `` is flagged even though it is not a plain literal — the concatenation bug's modern disguise.
5. **No autofix — by design.** The plugin deliberately ships without `--fix` for this rule because replacing a literal with a key requires human judgment (naming, context, plural shape). Budget review time accordingly; do not expect an automated migration.

## The 5 complementary tools

1. **`@spaced-out/eslint-plugin-i18n`.** Independent rule set including `no-literal-string` and `no-html` (translatable strings must not embed markup), usable outside the i18next ecosystem.
2. **`eslint-plugin-i18next-no-undefined-translation-keys`.** Cheap, popular guard against typo'd keys; pairs with `i18next` typed resources for compile-time key checking in TypeScript.
3. **`@lingui/cli extract --strict`.** In Lingui projects, strict mode fails when extraction finds messages without macro annotations — the same "no silent drift" contract for a different stack.
4. **`i18n-lint` (jwarby).** Scans HTML/template files for hardcoded strings where a JS linter cannot reach — useful for server-rendered templates and email HTML.
5. **Better i18n CLI / custom AST scanners.** Cross-file analysis (hardcoded strings, missing keys, unused keys) reported in one pass; for unusual frameworks, a ~100-line Babel-traverse script over "string literals in JSX" covers the 80% case.

## The 5 CI-gate rules for rollout

1. **Start warn-only, then flip to error.** Turning `no-literal-string` on cold across a legacy app yields thousands of hits; run it `warn` for a sprint, fix the top-offending files, then set `error` for new code via path-scoped overrides (`files: ['src/features/**']`).
2. **Scope rules to UI code.** Exclude `scripts/`, `tests/`, `*.config.ts`, and generated directories — literals there are not user-facing, and noise kills adoption faster than any miss.
3. **Fail PRs on catalog drift.** The extraction job commits or comments the diff; a PR that adds code strings without touching the catalog is either blocked or auto-labeled `i18n-debt` for triage.
4. **Gate on placeholder integrity per locale.** For each locale file: same set of `{placeholders}` as the source, valid ICU where used, no unbalanced tags. This is the check that catches broken machine-translation output.
5. **Report unused keys monthly, not per-PR.** Key deletion needs product judgment (campaigns, legal copy); surface it as a scheduled report with owners rather than a red X on someone's refactor.

## Gotchas

- **False positives kill the rule.** One week of noisy `no-literal-string` warnings and developers inline-disable it forever; invest early in the `ignores` list and `markupOnly`.
- **Extraction order matters.** Extract → validate placeholders → undefined-key check, as separate CI steps; one mega-script hides which stage failed.
- **Dynamic keys defeat naive checkers.** `` t(`btn.${variant}`) `` is invisible to static extraction — lint for it (`no-dynamic-key` style custom rule) and centralize such lookups in one switch.
- **Keys can exist but be empty.** An empty string is a valid JSON value that passes "key present" checks and renders blank UI; validate non-empty and non-source-duplicate where locales must diverge.
- **Codemods, not autofix.** Plan one codemod pass (jscodeshift) for bulk externalization when flipping rules to `error`; per-file manual fixes do not scale past a few hundred strings.

## Source URLs (verified 2026-08-15)

- https://github.com/edvardchen/eslint-plugin-i18next
- https://github.com/edvardchen/eslint-plugin-i18next/blob/main/docs/rules/no-literal-string.md
- https://www.npmjs.com/package/@spaced-out/eslint-plugin-i18n
- https://www.npmjs.com/package/eslint-plugin-i18next-no-undefined-translation-keys
- https://jwarby.github.io/i18n-lint/
- https://better-i18n.com/en/i18n/cli-code-scanning/
- https://github.com/formatjs/formatjs/discussions/3253
- https://dev.to/woovi/using-eslint-to-fix-wrong-i18n-usages-2h39

## Related

- `i18n/i18n-string-externalization-2026.md` — the extraction tooling this layering builds on
- `i18n/continuous-localization-cicd.md` — where the extraction job sits in the wider pipeline
- `i18n/locale-data-validation-2026.md` — validating locale data files themselves
- `i18n/flat-dotted-vs-nested-keys.md` — key structure the linters enforce
