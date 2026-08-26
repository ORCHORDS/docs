# XLIFF 2.0 Migration from XLIFF 1.2 and Interoperability

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your translation pipeline was built on XLIFF 1.2 files exchanged with an LSP (Language
Service Provider) five years ago. Your current TMS has upgraded to XLIFF 2.0 as the
default export format. When you import the new files your build scripts throw XML parse
errors, placeholders like `<x id="0"/>` become `<ph id="1">` and `<mrk>` elements appear
in unexpected places. CAT tools from different vendors accept one version but reject the
other, or silently mangle inline codes.

You need to understand the structural differences, write a migration path, and implement
bidirectional interoperability so both old and new toolchain components can co-exist
during transition.

## Context

**XLIFF** (XML Localization Interchange File Format) is the industry standard file format
for exchanging translatable content between authoring tools, translation memory systems,
and CAT tools. It is an OASIS standard.

| Version | Published | Schema | Adoption |
|---|---|---|---|
| 1.0 | 2002 | DTD | Legacy |
| 1.2 | 2008 | RelaxNG + W3C XML Schema | Dominant (2008–2022) |
| 2.0 | 2014 | W3C XML Schema | Growing — major TMS by 2022+ |
| 2.1 | 2018 | W3C XML Schema | Current; adds metadata modules |

XLIFF 2.x is **not backward compatible** with XLIFF 1.2 — they share a name and concept
but have entirely different XML namespaces and element structures.

## Structural Differences

### File header

**XLIFF 1.2:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2"
  xmlns="urn:oasis:names:tc:xliff:document:1.2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <file original="src/locales/en.json"
    source-language="en" target-language="de"
    datatype="plaintext">
    <header>
      <tool tool-id="crowdin" tool-name="Crowdin"/>
    </header>
    <body>
      <!-- trans-units -->
    </body>
  </file>
</xliff>
```

**XLIFF 2.1:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xliff version="2.1"
  xmlns="urn:oasis:names:tc:xliff:document:2.0"
  srcLang="en" trgLang="de">
  <file id="f1" original="src/locales/en.json">
    <!-- units — no separate <header> or <body> wrapper -->
  </file>
</xliff>
```

Key differences in the root:
- Namespace changes from `xliff:document:1.2` to `xliff:document:2.0`
- `source-language`/`target-language` → `srcLang`/`trgLang` (on `<xliff>`, not `<file>`)
- No `<header>` or `<body>` wrapper in 2.x
- `datatype` attribute removed (handled by modules in 2.x)

### Translation units

**XLIFF 1.2:**
```xml
<trans-unit id="SAVE_BUTTON" resname="SAVE_BUTTON">
  <source>Save changes</source>
  <target state="translated">Änderungen speichern</target>
  <note from="developer">Appears in the settings form footer</note>
</trans-unit>
```

**XLIFF 2.1:**
```xml
<unit id="SAVE_BUTTON">
  <notes>
    <note category="developer">Appears in the settings form footer</note>
  </notes>
  <segment state="translated">
    <source>Save changes</source>
    <target>Änderungen speichern</target>
  </segment>
</unit>
```

Key differences:
- `<trans-unit>` → `<unit>` (which now contains one or more `<segment>` elements,
  enabling sentence-level segmentation within one logical unit)
- `<note from="developer">` → `<note category="developer">` inside `<notes>`
- `state` attribute moves from `<target>` to `<segment>`
- `resname` attribute is removed; the `id` is the canonical identifier

### State values

| XLIFF 1.2 `target state` | XLIFF 2.x `segment state` |
|---|---|
| `new` | `initial` |
| `needs-translation` | `initial` |
| `translated` | `translated` |
| `signed-off` | `reviewed` |
| `final` | `final` |
| `needs-review-translation` | `translated` (review is a workflow concern) |
| `needs-adaptation` | (no direct equivalent — use metadata module) |

### Inline codes

**XLIFF 1.2** uses `<x/>`, `<g>`, `<ph>`, `<bpt>`, `<ept>`, `<it>` for inline markup:

```xml
<source>Click <x id="1" equiv-text="&lt;strong&gt;"/>here<x id="2" equiv-text="&lt;/strong&gt;"/> to save</source>
```

**XLIFF 2.x** uses `<ph>` (standalone), `<sc>`/`<ec>` (paired span open/close), and
`<pc>` (paired container) from the `urn:oasis:names:tc:xliff:document:2.0` core:

