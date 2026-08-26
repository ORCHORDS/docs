# icu-messageformat-advanced

**Issue:** ICU select, gender, number, date formatting in messages
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write `{count} {count, plural, one {item} other {items}}` in
English. The translator breaks it when translating to Russian
(needs `few` and `many` forms). The runtime shows raw ICU syntax
because the translation has unbalanced braces.

## Root cause
**ICU MessageFormat** is a complex syntax. Translators aren't
familiar with it. Errors are easy to introduce. The right
workflow uses tools that validate + visualize the message.

**Source:** ICU MessageFormat docs:
https://messageformat.icu/

## Common ICU patterns

### 1. Plural (covered in icu-plural-rules-20-locales.md)
```json
{
  "itemCount": "{count, plural, =0 {No items} one {1 item} few {# items} many {# items} other {# items}}"
}
```

### 2. Select (gender / variant)
```json
{
  "welcome": "{gender, select, male {Welcome, sir} female {Welcome, madam} other {Welcome, friend}}"
}
```

### 3. Number formatting
```json
{
  "balance": "Your balance is {amount, number, ::currency/USD}"
}
```

The `::currency/USD` is a skeleton — pre-defined number format.

### 4. Date formatting
```json
{
  "lastSeen": "Last seen {date, date, medium}"
}
```

### 5. Time formatting
```json
{
  "meetingTime": "Meeting at {time, time, short}"
}
```

### 6. Nested (select + plural)
```json
{
  "notification": "{user, select, friend {{count, plural, one {1 new message from your friend} other {# new messages from your friend}}} other {{count, plural, one {1 new message} other {# new messages}}}}"
}
```

This is hard to translate manually. Use a tool.

## Translation workflow

### Step 1: Generate source strings
Use `i18next-parser` or similar to extract all ICU messages from
the source code.

### Step 2: Translate with context
Send the source + target to a translator. Include the locale's
plural rules. For complex messages, include a screenshot or
example.

### Step 3: Validate
Before merging, validate the translated message:
```ts
import { MessageFormat } from 'messageformat';

function validateIcuMessage(template: string, locale: string): boolean {
  try {
    const mf = new MessageFormat(template, locale);
    return mf.format({ /* test values */ }) !== '';
  } catch (err) {
    return false;
  }
}
```

### Step 4: Visual QA
Render the message in the UI. Compare with the source. Check
for:
- Unbalanced braces
- Wrong number of plural categories
- Missing ICU placeholders (`{count}` without `count` arg)
- Whitespace issues (some locales put the count before/after
  the noun; some put it inside)

## Common pitfalls

### Unbalanced braces
```json
{
  "greeting": "Hello {name"  // missing }
}
```
Runtime: raw ICU syntax. Fix: add the `}`.

### Wrong plural category
```json
{
  "items": "{count, plural, one {1 item} other {# items}}"  // missing few/many
}
```
Runtime in Russian: the `other` form is used (wrong). Fix: add
`few` and `many`.

### Inline ICU in a translation
The translator may try to translate the ICU syntax itself:
```json
{
  "items_es": "{count, plural, uno {1 artículo} otros {# artículos}}"
}
```
Runtime: ICU doesn't know `uno` / `otros`. Fix: keep the ICU
keywords in English (`one`, `other`, `few`, `many`); only
translate the text inside `{...}`.

### Missing placeholder
```ts
t('greeting', { name: 'Alice' })  // template uses {name} and {age}
```
Runtime: `{age}` is rendered as `{age}`. Fix: add `age` to the
arguments.

## Verification
- **Test:** `test/icu.test.ts > all ICU messages parse for 20
  locales` — passes
- **Visual QA:** 20-locale screenshot pass
- **Translator review:** Native speaker reviews the complex
  messages

## Gotchas
- **Some i18n libs (next-intl) use ICU directly; others (i18next)
  use a simpler syntax.** Know which your project uses.
- **ICU in plural rules:** the locale's plural rules come from
  CLDR. The runtime lib uses them. Don't hardcode plural
  categories per locale.
- **Nested messages get exponentially complex.** Keep them
  shallow; split into multiple messages if possible.
- **The order of arguments in the template matters** for
  translators. `{name}, {count} items` is more translatable
  than `{count} items, {name}`.

## Related
- `icu-plural-rules-20-locales.md`
- `flat-dotted-vs-nested-keys.md`
- `data-i18n-marker-pattern.md`
- ICU: https://messageformat.icu/
- CLDR: https://cldr.unicode.org/
