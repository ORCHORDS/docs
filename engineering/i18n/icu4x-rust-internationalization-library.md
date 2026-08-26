# ICU4X — Rust-Based Internationalization for Resource-Constrained Environments

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application targets WebAssembly, mobile, or embedded environments
where bundling the full ICU C++ library (30+ MB) is impractical. You
need accurate locale-aware formatting (dates, numbers, plurals, collation)
but `Intl` APIs are unavailable or inconsistent across runtimes. Your
current approach either ships a massive data payload or produces
incorrect results for non-Latin scripts and complex locale rules.

## Context

ICU4X is a Unicode Consortium project written in Rust that provides
internationalization functionality designed for client-side and
resource-constrained environments. Unlike ICU4C (C++) and ICU4J (Java),
ICU4X uses zero-copy deserialization, modular data generation, and
compile-time dead-code elimination to produce small, fast binaries. In
2026, ICU4X 2.0 is stable with bindings for Rust, JavaScript (via WASM),
C++, Dart, and Objective-C. It provides ECMA-402-compatible APIs,
making it suitable as a polyfill or replacement for environments with
incomplete `Intl` support. The library is used in Firefox, Fuchsia, and
production mobile applications where binary size and memory footprint
are critical constraints.

## Architecture

```
ICU4X Data Pipeline:

┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ CLDR + ICU   │────►│ icu_datagen  │────►│ Baked Data   │
│ source data  │     │ (build-time) │     │ (compiled    │
│              │     │              │     │  into binary)│
└──────────────┘     └──────────────┘     └──────────────┘
                           │
                    ┌──────┴──────┐
                    │ Blob/FS     │
                    │ (runtime    │
                    │  loading)   │
                    └─────────────┘

Zero-copy flow:
  Source bytes → validate structure → construct pointers → use directly
  (No copying, no allocation, no parsing)
```

## Core components

```
icu_locale:
  → Locale parsing, canonicalization, negotiation
  → BCP-47 language tags
  → Locale fallback chains

icu_datetime:
  → Date and time formatting
  → Calendar systems (Gregorian, Buddhist, Japanese, Islamic, etc.)
  → Time zone formatting

icu_decimal:
  → Number formatting with grouping separators
  → Scientific and compact notation

icu_plurals:
  → CLDR plural rules for all locales
  → Cardinal and ordinal categories

icu_collator:
  → Locale-aware string comparison and sorting
  → Tailored collation for specific languages

icu_normalizer:
  → Unicode normalization (NFC, NFD, NFKC, NFKD)
  → Composing and decomposing characters

icu_segmenter:
  → Word, sentence, line, grapheme segmentation
  → Accurate for CJK, Thai, Khmer (no spaces)

icu_list:
  → Locale-aware list formatting ("A, B, and C")

icu_properties:
  → Unicode character properties
  → Script, category, bidirectional class
```

## Data management strategies

```rust
// Strategy 1: Compiled (baked) data — simplest, zero-cost loading
use icu::datetime::DateTimeFormatter;
use icu::locale::locale;

let formatter = DateTimeFormatter::try_new(
    locale!("fr").into(),
    Default::default(),
)?;
// Data is compiled into the binary at build time
// Dead-code elimination removes unused locale data

// Strategy 2: Blob provider — runtime loading from a binary blob
use icu_provider_blob::BlobDataProvider;

let blob = std::fs::read("icu4x_data.postcard")?;
let provider = BlobDataProvider::try_new_from_blob(blob.into_boxed_slice())?;
// Blob is zero-copy deserialized — no parsing overhead

// Strategy 3: FS provider — load individual files per locale
use icu_provider_fs::FsDataProvider;

let provider = FsDataProvider::try_new("/path/to/icu4x/data")?;
// Each locale/component loaded on demand
// Good for server-side with many locales
```

## Data generation (datagen)

```bash
# Generate baked data for specific locales and components
icu4x-datagen \
  --locales fr de ja ar zh \
  --components datetime decimal plurals list \
  --format blob2 \
  --out icu4x_data.postcard

# Generate compiled Rust data (baked provider)
icu4x-datagen \
  --locales fr de ja \
  --components datetime \
  --format mod \
  --out src/data/

# Generate only the data your code actually uses
icu4x-datagen \
  --format mod \
  --use-separate-crates
  # Dead-code elimination removes unused data at link time
```

