# Font Subsetting Pipeline for Multi-Script Web Fonts with R2

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

An example.com page serving Japanese, Arabic, and Latin users loads a single variable font that
covers all three scripts. The full font file is 4.2 MB. CLS (Cumulative Layout Shift) spikes
because the fallback system font has different metrics, and LCP is delayed because the font
blocks rendering. Breaking the font into per-script subsets—served via Cloudflare R2 + a Workers
font router—reduces per-locale payload to 60–280 KB while keeping the build pipeline automated
and cache-efficient.

## Context

Font subsetting extracts only the Unicode codepoints needed for a specific script or locale from
a larger typeface file, producing a smaller file that retains full OpenType feature fidelity for
that script. The toolchain used here is:

- **`fonttools` (Python)** — the reference subset tool (`pyftsubset`); produces correct
  GSUB/GPOS table slices for Arabic joining and Japanese GSUB ligatures
- **`glyphhanger`** — crawl-based subset calculation from live page content
- **Cloudflare R2** — immutable, content-addressed storage for subset files
- **Cloudflare Workers** — serve the correct subset based on `Accept-Language` or an explicit
  locale query parameter; inject `Font-Display` headers

Font files are content-addressed by hashing the subset codepoint set + source font version:
`{family}/{version}/{script-tag}/{hash}.woff2`. This enables indefinite `Cache-Control:
immutable` headers and eliminates cache invalidation on font updates.

## Unicode Codepoint Ranges by Script

```python
# scripts/font_ranges.py
# CLDR / Unicode script ranges used as subset boundaries.
# These include the core ranges; combining marks and OpenType features
# pull in additional codepoints via pyftsubset's --layout-features flag.

SCRIPT_RANGES = {
    'latin': [
        'U+0020-007E',  # Basic Latin
        'U+00A0-00FF',  # Latin-1 Supplement
        'U+0100-017F',  # Latin Extended-A
        'U+0180-024F',  # Latin Extended-B
        'U+1E00-1EFF',  # Latin Extended Additional (Vietnamese diacritics)
        'U+2000-206F',  # General Punctuation
        'U+20A0-20CF',  # Currency Symbols
    ],
    'arabic': [
        'U+0600-06FF',  # Arabic block
        'U+0750-077F',  # Arabic Supplement
        'U+FB50-FDFF',  # Arabic Presentation Forms-A (required for correct joining)
        'U+FE70-FEFF',  # Arabic Presentation Forms-B
        'U+0660-0669',  # Arabic-Indic digits (Eastern Arabic numerals)
        'U+06F0-06F9',  # Extended Arabic-Indic digits (Urdu/Persian)
    ],
    'hebrew': [
        'U+0590-05FF',  # Hebrew block
        'U+FB1D-FB4F',  # Hebrew Presentation Forms
    ],
    'japanese': [
        'U+3000-303F',  # CJK Symbols and Punctuation
        'U+3040-309F',  # Hiragana
        'U+30A0-30FF',  # Katakana
        'U+4E00-9FFF',  # CJK Unified Ideographs (core)
        'U+F900-FAFF',  # CJK Compatibility Ideographs
        'U+FF00-FFEF',  # Halfwidth and Fullwidth Forms
    ],
    'korean': [
        'U+AC00-D7A3',  # Hangul Syllables
        'U+1100-11FF',  # Hangul Jamo
        'U+3130-318F',  # Hangul Compatibility Jamo
    ],
    'cyrillic': [
        'U+0400-04FF',  # Cyrillic
        'U+0500-052F',  # Cyrillic Supplement
    ],
    'devanagari': [
        'U+0900-097F',  # Devanagari
        'U+A8E0-A8FF',  # Devanagari Extended
    ],
}
```

## Build Script: pyftsubset Pipeline

```python
#!/usr/bin/env python3
# scripts/subset_fonts.py
import hashlib, json, subprocess, sys
from pathlib import Path

FONT_SOURCE = Path('fonts/source/OrchordsSans-Variable.ttf')
OUTPUT_DIR  = Path('fonts/dist')
FONT_VERSION = '3.2.1'  # bump on each source font update

# OpenType layout features preserved per script
LAYOUT_FEATURES = {
    'arabic':     'mark,mkmk,calt,liga,curs,init,medi,fina,isol',
    'japanese':   'mark,mkmk,calt,liga,vert,vrt2,kern',
    'hebrew':     'mark,mkmk,calt',
    'latin':      'mark,mkmk,calt,liga,kern,lnum,tnum',
    'default':    'mark,mkmk,calt,kern',
}

def make_unicodes(ranges: list[str]) -> str:
    return ','.join(ranges)

def subset_font(script: str, unicode_ranges: list[str]) -> Path:
    unicodes = make_unicodes(unicode_ranges)
    # Hash the content key for immutable cache naming
    content_key = f'{FONT_VERSION}:{script}:{unicodes}'
    file_hash   = hashlib.sha256(content_key.encode()).hexdigest()[:12]
    outfile     = OUTPUT_DIR / script / f'{file_hash}.woff2'
    outfile.parent.mkdir(parents=True, exist_ok=True)

    if outfile.exists():
        print(f'[skip] {script}/{file_hash}.woff2 (cached)')
        return outfile

    features = LAYOUT_FEATURES.get(script, LAYOUT_FEATURES['default'])
    cmd = [
        'pyftsubset', str(FONT_SOURCE),
        f'--unicodes={unicodes}',
        f'--layout-features={features}',
        '--flavor=woff2',
        '--with-zopfli',           # better compression for static assets
        '--name-IDs=*',            # preserve full name table
        '--notdef-outline',
        f'--output-file={outfile}',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f'pyftsubset failed for {script}')

    size_kb = outfile.stat().st_size // 1024
    print(f'[done] {script}/{file_hash}.woff2  ({size_kb} KB)')
    return outfile

def main():
    from font_ranges import SCRIPT_RANGES
    manifest = {}
    for script, ranges in SCRIPT_RANGES.items():
        path = subset_font(script, ranges)
        manifest[script] = {
            'file':    str(path.relative_to(OUTPUT_DIR.parent)),
            'hash':    path.stem,
            'version': FONT_VERSION,
            'ranges':  ranges,
        }

    manifest_path = OUTPUT_DIR / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f'\nManifest written to {manifest_path}')

if __name__ == '__main__':
    main()
```

