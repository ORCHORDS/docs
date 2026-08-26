# brand-literals-stay-english

**Issue:** Translating brand literals breaks trust + RTL layout
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main
**Author:** the platform team
**Status:** documented (intentional design choice)

## Symptom
You run a translation pass and the Turkish locale shows:
"the platform'e hoş geldiniz" — looks fine.
But the Russian locale shows: "the platform token'a hoş geldiniz" — weird.
And the Arabic locale shows: "the platform مرحبا" — broken RTL with English on the left of Arabic.

## Root cause
Three categories of text should NEVER be translated:

1. **Brand literals** — `the platform`, `the platform`, `$the platform`, `the platform`
2. **Proper-noun standards** — `GDPR`, `DSA`, `DMCA`, `CCPA`, `PECR`,
   `LGPD`, `PIPEDA`, `RGPD`, `eIDAS`, `WCAG`, `AODA`, `A11Y`, `NCMEC`,
   `ICO`, `NDA`, `SOC 2`, `ISO 27001`, `PCI DSS`
3. **Crypto contract addresses** — `0x1234...abcd` (Solana + EVM)

Translating these:
- Dilutes the brand (`the platform` in Arabic is unrecognizable)
- Breaks RTL layout in Arabic/Hebrew (English on the left of Arabic
  flips with `<bdi>` wrap)
- Adds risk of mistranslation (regulators care if "GDPR" becomes
  "General Data Protection Regulation" in your TOS — the law has a
  specific name)

**Source:** Unicode Bidi Algorithm (UBA) for RTL safety:
https://www.unicode.org/reports/tr9/

## Fix
Two layers:

### Layer 1: Translation pass
When generating per-locale JSON, copy the English value verbatim for
brand literals and proper-noun standards. Don't even attempt translation.

```python
BRAND_LITERALS = {
    'the platform', 'the platform', '$the platform', 'the platform', 'the platform token',
    'Beta', 'Testnet', 'Mainnet', 'Genesis'
}

PROPER_NOUN_STANDARDS = {
    'GDPR', 'DSA', 'DMCA', 'CCPA', 'PECR', 'LGPD', 'PIPEDA', 'RGPD',
    'eIDAS', 'WCAG', 'AODA', 'NCMEC', 'ICO', 'SOC 2', 'ISO 27001',
    'PCI DSS', 'A11Y', 'API', 'SDK', 'TLS', 'MFA', 'SSO', 'SAML',
    'SCIM', 'MFA', 'OTP', 'KYC', 'AML', 'CFT', 'OFAC', 'NFT',
    'EVM', 'ERC-20', 'ERC-721', 'SPL', 'JIT', 'AOT'
}
```

### Layer 2: RTL-safe wrap
In JSX, wrap brand literals in `<bdi>` to isolate them from the
surrounding text direction:

```jsx
<p>
  {t('welcome.prefix')}{' '}
  <bdi>the platform</bdi>{' '}
  {t('welcome.suffix')}
</p>
```

`<bdi>` (BiDi Isolation) tells the browser to treat the content as
directionally neutral, so Arabic + English in the same paragraph
don't fight each other.

## Verification
- **Visual QA:** `/workspace/visual-qa/screenshots/` — 9 pages × 19 locales
  show brand literals rendered in English across all locales
- **Coverage report:** Per-locale long-prose-same-as-en count is 1-11
  (most: 1-4), all from brand literals + proper-noun standards
- **Live:** https://a9815932.the platform-ca0.pages.dev — Arabic locale has
  `the platform` rendered with `<bdi>` wrap

## Gotchas
- **Don't translate "Beta" to "β" in Greek.** It's not a Beta-test
  version, it's a brand modifier.
- **"Genesis" is both a brand literal AND a religious term.** Don't
  translate it (e.g. "創世記" in zh-CN). The brand takes priority.
- **Some standards have localized acronyms but the ENGLISH acronym
  is the legal reference.** "RGPD" (FR) and "GDPR" (EN) are the same
  law. Render the ENGLISH acronym to match legal documents.
- **In Spanish (es), "PCD" (persona con discapacidad) is the term
  for "person with disability".** But "WCAG" stays as-is.
- **`<bdi>` is the modern equivalent of `<span dir="ltr">` with
  isolation.** Use `<bdi>` for new code.

## Related
- the platform issue #open-issue-academy-glossary (Academy translation gaps — 60+ glossary terms)
- Unicode Bidi: https://www.unicode.org/reports/tr9/
- MDN `<bdi>`: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/bdi
