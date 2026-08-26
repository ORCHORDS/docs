# fetch-body-consumed-twice

**Issue:** Calling `response.json()` or `response.text()` twice on the same Response throws "body used already"
**Date:** 2026-08-11
**Status:** documented

## Symptom
`TypeError: body used already` or `TypeError: Failed to execute 'json' on 'Response': body is already used` is thrown on the second read attempt.

## Root cause
A `Response` body is a `ReadableStream` that can only be consumed once. Once `.json()`, `.text()`, `.arrayBuffer()`, or `.blob()` is called, the stream is exhausted. A second call fails.

## Fix
Use `response.clone()` before the first consume if you need to read the body multiple times:
```ts
const response = await fetch(url);
const responseForLogging = response.clone();

const data = await response.json();
const rawText = await responseForLogging.text(); // safe — separate clone
```
Or store the result in a variable instead of calling the body reader twice.

## Detection
```
grep -rn "response\." src/ --include="*.ts" | grep "\.json\|\.text\|\.arrayBuffer\|\.blob"
```
Look for multiple body-consuming calls on the same response variable.

## Related
- `response-clone-pattern.md`
- `fetch-no-throw-on-4xx.md`
