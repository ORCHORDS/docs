# gender-inflection-patterns

**Issue:** Handling grammatical gender in translations without combinatorial explosion
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Romance and Slavic languages inflect adjectives and verbs based on gender. Naive concatenation produces ungrammatical strings.

## Pattern / Solution
ICU `select` format:
```
{gender, select,
  male   {He completed the task}
  female {She completed the task}
  other  {They completed the task}
}
```
Combined gender + plural:
```
{gender, select,
  male   {{count, plural, one{He sent # message} other{He sent # messages}}}
  female {{count, plural, one{She sent # message} other{She sent # messages}}}
  other  {{count, plural, one{They sent # message} other{They sent # messages}}}
}
```
Russian example (verb ending depends on subject gender):
```json
{ "saved_by": "{actor, select, male{сохранён} female{сохранена} other{сохранено}}" }
```

## Gotchas
- `other` is required even in binary-gender systems
- Do not conflate grammatical gender with user-facing pronoun preference
- Finnish and Turkish are grammatically genderless

## Related
- `icu-message-format.md`
- `plural-rules-cldr.md`
