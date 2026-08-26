# transactional-email-push-localization

**Issue:** Transactional messages — verification emails, password resets, order confirmations, shipping notifications, push alerts — are the highest-stakes strings a localized product sends, because they must reach the user in the right language even when the user never opens the app again to pick it. Current-generation pipelines localize the in-app UI but still fire English password-reset emails to the whole world, or solve it by duplicating one template per language until the password-reset flow diverges across 15 maintained copies. The engineering problems: capturing and persisting per-user locale and timezone, choosing between single-template-plus-catalog and per-locale template architectures, formatting embedded dates/currency/numbers inside message bodies, handling RTL email HTML, and localizing push titles within OS length limits.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Locale capture and storage

1. **Capture locale at signup, not at send time.** Best-practice guidance for multilingual transactional email at scale is to record the user's preferred language during onboarding and store it on the user profile. At send time the job looks up a stored value; it must never guess from the user's IP or the request's Accept-Language, because transactional sends are often triggered by background jobs with no request context.
2. **Store full BCP-47 when you need it.** A bare language code loses date formats and currency conventions (de vs de-AT, zh vs zh-Hant-HK). Store what the user actually chose including region, and normalize at read time for template selection.
3. **Default and fallback policy.** When no locale is known (legacy users, system-generated accounts), fall back to a documented default and let the email include a language switcher link that persists the choice back to the profile — a one-click fix for years of English-only legacy users.
4. **Timezone and unit persistence.** Store the user's IANA timezone separately from locale; a de-CH user in Singapore still wants shipping dates in Singapore time formatted with German month names. Never derive timezone from locale — Brazilian Portuguese speakers live in nine timezones.

## Template architecture

1. **One template, locale-driven substitution.** The two documented architectures are a single template pulling translated strings from a catalog per locale versus separate templates per language. The single-template approach with i18n keys (the same catalogs the app uses) keeps layout logic in one place and is the maintainable default; per-locale templates are justified only when legal content or radically different layouts (RTL) demand it.
2. **Share catalogs, not just infrastructure.** Pull email strings from the same translation management system and namespaces as the product UI where wording overlaps ("Reset password", "Confirm your email"), so terminology stays consistent and translators review each string once. Email-only namespaces (subject lines, preheaders) still live in the same TMS with the same review gates.
3. **Subjects, preheaders, and length limits.** Localized subject lines routinely run 30-50 percent longer than English (German, Russian); design for the longest locale and check rendered subjects against common client truncation (~40-60 visible characters). Push notification titles face hard OS limits and truncate more brutally — keep push keys separate with per-locale length guidance in translator notes.
4. **ICU message syntax for interpolated values.** Order confirmations embed counts, names, amounts: use ICU MessageFormat (select/plural) so "1 item / 2 items / 5 items" pluralizes correctly per locale instead of concatenating translated fragments. Fragment concatenation is the number-one source of broken machine-like localized emails.

## Formatting inside message bodies

1. **Dates, times, and currency via the profile's locale plus timezone.** Format embedded values server-side with the same ICU stack as the web app (ICU4C/ICU4J/Intl-facing libraries): "3. September 2026" for de-DE, with timezone converted before formatting. An unformatted ISO timestamp in a localized email signals the pipeline skipped this step.
2. **RTL email HTML.** Email clients have patchy CSS support; RTL emails need dir="rtl" on the body/table, logical text alignment via direct attributes, and mirrored table column order — CSS logical properties are not reliably honored in email engines. Maintain the RTL variant as a tested template variant, verified in the screenshot-based email preview tooling.
3. **Plain-text alternative per locale.** Every multipart email needs a text/plain part; generate it from the same catalog with line lengths recomputed per language (word lengths differ) rather than naively stripping tags from the HTML.
4. **Links and localized landing pages.** A localized email with English-link destinations breaks the experience at the last step: parameterize destination URLs with the message's locale so the reset-password landing page opens in the same language the email spoke.

## Pipeline and QA

1. **Render-before-send validation.** Assert before dispatch that every key used by the chosen template exists in the recipient's locale catalog with all placeholders resolved; a missing key must fall back to the default locale's full string, never ship as "email.reset.greeting" to an end user.
2. **Preview tooling with real fixtures.** Wire the email/push rendering path into in-context translation preview (screenshots of rendered templates per locale) so translators and reviewers see the assembled message, not isolated strings — catching overflow, broken pluralization, and RTL layout before send.
3. **Per-locale seed tests.** CI sends each template to a fixture inbox per locale on every catalog change; snapshot the rendered bodies (HTML and plain text) and diff them. This is the only layer that catches a translator edit breaking an ICU placeholder or an RTL mirror.
4. **Change velocity decoupling.** Because email templates depend on catalogs shared with the app, gate marketing-driven rewording separately from transactional templates: password-reset wording changes deserve slower review than a promotional subject line, even when both live in the same TMS.