## R2 Upload via Wrangler (CI Step)

```bash
#!/bin/bash
# ci/upload-fonts.sh
set -euo pipefail

BUCKET="orchords-fonts"
DIST="fonts/dist"

# Upload each subset with immutable cache headers
find "$DIST" -name '*.woff2' | while read -r file; do
  key="fonts/${file#$DIST/}"  # e.g. fonts/japanese/abc123def456.woff2
  wrangler r2 object put "$BUCKET/$key" \
    --file "$file" \
    --content-type "font/woff2" \
    --cache-control "public, max-age=31536000, immutable"
  echo "Uploaded: $key"
done

# Upload the manifest (not immutable—changes on each font release)
wrangler r2 object put "$BUCKET/fonts/manifest.json" \
  --file "$DIST/manifest.json" \
  --content-type "application/json" \
  --cache-control "public, max-age=300"
```

The manifest is short-lived (5 min TTL) so Workers can discover new subset hashes quickly after
a font release. The WOFF2 files themselves are indefinitely cached—the hash in the filename
guarantees a new URL for every new subset.

## Workers Font Router

```ts
// src/font-worker.ts
import { Env } from './env';

// Map BCP 47 language to Unicode script tag
const LANG_TO_SCRIPT: Record<string, string> = {
  ar: 'arabic', he: 'hebrew', fa: 'arabic', ur: 'arabic',
  ja: 'japanese', ko: 'korean',
  ru: 'cyrillic', uk: 'cyrillic', bg: 'cyrillic',
  hi: 'devanagari', mr: 'devanagari', ne: 'devanagari',
};

function detectScript(acceptLanguage: string): string {
  const primaryTag = acceptLanguage.split(',')[0].trim().split(';')[0].trim();
  const lang = new Intl.Locale(primaryTag).language;
  return LANG_TO_SCRIPT[lang] ?? 'latin';
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // /fonts/manifest.json — serve manifest from R2
    if (url.pathname === '/fonts/manifest.json') {
      const obj = await env.FONTS_BUCKET.get('fonts/manifest.json');
      if (!obj) return new Response('Not found', { status: 404 });
      return new Response(obj.body, {
        headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=300' },
      });
    }

    // /fonts/auto — detect script from Accept-Language and redirect to hash URL
    if (url.pathname === '/fonts/auto') {
      const acceptLang = request.headers.get('Accept-Language') ?? 'en';
      const script = detectScript(acceptLang);

      // Read manifest to get current hash
      const manifestObj = await env.FONTS_BUCKET.get('fonts/manifest.json');
      if (!manifestObj) return new Response('Font manifest unavailable', { status: 503 });
      const manifest = await manifestObj.json<Record<string, { hash: string }>>();
      const entry = manifest[script] ?? manifest['latin'];

      // Permanent redirect to the content-addressed URL (cached at CDN)
      return Response.redirect(
        `${url.origin}/fonts/${script}/${entry.hash}.woff2`,
        301,
      );
    }

    // /fonts/{script}/{hash}.woff2 — serve from R2, set immutable headers
    const match = url.pathname.match(/^\/fonts\/([\w-]+)\/([a-f0-9]+)\.woff2$/);
    if (match) {
      const [, script, hash] = match;
      const key = `fonts/${script}/${hash}.woff2`;
      const obj = await env.FONTS_BUCKET.get(key, { onlyIf: request.headers });

      if (!obj) return new Response('Not found', { status: 404 });
      if (obj.status === 304) return new Response(null, { status: 304 });

      return new Response(obj.body, {
        headers: {
          'Content-Type': 'font/woff2',
          'Cache-Control': 'public, max-age=31536000, immutable',
          'ETag': obj.httpEtag,
          'Access-Control-Allow-Origin': '*',  // required for cross-origin font loading
        },
      });
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## CSS @font-face with font-display and size-adjust

```css
/* Generated by build step from manifest.json */
/* public/fonts.css */