## WASM integration

```javascript
// JavaScript via WASM bindings
import init, { ICU4XLocale, ICU4XDateTimeFormatter } from 'icu4x-wasm';

await init();

const locale = ICU4XLocale.create_from_string('ja');
const formatter = ICU4XDateTimeFormatter.create_with_length(
  provider,
  locale,
  'long', // date length
  'short' // time length
);

const result = formatter.format_iso_datetime(isoDatetime);
// "2026年8月16日 14:30"

// Bundle size: ~50-200 KB for typical use cases
// vs 30+ MB for full ICU4C
```

## Comparison with alternatives

```
                  ICU4X         ICU4C          Intl (browser)
Language:         Rust          C++            JS engine native
Binary size:      50-500 KB     5-30 MB        0 (built-in)
Data loading:     Zero-copy     File/memory    Engine internal
WASM support:     Native        Possible       N/A
CLDR version:     Latest        Latest         Varies by engine
Customization:    Full          Full           Limited
Consistency:      Identical     Identical      Varies by browser
Mobile:           Excellent     Heavy          Partial
Embedded:         Excellent     Impractical    Unavailable
```

## Anti-patterns

- **Bundling all CLDR data** — including data for all 700+ locales
  when your application supports 10. Use `icu4x-datagen` with
  `--locales` to generate only the data your application needs.
  This can reduce data size from megabytes to kilobytes.
- **Using ICU4C in WASM** — compiling ICU4C to WASM produces
  multi-megabyte binaries with slow initialization. ICU4X was
  designed for WASM from the start, with zero-copy deserialization
  and minimal allocations.
- **Falling back to manual formatting** — implementing date or
  number formatting with string concatenation instead of using
  locale-aware formatters. This produces incorrect results for
  most non-English locales (date order, grouping separators,
  decimal marks, plural forms).
- **Ignoring segmentation** — using whitespace splitting for word
  boundaries. Thai, Khmer, Japanese, and Chinese do not use spaces
  between words. ICU4X's segmenter handles these correctly using
  dictionary-based and rule-based algorithms.

## Gotchas

- **Data versioning** — ICU4X data is tied to a specific CLDR
  version. Upgrading the ICU4X library may require regenerating
  data files. Pin the CLDR version in your build pipeline.
- **Compiled data and binary size** — baked data is convenient
  but increases binary size proportionally to the number of
  locales and components. For applications supporting many locales,
  use blob or filesystem providers with on-demand loading.
- **FFI boundary overhead** — while ICU4X itself is zero-copy, the
  FFI boundary between Rust and JavaScript/C++ involves some
  copying. Batch operations where possible rather than calling
  across the FFI boundary per character or string.
- **No runtime locale detection** — ICU4X formats data but does
  not detect the user's locale. Combine with browser APIs
  (`navigator.languages`) or HTTP headers (`Accept-Language`)
  for locale detection.

## Verification

- Data generation is integrated into the build pipeline.
- Only required locales and components are included in the bundle.
- WASM binary size stays under budget (typically < 500 KB).
- Formatting output matches CLDR expected results for all supported locales.
- Segmentation handles CJK and Southeast Asian scripts correctly.
- Zero-copy deserialization is verified (no unnecessary allocations).

## Related

- `documentation/categories/i18n/icu-messageformat2-2026.md`
- `documentation/categories/i18n/unicode-collation-2026.md`
- `documentation/categories/i18n/text-segmentation-2026.md`

## Source URLs (verified 2026-08-16)

- ICU4X Project — https://icu4x.unicode.org/
- ICU4X GitHub Repository — https://github.com/unicode-org/icu4x
- ICU4X Rust Documentation — https://docs.rs/icu
- Global Text Infrastructure: i18n, ICU, and Rust's ICU4X — https://www.minimalistinnovation.com/post/global-text-infrastructure-i18n-icu-rust