```xml
<source>Click <pc id="1" canCopy="no" canDelete="no" equivEnd="2"><mrk translate="no">here</mrk></pc> to save</source>
```

Or using `<ph>` for standalone placeholders:

```xml
<source>Hello, <ph id="1" equiv="{name}" dataRef="d1"/></source>
<originalData>
  <data id="d1">{name}</data>
</originalData>
```

The `<originalData>` section is the XLIFF 2.x mechanism for safely round-tripping
source placeholders — the actual placeholder text (`{name}`) is stored in `<data>` and
referenced by `dataRef`, preventing translators from accidentally editing placeholder
syntax.

## Migration Script: XLIFF 1.2 → 2.1

```typescript
// scripts/xliff-migrate.ts
import { XMLParser, XMLBuilder } from 'fast-xml-parser';
import { readFileSync, writeFileSync } from 'fs';

const STATE_MAP: Record<string, string> = {
  'new': 'initial',
  'needs-translation': 'initial',
  'translated': 'translated',
  'signed-off': 'reviewed',
  'final': 'final',
  'needs-review-translation': 'translated',
  'needs-l10n': 'initial',
};

export function migrateXliff12to21(input: string): string {
  const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: '@_' });
  const doc = parser.parse(input);

  const xliff12 = doc.xliff;
  const files = Array.isArray(xliff12.file) ? xliff12.file : [xliff12.file];

  const units = files.flatMap((file: any, fileIndex: number) => {
    const transUnits = Array.isArray(file.body['trans-unit'])
      ? file.body['trans-unit']
      : [file.body['trans-unit']];

    return transUnits.map((tu: any) => {
      const state12 = tu.target?.['@_state'] ?? 'new';
      const state21 = STATE_MAP[state12] ?? 'initial';

      const unit: any = {
        '@_id': tu['@_id'] ?? tu['@_resname'],
      };

      if (tu.note) {
        unit.notes = {
          note: {
            '@_category': tu.note['@_from'] ?? 'general',
            '#text': typeof tu.note === 'string' ? tu.note : tu.note['#text'],
          },
        };
      }

      unit.segment = {
        '@_state': state21,
        source: { '#text': tu.source },
        target: { '#text': typeof tu.target === 'string' ? tu.target : tu.target?.['#text'] },
      };

      return unit;
    });
  });

  const xliff21 = {
    '?xml': { '@_version': '1.0', '@_encoding': 'UTF-8' },
    xliff: {
      '@_version': '2.1',
      '@_xmlns': 'urn:oasis:names:tc:xliff:document:2.0',
      '@_srcLang': xliff12['@_source-language'] ?? files[0]['@_source-language'],
      '@_trgLang': xliff12['@_target-language'] ?? files[0]['@_target-language'],
      file: {
        '@_id': 'f1',
        '@_original': files[0]['@_original'] ?? 'messages',
        unit: units,
      },
    },
  };

  const builder = new XMLBuilder({ ignoreAttributes: false, attributeNamePrefix: '@_', format: true });
  return builder.build(xliff21);
}

// CLI usage
const input = readFileSync(process.argv[2], 'utf8');
const output = migrateXliff12to21(input);
writeFileSync(process.argv[3] ?? process.argv[2].replace('.xlf', '-v2.xlf'), output);
console.log('Migration complete.');
```

## Bidirectional Interoperability Strategy

During TMS/toolchain migration you will have tools that produce XLIFF 1.2 and tools that
consume XLIFF 2.x, or vice versa. Use an adapter layer at the pipeline boundary:

```typescript
// lib/xliff/adapter.ts
import { migrateXliff12to21 } from './migrate-up.js';
import { migrateXliff21to12 } from './migrate-down.js'; // reverse direction

type XliffVersion = '1.2' | '2.0' | '2.1';

function detectVersion(xml: string): XliffVersion {
  if (xml.includes('xliff:document:1.2')) return '1.2';
  if (xml.includes('version="2.1"')) return '2.1';
  return '2.0';
}

export function normalizeToV21(xml: string): string {
  const version = detectVersion(xml);
  if (version === '1.2') return migrateXliff12to21(xml);
  return xml; // 2.0 and 2.1 are structurally compatible
}

export function normalizeToV12(xml: string): string {
  const version = detectVersion(xml);
  if (version !== '1.2') return migrateXliff21to12(xml);
  return xml;
}
```

## XLIFF 2.x Modules

