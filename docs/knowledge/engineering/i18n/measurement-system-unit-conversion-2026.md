# measurement-system-unit-conversion-2026

**Issue:** The app stored and displayed product dimensions and temperatures with units hardcoded per market ("72°F", "16 oz") and unit symbols baked into translation strings. Metric-locale users saw Fahrenheit with no way to read it, `Intl.NumberFormat` was never used because "the unit is part of the sentence", and no two systems agreed on the source-of-truth unit. The gap: `Intl.NumberFormat` with `style: 'unit'` only *formats* a number in a given unit — it never *converts* between measurement systems and never *chooses* the unit for a locale. Conversion and system selection are your code's job; this article covers how to do both without baking "°F" into copy.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Measurement systems per territory

1. **CLDR defines the territory defaults.** CLDR supplemental `measurementData.xml` maps each territory to a default system: `metric` (essentially everywhere), `US` (United States, plus Liberia and Myanmar as customary holdouts), and `UK` (hybrid: miles/yards for road distances and pints for beer, but Celsius for weather and kilograms for groceries). Never hardcode "imperial vs metric" — model the three-way choice and the hybrid case.
2. **The BCP 47 `-u-ms-` keyword requests a system.** Locale tags can carry the measurement system extension (`en-US-u-ms-uksystem`, `en-GB-u-ms-metric`), and ICU/CLDR consumers can read it. Use it to express an explicit user override inside your locale identifier itself.
3. **Region, not language, drives the default.** `en` is spoken in metric countries; `de` speakers in the US may want US customary. Resolve the system from the locale's *region* subtag (mapped through CLDR data), falling back to metric when the region is unknown.
4. **User preference beats territory default.** Offer a metric/imperial toggle for anything consequential (weather, fitness distances, cooking) and persist it; locale-derived defaults are a starting point, not a rule.

## Store canonical, convert at display

1. **Pick one canonical unit per quantity and store only that.** Meters, grams, liters, degrees Celsius (or raw Kelvin if you prefer), seconds — store the number plus the canonical unit, never a preformatted string like `"5'11\""`. Conversion happens once, at the display boundary.
2. **Convert with explicit factors, and convert temperatures correctly.** Lengths and masses scale (`km = miles × 1.609344`), but temperature has an offset: `°F = °C × 9/5 + 32`. The classic bug is applying a factor without the offset (or the reverse direction with the operations in the wrong order). Freeze-test both directions: 0°C ↔ 32°F, 100°C ↔ 212°F, -40° equal in both.
3. **Format the converted value with `Intl.NumberFormat` unit style.** `new Intl.NumberFormat('en-US', { style: 'unit', unit: 'fahrenheit' }).format(72)` yields "72°F" with locale-correct grouping; `unitDisplay: 'long'` gives "72 degrees Fahrenheit" for accessible/verbose contexts; `narrow` avoids spaces where space is scarce. Unit identifiers are CLDR unit IDs (`kilometer-per-hour`, `celsius`), not free text.
4. **Never bake the unit symbol into the translation string.** A message like `"High of {temp}°F today"` cannot be re-unit-ed. Send translators `{value}` where value is pre-formatted by `Intl` for the chosen unit, or pass `{amount}` + `{unit}` and compose with an ICU `{unit, select}`-style pattern if the grammar demands it.
5. **Round to sensible display precision after converting.** 72°F → 22.222°C should display as 22°C; a 5 km race in miles should show 3.1 mi, not 3.10686 mi. Round for display only — keep the full-precision canonical value for math.

## Conversion pitfalls

1. **Intl does not convert, and it will not pick the unit.** `Intl.NumberFormat` formats whatever unit and magnitude you pass (Stack Overflow is full of "why doesn't Intl convert cm to m" — it doesn't, and there is no auto-scaling to bigger units either: 1500 m stays "1,500 m" unless you convert to km yourself).
2. **US and imperial units differ.** The US pint is 16 fl oz (473 ml); the imperial pint is 20 fl oz (568 ml). Same word, ~20% different quantity — gallons, tons, and fluid ounces all diverge. Use region-correct conversion factors (`fl oz (US)` vs `fl oz (Imp)`), especially for recipes and beverages.
3. **Some "units" do not convert by factor at all.** Clothing and shoe sizes (EU 42 ≈ US 9 men's, but not linearly), paper sizes (A4 vs Letter), ring sizes, and drill gauges are nominal scales — they need lookup tables, not arithmetic. Never offer a "converted" shoe size computed from a length factor.
4. **Hybrid locales need per-quantity choices.** UK users expect miles for driving but Celsius for weather and stone for body weight; a single "use imperial" switch produces wrong-feeling results. Decide system per quantity family, guided by CLDR/territory conventions.
5. **Precision and accumulated error.** Convert once from canonical to display; converting a chain (stored km → shown miles → re-entered → stored as "miles" → converted again) compounds rounding. Always know which unit a given field is in, ideally typed (`Quantity { value: number, unit: 'km' }`) rather than implicit.