@font-face {
  font-family: 'OrchordsSans';
  src: url('https://fonts.example.com/fonts/latin/abc123def456.woff2') format('woff2');
  unicode-range:
    U+0020-007E, U+00A0-00FF, U+0100-017F,
    U+0180-024F, U+1E00-1EFF, U+2000-206F, U+20A0-20CF;
  font-weight: 100 900;
  font-display: swap;
  /* size-adjust prevents layout shift when swapping from system fallback */
  size-adjust: 98.5%;
  ascent-override: 95%;
  descent-override: 22%;
}

@font-face {
  font-family: 'OrchordsSans';
  src: url('https://fonts.example.com/fonts/arabic/fed987cba321.woff2') format('woff2');
  unicode-range:
    U+0600-06FF, U+0750-077F,
    U+FB50-FDFF, U+FE70-FEFF,
    U+0660-0669, U+06F0-06F9;
  font-weight: 100 900;
  font-display: swap;
}
```

The `unicode-range` descriptor ensures browsers only download the Arabic subset when the page
contains Arabic codepoints—no JS detection required.

## Anti-patterns

- **Storing font files in R2 without content-addressed naming.** A mutable key like
  `fonts/latin/latest.woff2` means the CDN serves stale files after an update until the
  `Cache-Control` TTL expires. Content-addressed names + `immutable` header = zero cache
  invalidation complexity.
- **Uploading fonts from CI without checking for existing objects.** The build script should skip
  uploading an R2 object when the key already exists (check with `wrangler r2 object head` or use
  the R2 API's `ifNoneMatch`). Unnecessary uploads add CI time and R2 operation costs.
- **Using a monolithic font for all locales via a CDN rewrite.** This is simpler to set up but
  means every user downloads 4+ MB. Subsetting is the correct solution.
- **Omitting `Access-Control-Allow-Origin` on font responses.** Fonts loaded cross-origin (from
  `fonts.example.com` into `example.com`) trigger CORS. Without the header, Firefox and Safari
  block the font silently—no console error, just fallback rendering.
- **Subsetting without `--layout-features`** `pyftsubset` defaults to subsetting only glyph
  outlines. Arabic text without `curs,init,medi,fina,isol` features renders as isolated letters
  rather than connected script—a critical rendering failure.

## Gotchas

- `pyftsubset` with `--with-zopfli` requires the `brotli` Python package and the `zopfli` binary.
  CI images often lack these; add them to the Docker image or use `pip install fonttools[woff]`
  which includes the pure-Python zopfli fallback.
- R2 has a 10 GB free tier then $0.015/GB/month storage and $0.36/million Class B operations
  (reads). Font files are small; storage cost is negligible. Read cost at scale: cache fonts
  aggressively at the CDN layer (Workers Cache API or Cloudflare's default CDN caching) to keep
  R2 reads minimal.
- The font manifest Worker route (`/fonts/auto`) performs an R2 read on every request. Cache the
  manifest in the Workers Cache API or KV with a 5-minute TTL to avoid R2 costs and latency on
  high-traffic font routes.
- Variable fonts subset differently than static fonts. `pyftsubset` retains the `gvar` and
  `HVAR` tables for variable fonts, which can make subsets larger than expected. Profile output
  size per script; if Japanese exceeds 400 KB, consider an additional subset by JLPT level or
  GSUB feature group.

## Verification

```bash
# Check subset integrity—OpenType validator
pip install fonttools
python -c "from fontTools.ttLib import TTFont; TTFont('fonts/dist/arabic/fed987cba321.woff2')"

# Confirm Arabic joining features survived subsetting
python -c "
from fontTools.ttLib import TTFont
font = TTFont('fonts/dist/arabic/fed987cba321.woff2')
print([r.LookupListIndex for r in font['GSUB'].table.FeatureList.FeatureRecord
       if r.FeatureTag in ('init','medi','fina','isol')])
"

# Verify CORS headers on production
curl -I -H 'Origin: https://example.com' \
  https://fonts.example.com/fonts/latin/abc123def456.woff2 | grep -i 'access-control'

# Size audit per subset
wrangler r2 object list orchords-fonts --prefix 'fonts/' | \
  awk '{print $1, $3}' | sort -k2 -n
```

## Related

- `multilingual-font-loading-subsetting.md`
- `chinese-japanese-cjk-fonts.md`
- `arabic-persian-text-rendering.md`
- `indic-script-rendering.md`
- `i18n-bundle-size-tree-shaking-2026.md`

## Sources

- fonttools / pyftsubset: https://fonttools.readthedocs.io/en/latest/subset/index.html
- Cloudflare R2 storage: https://developers.cloudflare.com/r2/
- Google Fonts `font-display` guide: https://developers.google.com/fonts/docs/css2#use_font-face_in_your_html
- Unicode Script property: https://www.unicode.org/reports/tr24/
- CSS `unicode-range` MDN: https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/unicode-range
- size-adjust descriptor: https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/size-adjust
