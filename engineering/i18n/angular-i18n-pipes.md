# angular-i18n-pipes

**Issue:** Using Angular built-in i18n pipes for locale-aware formatting
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Angular ships `DatePipe`, `DecimalPipe`, `CurrencyPipe`, and `PercentPipe`. They are locale-aware when the app is configured with a locale provider.

## Pattern / Solution
Register locale data once:
```ts
import { registerLocaleData } from '@angular/common';
import localeFr from '@angular/common/locales/fr';
import { LOCALE_ID } from '@angular/core';
registerLocaleData(localeFr);
@NgModule({
  providers: [{ provide: LOCALE_ID, useValue: 'fr-FR' }],
})
export class AppModule {}
```
Templates:
```html
{{ price | currency:'EUR':'symbol':'1.2-2' }}
{{ today | date:'longDate' }}
{{ ratio | percent:'1.0-1' }}
```
Extract strings:
```bash
ng extract-i18n --output-path src/locales --format xliff2
```

## Gotchas
- `LOCALE_ID` must be set before pipes render; dynamic switching requires re-bootstrap or custom pipe
- `@angular/common/locales` tree-shakes — only registered locales are included
- Default extraction format is XLIFF 1.2; use `--format xliff2` for XLIFF 2

## Related
- `xliff-format-handling.md`
- `date-formatting-intl.md`