XLIFF 2.1 has optional modules that extend the core for specific use cases:

| Module | Namespace prefix | Use case |
|---|---|---|
| Translation Candidates (TC) | `tc:` | TM match suggestions |
| Metadata (MTD) | `mtd:` | Custom key-value metadata |
| Format Style (FS) | `fs:` | HTML/markup preservation |
| Size Restriction (SZR) | `szr:` | Character/pixel limits per segment |
| Change Tracking (CT) | `ctr:` | Revision history |
| Validation (VAL) | `val:` | Custom validation rules |
| ITS (Information Typing) | `its:` | ITS 2.0 integration for domain, terminology |

For localization pipelines the most commonly needed modules are **Metadata** (for
storing source string context like screenshots, max length, domain), **Size Restriction**
(for UI strings with pixel-width limits), and **Translation Candidates** (when
exposing TM leverage within the XLIFF file).

## Anti-patterns

- **Renaming `trans-unit` to `unit` manually** — the segment model in XLIFF 2.x changes
  the semantics, not just the element name. A 1.2 `trans-unit` maps to a `unit`
  containing exactly one `segment`; do not merge or split without understanding the
  new segmentation model.
- **Ignoring `<originalData>`** — if your conversion tool strips `<originalData>` blocks,
  placeholder content (`{0}`, `<br>`, ICU expressions) is exposed to translators and will
  be corrupted in many CAT tools.
- **Treating XLIFF 2.0 and 2.1 as identical** — 2.1 adds the Change Tracking and
  Validation modules; files with those modules will fail schema validation against a
  2.0 XSD.
- **Mapping all XLIFF 1.2 states to XLIFF 2.x `initial`** — information loss; at minimum
  map `translated` → `translated` and `final` → `final` to preserve workflow state.
- **Using the same `id` attribute value in unit and segment** — in XLIFF 2.x, `<unit>`
  and `<segment>` have separate `id` namespaces; segment ids are auto-generated when
  there is only one segment per unit.

## Gotchas

- `fast-xml-parser` and similar JS libraries do not validate against XSD; run your output
  through the OASIS XLIFF 2.1 validator (`xliff-core-2.1.xsd`) before sending to an LSP.
- The XLIFF 1.2 `restype` attribute (for UI element type hints like `button`, `label`,
  `menu`) has no direct XLIFF 2.x equivalent; store it in the Metadata module.
- Some CAT tools (SDL Trados, memoQ) have their own XLIFF 2.x "flavors" with vendor
  extensions; always test your migration output in the specific tool your LSP uses.
- Character encoding must be UTF-8 in both versions; XLIFF 1.2 files saved by older tools
  in ISO-8859-1 must be re-encoded before migration.
- XLIFF 2.x uses `xml:space="preserve"` differently from 1.2; leading/trailing whitespace
  in `<source>` and `<target>` elements is significant in 2.x by default.

## Verification

```bash
# Validate XLIFF 2.1 output against the official XSD
# Download xliff-core-2.1.xsd from https://docs.oasis-open.org/xliff/xliff-core/v2.1/
xmllint --schema xliff-core-2.1.xsd --noout output.xlf && echo "Valid XLIFF 2.1"

# Round-trip test: parse and re-serialize, compare segment count
node -e "
  const { normalizeToV21 } = require('./lib/xliff/adapter.js');
  const xml = require('fs').readFileSync('test.xlf', 'utf8');
  const v21 = normalizeToV21(xml);
  const segCount = (v21.match(/<segment/g) || []).length;
  const tuCount = (xml.match(/<trans-unit/g) || []).length;
  console.log('trans-units:', tuCount, '→ segments:', segCount);
  if (segCount !== tuCount) process.exit(1);
"
```

## Related

- `xliff-format-handling.md`
- `po-gettext-format.md`
- `translation-pipeline.md`
- `crowdin-phrase-translation-pipeline-automation.md`
- `tolgee-weblate-transifex-comparison-2026.md`
- `continuous-localization-cicd.md`

## Sources

- OASIS XLIFF 2.1 Specification: https://docs.oasis-open.org/xliff/xliff-core/v2.1/xliff-core-v2.1.html
- OASIS XLIFF 1.2 Specification: http://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html
- XLIFF 2 vs 1.2: Breaking changes summary — OASIS Technical Committee Note
- fast-xml-parser: https://github.com/NaturalIntelligence/fast-xml-parser
- xmllint man page (libxml2)
